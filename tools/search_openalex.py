"""OpenAlex 论文搜索工具（阶段 1，搜索主通道）。

为什么引入（问题文档 P11）：S2 key 申请被拒 + arXiv API 出口限流严重；
OpenAlex 无 key 限流宽松（约 10 万次/天），聚合 arXiv/S2/Crossref 数据，
自带被引数/venue/年份（正好是筛选排序需要的信号）+ OA PDF 链接。

API：GET https://api.openalex.org/works?search=<query>&per-page=<n>
要点：
- 摘要以"倒排索引"（abstract_inverted_index）返回，需要重建为文本；
- 论文唯一标识用 OpenAlex ID 或 DOI（不依赖 arXiv ID，覆盖更广）；
- best_oa_location.pdf_url 提供开放获取 PDF 直链（无则跳过下载）。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

import config

OPENALEX_BASE = "https://api.openalex.org/works"
USER_AGENT = "lit-review-agent/0.1 (research automation; contact: local user)"

# 限速器：模块级令牌桶（保证全局间隔 >= OPENALEX_REQUEST_INTERVAL）
# 替代固定 sleep——主动排队控制节奏，避免瞬时频率撞限流
OPENALEX_REQUEST_INTERVAL = 1.0  # 秒
_last_request_ts: float = 0.0


def _rate_limit() -> None:
    """全局限速：距上次请求不足间隔则 sleep 补足（多线程场景可加锁）。"""
    global _last_request_ts
    elapsed = time.time() - _last_request_ts
    wait = OPENALEX_REQUEST_INTERVAL - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.time()


def _http_get(params: dict[str, Any], retries: int = 2) -> requests.Response:
    """带 429 智能重试的 GET（尊重 Retry-After，内部重试 retries 次）。"""
    _rate_limit()
    params = dict(params)
    if config.settings.openalex_mailto:
        params["mailto"] = config.settings.openalex_mailto  # 礼貌池：提升配额
    resp = requests.get(
        OPENALEX_BASE,
        params=params,
        headers={"User-Agent": USER_AGENT},
        proxies=_proxies(),
        timeout=30,
    )
    if resp.status_code == 429 and retries > 0:
        retry_after = resp.headers.get("Retry-After")
        wait = min(float(retry_after) if retry_after else 3.0, 30.0)
        print(f"[search_openalex] 429 限流，按 Retry-After 等待 {wait:.0f}s 重试…")
        time.sleep(wait)
        return _http_get(params, retries - 1)
    return resp


@dataclass
class OpenAlexResult:
    """OpenAlex 搜索结果的规范化结构。"""

    openalex_id: str        # https://openalex.org/Wxxxx
    doi: str                # https://doi.org/xxx
    title: str
    authors: list[str]
    year: int
    venue: str              # raw_source_name（会议/期刊名）
    cited_by: int           # 被引数（排序信号）
    abstract: str           # 重建后的摘要文本
    pdf_url: str            # best_oa_location.pdf_url（无则空串）
    arxiv_id: str = ""      # ids.arxiv 若有（反查 arXiv 版用）

    @property
    def paper_id(self) -> str:
        """稳定唯一标识：优先 arXiv ID，否则 OpenAlex ID 尾段，否则 DOI。"""
        if self.arxiv_id:
            return self.arxiv_id
        tail = self.openalex_id.rstrip("/").rsplit("/", 1)[-1]  # Wxxxx
        return tail or hashlib.md5(self.doi.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "openalex_id": self.openalex_id,
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "cited_by": self.cited_by,
            "abstract": self.abstract,
            "pdf_url": self.pdf_url,
            "arxiv_id": self.arxiv_id,
        }


def rebuild_abstract(inverted: dict[str, list[int]] | None) -> str:
    """把 abstract_inverted_index（倒排索引）重建为摘要文本。

    OpenAlex 存的是 {词: [位置...]}，按位置排序拼接即得原文。
    """
    if not inverted:
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))


def _parse_work(w: dict[str, Any]) -> OpenAlexResult:
    """把一个 work 对象解析成 OpenAlexResult。"""
    title = (w.get("title") or w.get("display_name") or "").strip()
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in w.get("authorships", [])
    ]
    authors = [a for a in authors if a]

    primary = w.get("primary_location") or {}
    venue = primary.get("raw_source_name") or ""

    # 反查 arXiv ID：优先级 locations（arXiv 版本链接）> ids.arxiv
    arxiv_id = ""
    for loc in w.get("locations") or []:
        url = loc.get("landing_page_url") or ""
        if "arxiv.org/abs/" in url:
            arxiv_id = url.split("/abs/")[-1].split("v")[0]
            break
    if not arxiv_id:
        arxiv_val = (w.get("ids") or {}).get("arxiv")
        if arxiv_val:
            arxiv_id = str(arxiv_val).rsplit(":", 1)[-1].split("v")[0]

    # PDF 直链优先级（P11 教训：出版社 OA 链接常 403，arXiv 下载畅通）：
    # 1. arXiv ID → arXiv 直链（最可靠）
    # 2. best_oa_location.pdf_url（可能 403，fetch 失败会自动跳过）
    if arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    else:
        best_oa = w.get("best_oa_location") or {}
        pdf_url = best_oa.get("pdf_url") or ""

    return OpenAlexResult(
        openalex_id=w.get("id", ""),
        doi=w.get("doi", ""),
        title=title,
        authors=authors,
        year=w.get("publication_year") or 0,
        venue=venue,
        cited_by=w.get("cited_by_count") or 0,
        abstract=rebuild_abstract(w.get("abstract_inverted_index")),
        pdf_url=pdf_url,
        arxiv_id=arxiv_id,
    )


def _proxies() -> dict[str, str] | None:
    if config.settings.arxiv_proxy:
        return {"http": config.settings.arxiv_proxy, "https": config.settings.arxiv_proxy}
    return None


def _cache_path(
    query: str, per_page: int, oa_only: bool, year_from: int | None, sort: str | None
) -> Path:
    key = hashlib.md5(
        f"openalex|{query}|{per_page}|oa:{oa_only}|y:{year_from}|s:{sort}".encode("utf-8")
    ).hexdigest()[:16]
    return config.settings.cache_dir / "search" / f"{key}.json"


def search_openalex(
    query: str,
    per_page: int = 20,
    oa_only: bool = True,
    year_from: int | None = None,
    sort: str | None = None,
    use_cache: bool = True,
) -> list[OpenAlexResult]:
    """按关键词搜索 OpenAlex。

    Args:
        query: 搜索关键词（空格分隔的词，支持引号词组）。
        per_page: 返回条数（上限 200）。
        oa_only: 只搜开放获取（OA）论文（默认开——提高 PDF 可得率）。
        year_from: 只返回该年份及以后的论文（如 2023 → publication_year >= 2023）。
        sort: OpenAlex 排序字段，如 "publication_date:desc"（按时间最新优先）
              或默认（relevance_score 相关性）。
        use_cache: 本地缓存（默认开）。

    Returns:
        规范化结果列表；失败返回空列表。
    """
    if use_cache:
        cache_file = _cache_path(query, per_page, oa_only, year_from, sort)
        if cache_file.exists():
            try:
                items = json.loads(cache_file.read_text(encoding="utf-8"))
                return [OpenAlexResult(**item) for item in items]
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[search_openalex] 缓存损坏，忽略并重新请求: {e}")

    params: dict[str, Any] = {
        "search": query,
        "per-page": min(per_page, 200),
    }
    if sort:
        params["sort"] = sort
    filters: list[str] = []
    if oa_only:
        # 只返回开放获取论文（filter 语法：open_access.is_oa:true）
        filters.append("open_access.is_oa:true")
    if year_from:
        # publication_year:>year-1 等价于 >= year（OpenAlex filter 无 >=，用 >）
        filters.append(f"publication_year:>{int(year_from) - 1}")
    if filters:
        params["filter"] = ",".join(filters)

    try:
        resp = _http_get(params)
        resp.raise_for_status()
        results = [_parse_work(w) for w in resp.json().get("results", [])]
    except requests.RequestException as e:
        print(f"[search_openalex] 请求失败: {e}")
        return []

    if use_cache and results:
        cache_file = _cache_path(query, per_page, oa_only, year_from, sort)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return results
