"""PDF 解析验证：用本地真实论文 PDF 测试 parse_pdf。

用法：python scripts/verify_parse.py <pdf路径>
不依赖网络，验证：打开 → 提取全文 → 文本统计（双栏论文重点看开头顺序）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.parse_pdf import parse_pdf, truncate_text  # noqa: E402


def main() -> None:
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf_path:
        print("用法: python scripts/verify_parse.py <pdf路径>")
        sys.exit(1)

    print(f"=== 解析: {pdf_path} ===")
    text = parse_pdf(pdf_path)
    if text is None:
        print("❌ 解析失败（可能加密/损坏/无文本）")
        sys.exit(1)

    print(f"✅ 解析成功，全文 {len(text)} 字符")
    print("\n--- 开头 500 字符（检查双栏顺序/标题/摘要）---\n")
    print(text[:500])
    print("\n--- 截断工具检查 ---")
    short = truncate_text(text, max_chars=800)
    print(f"截断后 {len(short)} 字符，结尾: ...{short[-60:]}")


if __name__ == "__main__":
    main()
