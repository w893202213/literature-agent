"""诊断：搜索结果里是否有评测集论文（宽松匹配）。

用法：python scripts/diag_recall2.py [查询词]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_eval import load_dataset  # noqa: E402
from tools.search_openalex import search_openalex  # noqa: E402


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "vision-language model"
    results = search_openalex(query, per_page=50, oa_only=False,
                              sort="publication_date:desc")
    print(f"搜索「{query}」→ {len(results)} 条（按时间倒序）\n")
    for r in results[:40]:
        print(f"  {r.year} | {r.title[:80]}")

    dataset = load_dataset()
    gold_titles = [p["title"] for p in dataset]
    print("\n--- 评测集标题宽松匹配 ---")
    for p in dataset:
        t = p["title"]
        hit = any(
            t[:25].lower() in r.title.lower() or r.title.lower() in t[:25].lower()
            for r in results
        )
        if hit:
            print(f"  ✅ {t[:60]}")
    print("（无 ✅ 输出 = 前 50 条里没有评测集论文）")


if __name__ == "__main__":
    main()
