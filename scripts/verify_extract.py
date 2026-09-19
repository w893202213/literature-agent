"""结构化提取验证：真实论文 PDF → LLM 提取 → Schema 校验。

用法：python scripts/verify_extract.py <pdf路径>
验证：解析 → 截断 → LLM 结构化提取（三重保险）→ 校验 → 打印结果。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.extract_paper_info import extract_paper_info  # noqa: E402
from tools.parse_pdf import parse_pdf, truncate_text  # noqa: E402
from tools.schemas import validate_paper_info  # noqa: E402


def main() -> None:
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf_path:
        print("用法: python scripts/verify_extract.py <pdf路径>")
        sys.exit(1)

    print(f"=== 提取: {Path(pdf_path).name} ===")
    text = parse_pdf(pdf_path)
    if text is None:
        print("❌ PDF 解析失败")
        sys.exit(1)
    print(f"✅ 解析 {len(text)} 字符 → 截断为 {min(len(text), 12_000)} 字符")

    info, meta = extract_paper_info(text)
    print(f"meta: attempts={meta['attempts']}, error={meta['error']!r}")

    if info is None:
        print("❌ 提取失败（重试耗尽）")
        sys.exit(1)

    ok, err = validate_paper_info(info)
    print(f"Schema 校验: {'✅ 通过' if ok else f'❌ {err}'}")
    print("\n--- 提取结果（截断显示）---")
    for k, v in info.items():
        s = str(v).replace("\n", " ")
        print(f"  {k}: {s[:120]}")
    print(f"\n字段数: {len(info)}")


if __name__ == "__main__":
    main()
