"""诊断：未命中论文用什么关键词能在 OpenAlex 召回。

用法：python scripts/diag_missed.py
对评测集未命中论文尝试多种关键词，打印哪个能命中。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_eval import load_dataset  # noqa: E402
from tools.dedupe import normalize_title  # noqa: E402
from tools.search_openalex import search_openalex  # noqa: E402

MISSED = ["2504.07615", "2503.11794", "2512.12701",
          "2603.01096", "2506.18985", "2506.23663"]


def try_query(p, query: str) -> tuple[bool, list[str]]:
    """用 query 搜索，返回 (是否命中, 前 3 条标题)。"""
    results = search_openalex(query, per_page=15, oa_only=False, year_from=2025)
    nt = normalize_title(p["title"])
    hit = any(normalize_title(r.title) == nt or r.paper_id == p["arxiv_id"]
              for r in results)
    titles = [r.title[:50] for r in results[:3]]
    return hit, titles


def main() -> None:
    dataset = {p["arxiv_id"]: p for p in load_dataset()}
    for aid in MISSED:
        p = dataset.get(aid, {})
        title = p.get("title", "")
        candidates = [
            title[:60],
            title.split(":")[0][:40] if ":" in title else title[:25],
            title.replace(": ", " ").split()[:3],
            " ".join(title.replace(": ", " ").split()[:2]),
        ]
        print(f"\n== {aid} {title[:55]}")
        for i, q in enumerate(candidates):
            if isinstance(q, list):
                q = " ".join(q)
            hit, titles = try_query(p, q)
            mark = "✅" if hit else "  "
            print(f"  {mark} [{i}] 关键词「{q[:35]}」→ {'命中' if hit else '未命中'} | 前几条: {titles}")


if __name__ == "__main__":
    main()
