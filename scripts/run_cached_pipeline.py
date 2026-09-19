"""基于缓存跑流水线：验证 下载→解析→提取→落盘 全链路。

用法：python scripts/run_cached_pipeline.py [篇数]
从 data/cache/search/*.json 读取搜索结果（免网络搜索），逐篇跑 process_one_paper。
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.pipeline import process_one_paper  # noqa: E402
from tools.search_arxiv import SearchResult  # noqa: E402


def load_cached_results() -> list[SearchResult]:
    results: list[SearchResult] = []
    for f in glob.glob("data/cache/search/*.json"):
        items = json.loads(Path(f).read_text(encoding="utf-8"))
        results.extend(SearchResult(**item) for item in items)
    return results


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    results = load_cached_results()
    print(f"缓存中 {len(results)} 篇，本次处理 {min(limit, len(results))} 篇\n")

    run = "cached-pipeline"
    ok, fail = 0, 0
    for r in results[:limit]:
        rec = process_one_paper(r, run)
        if rec["status"] == "ok":
            ok += 1
        else:
            fail += 1
    print(f"\n=== 完成: 成功 {ok} / 失败 {fail} ===")


if __name__ == "__main__":
    main()
