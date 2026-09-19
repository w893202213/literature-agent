"""Semantic Scholar 论文搜索工具（阶段 1）。

用途：补充引用数 / venue / 年份等排序信号，与 ArXiv 结果做交叉。
注意：注册免费 key（S2_API_KEY）后限流约 5000 次/5 分钟；无 key 限流极严。
参考 API：https://api.semanticscholar.org/graph/v1/paper/search
"""

from __future__ import annotations

from typing import Any

import requests

import config

S2_BASE = "https://api.semanticscholar.org/graph/v1"


def search_semanticscholar(
    query: str,
    max_results: int = 20,
    fields: str = "title,abstract,year,venue,citationCount,externalIds,url",
) -> list[dict[str, Any]]:
    """按关键词搜索 Semantic Scholar。

    Args:
        query: 搜索关键词。
        max_results: 返回条数上限（官方上限 100）。
        fields: 需要的字段，默认含引用数与 venue。

    Returns:
        规范化字典列表，形如：
        [{"paperId", "title", "abstract", "year", "venue",
          "citationCount", "externalIds": {"ArXiv": "..."}, "url"}, ...]
    """
    params: dict[str, Any] = {
        "query": query,
        "limit": min(max_results, 100),
        "fields": fields,
    }
    headers: dict[str, str] = {}
    if config.settings.s2_api_key:
        headers["x-api-key"] = config.settings.s2_api_key

    try:
        resp = requests.get(
            f"{S2_BASE}/paper/search",
            params=params,
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 429:
            print("[search_semanticscholar] 触发限流（429），请检查 S2_API_KEY 或放慢节奏")
            return []
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.RequestException as e:
        print(f"[search_semanticscholar] 请求失败: {e}")
        return []


# TODO(阶段1): 实现按 arxiv_id 查询单篇引用数/venue 的补充函数
#   def get_citation_by_arxiv_id(arxiv_id: str) -> dict | None: ...
