"""阶段 1 地基验证：真实搜索 ArXiv。

用法：
    python scripts/verify_search.py "vision-language knowledge distillation"
    python scripts/verify_search.py          # 使用默认主题
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.search_arxiv import search_arxiv  # noqa: E402


def main() -> None:
    topic = sys.argv[1] if len(sys.argv) > 1 else "vision-language knowledge distillation"
    print(f"=== 搜索主题：{topic} ===")
    results = search_arxiv(topic, max_results=5)
    print(f"返回 {len(results)} 篇\n")
    for r in results:
        print(f"  [{r.arxiv_id}] {r.title[:70]}")
        print(f"      作者数={len(r.authors)} | 年份={r.published[:4]} | 分类={','.join(r.categories[:3])}")
        print(f"      pdf: {r.pdf_url}")


if __name__ == "__main__":
    main()
