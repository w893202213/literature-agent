"""OpenAlex 搜索验证：打印候选的 arXiv/PDF 命中情况。

用法：python scripts/verify_openalex.py [query] [per_page]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.search_openalex import search_openalex  # noqa: E402


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "CLIP knowledge distillation"
    per_page = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    print(f"=== OpenAlex 搜索: {query} (per_page={per_page}) ===")
    results = search_openalex(query, per_page=per_page)
    print(f"候选 {len(results)} 篇\n")
    for r in results:
        pdf = r.pdf_url[:70] if r.pdf_url else "(无 PDF)"
        print(f"  [{r.paper_id}] arxiv={r.arxiv_id or '-'}")
        print(f"      {r.title[:60]} | {r.year} | {r.venue[:30]} | 被引 {r.cited_by}")
        print(f"      pdf: {pdf}")


if __name__ == "__main__":
    main()
