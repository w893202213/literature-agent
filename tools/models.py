"""数据模型（阶段 1）：搜索源统一的数据结构。

独立成模块是为了避免循环导入（pipeline / rank / 各搜索源都需要它）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PaperCandidate:
    """搜索源统一的论文候选（pipeline 只认这个抽象）。"""

    paper_id: str          # 稳定唯一标识（arxiv_id / openalex_id / doi 哈希）
    title: str
    pdf_url: str           # 可下载的 PDF 直链（无则跳过下载）
    authors: list[str] = field(default_factory=list)
    summary: str = ""
    year: str = ""
    venue: str = ""
    source: str = ""       # "arxiv" / "openalex"
    scores: dict = field(default_factory=dict)  # 相关性打分（rank 环节写入）
