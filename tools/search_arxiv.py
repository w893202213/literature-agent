"""ArXiv 论文搜索工具（阶段 1，REST 直调版）。

为什么不用 arxiv 官方库而用 REST 直调（可讲取舍）：
- **代理支持**：受限出口（NAT/共享 IP）下 arXiv 极易 429，REST 直调可通过
  `ARXIV_PROXY` 走代理（Clash 等），官方库不透明、难接代理；
- **可控性**：UA、限速、重试、Retry-After 全部自己控制；
- **协议透明**：ArXiv API 就是 `GET https://export.arxiv.org/api/query`（Atom XML），
  分页参数 start/max_results、排序 sortBy/sortOrder，面试能讲细节。

速率限制（对齐 PROJECT_PLAN 第 5 节）：
- 请求间隔 >= config.settings.arxiv_request_interval（默认 3s）；
- 429/5xx 指数退避重试（最多 5 次，2s→4s→8s→…→30s）；
- 本地缓存搜索结果（data/cache/search/），同一查询只请求一次。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import config

# Atom XML 命名空间
ATOM = "{http://www.w3.org/2005/Atom}"

# arXiv 官方建议 UA 带联系方式（礼貌抓取）
USER_AGENT = "lit-review-agent/0.1 (research automation; contact: local user)"


@dataclass
class SearchResult:
    """单篇论文的搜索元数据（搜索阶段产物，与解析阶段产物区分）。"""

    arxiv_id: str
    title: str
    authors: list[str]
    summary: str
    published: str          # ISO 日期字符串
    pdf_url: str
    categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "summary": self.summary,
            "published": self.published,
            "pdf_url": self.pdf_url,
            "categories": self.categories,
        }


class ArxivRateLimitError(ConnectionError):
    """arXiv 限流（429）：冷却窗口是分钟级，重试无意义，应快速失败。"""


# 重试策略：429（ArxivRateLimitError）立即放弃；其他网络错误（超时/断连）
# 指数退避重试 3 次（2s→4s→8s）。避免在限流窗口内白白等待。
_retry_arxiv = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    retry=retry_if_exception(lambda e: not isinstance(e, ArxivRateLimitError)),
)


def _build_url(
    query: str,
    start: int,
    max_results: int,
    sort_by: str,
    sort_order: str,
) -> str:
    """构造 ArXiv API URL（Atom XML 接口）。"""
    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,        # relevance / submittedDate / lastUpdatedDate
        "sortOrder": sort_order,  # ascending / descending
    }
    return "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)


def _proxies() -> dict[str, str] | None:
    """按配置返回代理字典；未配置返回 None（直连）。"""
    if config.settings.arxiv_proxy:
        return {"http": config.settings.arxiv_proxy, "https": config.settings.arxiv_proxy}
    return None


def _parse_entry(entry: ET.Element) -> SearchResult:
    """把一个 <entry> 解析成 SearchResult。"""
    full_id = (entry.findtext(f"{ATOM}id") or "").strip()   # http://arxiv.org/abs/2301.12345v2
    arxiv_id = full_id.rsplit("/abs/", 1)[-1].split("v")[0] if full_id else ""
    title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
    authors = [a.findtext(f"{ATOM}name") or "" for a in entry.findall(f"{ATOM}author")]
    summary = " ".join((entry.findtext(f"{ATOM}summary") or "").split())
    published = entry.findtext(f"{ATOM}published") or ""
    categories = [c.get("term", "") for c in entry.findall(f"{ATOM}category")]

    pdf_url = ""
    for link in entry.findall(f"{ATOM}link"):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
    if not pdf_url and arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    return SearchResult(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        summary=summary,
        published=published,
        pdf_url=pdf_url,
        categories=categories,
    )


@_retry_arxiv
def _fetch_results(
    query: str,
    start: int,
    max_results: int,
    sort_by: str,
    sort_order: str,
) -> list[SearchResult]:
    """请求 ArXiv 并解析结果（被重试装饰器包裹）。"""
    resp = requests.get(
        _build_url(query, start, max_results, sort_by, sort_order),
        headers={"User-Agent": USER_AGENT},
        proxies=_proxies(),
        timeout=30,
    )
    if resp.status_code == 429:
        # 限流窗口分钟级，不重试（ArxivRateLimitError 被重试策略排除）
        retry_after = resp.headers.get("Retry-After", "unknown")
        raise ArxivRateLimitError(f"arXiv 429 限流 (Retry-After={retry_after})")
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    return [_parse_entry(e) for e in root.findall(f"{ATOM}entry")]


def _cache_path(query: str, max_results: int, sort_by: str) -> Path:
    """搜索缓存的本地路径（按 query+max_results+sort_by 哈希命名）。"""
    key = hashlib.md5(f"{query}|{max_results}|{sort_by}".encode("utf-8")).hexdigest()[:16]
    return config.settings.cache_dir / "search" / f"{key}.json"


def search_arxiv(
    query: str,
    max_results: int = 20,
    sort_by: str = "relevance",
    sort_order: str = "descending",
    use_cache: bool = True,
) -> list[SearchResult]:
    """按关键词搜索 ArXiv。

    Args:
        query: 搜索关键词（支持 arxiv 查询语法，如 'all:knowledge distillation'）。
        max_results: 返回条数上限。
        sort_by: 排序方式，relevance / submittedDate / lastUpdatedDate。
                 relevance 失败（429/503）时自动降级 submittedDate。
        sort_order: ascending / descending。
        use_cache: 是否使用本地缓存（默认开——省请求、防限流）。

    Returns:
        规范化后的搜索结果列表；全部失败返回空列表（不抛异常）。
    """
    # 1. 命中缓存直接返回（防限流的治本手段）
    if use_cache:
        cache_file = _cache_path(query, max_results, sort_by)
        if cache_file.exists():
            try:
                items = json.loads(cache_file.read_text(encoding="utf-8"))
                return [SearchResult(**item) for item in items]
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[search_arxiv] 缓存损坏，忽略并重新请求: {e}")

    # 2. 全局限速：保证相邻请求间隔 >= config.settings.arxiv_request_interval
    time.sleep(config.settings.arxiv_request_interval)

    # 3. 排序降级链：relevance（相关性，最理想）失败 → submittedDate（最新，最稳）
    sort_chain = [sort_by]
    if sort_by != "submittedDate":
        sort_chain.append("submittedDate")

    last_err: Exception | None = None
    for s in sort_chain:
        try:
            results = _fetch_results(query, 0, max_results, s, sort_order)
        except Exception as e:  # noqa: BLE001 —— 429/503/网络错误均进入降级
            last_err = e
            print(f"[search_arxiv] 排序 {s} 失败({e})，尝试降级排序…")
            continue

        # 4. 写缓存（key 用实际成功的排序）
        if use_cache and results:
            cache_file = _cache_path(query, max_results, s)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return results

    print(f"[search_arxiv] 全部排序策略失败: {last_err}")
    return []


def build_arxiv_query(topic: str) -> str:
    """把自然语言主题转成 arXiv 查询串（all: 字段，AND 组合）。

    规则：
    - 按空白/逗号拆成词组（连字符词组如 vision-language 整体保留）；
    - 每个词组加引号 + all: 前缀（all: 覆盖标题+摘要+作者）；
    - 词组间 AND 连接（精准优先；召回不足时上层可拆多个子主题搜索）。

    Examples:
        >>> build_arxiv_query("vision-language knowledge distillation")
        'all:"vision-language" AND all:"knowledge" AND all:"distillation"'
        >>> build_arxiv_query("CLIP, prompt learning")
        'all:"CLIP" AND all:"prompt" AND all:"learning"'
    """
    terms = [t.strip() for t in re.split(r"[\s,;]+", topic) if t.strip()]
    if not terms:
        return ""
    return " AND ".join(f'all:"{t}"' for t in terms)
