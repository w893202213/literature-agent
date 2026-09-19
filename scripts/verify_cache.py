"""缓存命中验证：不请求网络，验证 search_arxiv 的数据流正确。

用法：python scripts/verify_cache.py
原理：向缓存目录写入一条假数据 → 调 search_arxiv → 应命中缓存直接返回。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.search_arxiv import _cache_path, search_arxiv  # noqa: E402

QUERY = "vision-language knowledge distillation"
MAX_RESULTS = 5

FAKE_RESULTS = [
    {
        "arxiv_id": "2301.00001",
        "title": "Test Paper A: Vision-Language Distillation",
        "authors": ["Alice Zhang", "Bob Li"],
        "summary": "A fake cached entry for data-flow verification.",
        "published": "2023-01-01T00:00:00Z",
        "pdf_url": "https://arxiv.org/pdf/2301.00001",
        "categories": ["cs.CV"],
    }
]


def main() -> None:
    cache_file = _cache_path(QUERY, MAX_RESULTS, "relevance")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(FAKE_RESULTS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已写入假缓存: {cache_file}")

    results = search_arxiv(QUERY, max_results=MAX_RESULTS)
    print(f"search_arxiv 返回 {len(results)} 篇（应命中缓存=1 篇）")
    for r in results:
        print(f"  [{r.arxiv_id}] {r.title} | 作者数={len(r.authors)} | {r.pdf_url}")

    assert len(results) == 1, "缓存命中失败"
    assert results[0].arxiv_id == "2301.00001", "缓存内容解析错误"
    print("✅ 缓存命中 + 数据流验证通过")


if __name__ == "__main__":
    main()
