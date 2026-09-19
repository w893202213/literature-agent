"""PDF 全文提取工具（阶段 1，基于 PyMuPDF）。

容错设计（对齐 PROJECT_PLAN 第 5 节）：
- 双栏论文按块坐标排序（PyMuPDF 默认顺序可能错乱）；
- 公式/表格乱码是常态，直接保留原文即可，不报错；
- 加密或损坏 PDF 返回 None，由上层标记“解析失败”并跳过，不中断流程。
"""

from __future__ import annotations

from pathlib import Path

import pymupdf  # PyMuPDF 新 API（fitz 已弃用）


def _page_text_in_reading_order(page) -> str:
    """按阅读顺序提取一页文本（处理双栏论文）。

    问题：get_text("text") 按行返回，双栏论文左右栏会逐行交错；
    单纯按 y 分组也会让右栏顶部标题混进左栏正文。
    解决：先按 x 中位线分左右栏，再各栏内按 y 排序，先左后右拼接。
    单栏论文（右栏为空/占比极小）自动退化为按 y 排序。
    """
    blocks = [b for b in page.get_text("blocks") if b[4] and b[4].strip()]
    if not blocks:
        return ""

    width = page.rect.width
    mid = width / 2
    left = [b for b in blocks if b[0] < mid]
    right = [b for b in blocks if b[0] >= mid]

    # 右栏占比过低 → 视为单栏（或只是缩进），按 y 排序即可
    if not right or len(right) < len(left) * 0.2:
        left.sort(key=lambda b: (round(b[1] / 12.0), b[0]))
        return "\n".join(b[4].strip() for b in left)

    left.sort(key=lambda b: b[1])
    right.sort(key=lambda b: b[1])
    return "\n".join(b[4].strip() for b in left) + "\n" + "\n".join(
        b[4].strip() for b in right
    )


def parse_pdf(pdf_path: Path | str) -> str | None:
    """提取 PDF 全文，返回纯文本；失败（加密/损坏/缺页）返回 None。

    Args:
        pdf_path: 本地 PDF 文件路径。

    Returns:
        全文文本（按阅读顺序），解析失败返回 None。
    """
    path = Path(pdf_path)
    if not path.exists():
        print(f"[parse_pdf] 文件不存在: {path}")
        return None

    try:
        doc = pymupdf.open(path)
    except Exception as e:  # noqa: BLE001 —— 损坏/加密 PDF 常见，静默降级
        print(f"[parse_pdf] 打开失败（可能加密或损坏）: {e}")
        return None

    if doc.needs_pass:
        print(f"[parse_pdf] 加密 PDF，跳过: {path.name}")
        doc.close()
        return None

    pages: list[str] = []
    try:
        for page in doc:
            text = _page_text_in_reading_order(page)
            if text:
                pages.append(text)
    finally:
        doc.close()

    if not pages:
        print(f"[parse_pdf] 未提取到任何文本: {path.name}")
        return None

    # 拼接页间加换行分隔
    return "\n\n".join(pages)


def truncate_text(text: str, max_chars: int = 12_000) -> str:
    """截断过长的正文，控制发送给 LLM 的上下文长度（成本护栏）。

    策略：保留论文开头（摘要/引言/方法通常集中在前部），
    后续部分按段落截断。阶段 2 做 RAG 时可替换为按章节/块切分。
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n...[内容过长已截断]"
