"""相关性筛选验证：搜索 + 筛选，打印每篇打分（不下载不提取）。

用法：python scripts/verify_rank.py "主题" [候选数]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.pipeline import _search  # noqa: E402
from tools.rank import filter_candidates  # noqa: E402


def main() -> None:
    topic = sys.argv[1] if len(sys.argv) > 1 else "CLIP knowledge distillation"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    print(f"=== 筛选验证: {topic} ===")

    candidates = _search(topic, "openalex", n)
    print(f"搜索到 {len(candidates)} 篇候选\n")

    kept, stats = filter_candidates(topic, candidates, min_score=3)
    print(
        f"\n筛选统计: {stats['before']} → 年份 {stats['after_year']}"
        f" → 去重 {stats['after_dedupe']} → 打分 {stats['scored']}"
        f" → 保留 {stats['kept']}"
    )
    print("\n保留的候选:")
    for c in kept:
        sc = c.scores.get("relevance")
        print(f"  [{sc}/5] {c.paper_id} | {c.title[:50]} | {c.year}")


if __name__ == "__main__":
    main()
