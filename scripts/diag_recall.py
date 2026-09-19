"""诊断：OpenAlex 搜索结果与评测集的匹配情况。

用法：python scripts/diag_recall.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_eval import load_dataset  # noqa: E402
from tools.dedupe import normalize_title  # noqa: E402
from tools.search_openalex import search_openalex  # noqa: E402


def main() -> None:
    dataset = load_dataset()
    topic = dataset[0].get("_topic", "")
    results = search_openalex(topic, per_page=50)
    print(f"搜索 '{topic}' → {len(results)} 条结果\n")

    gold_titles = {normalize_title(p["title"]) for p in dataset}
    for i, r in enumerate(results[:30]):
        n = normalize_title(r.title)
        hit = "★命中" if n in gold_titles else ""
        print(f"  [{i}] {r.title[:70]} | {r.paper_id} {hit}")

    # 检查评测集标题是否出现在结果（宽松子串）
    print("\n--- 宽松匹配检查（评测集标题子串出现在结果中）---")
    for p in dataset:
        t = p["title"]
        found = any(t[:30].lower() in r.title.lower() for r in results)
        if found:
            print(f"  ✅ {t[:60]}")


if __name__ == "__main__":
    main()
