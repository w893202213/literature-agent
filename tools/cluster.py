"""主题聚类工具（阶段 2）。

用途：对已提取的论文按主题聚类，聚类结果作为：
1. 对比表格的章节划分依据；
2. 综述 related work 段落的分组依据。

实现选择（阶段 2 定）：
- A. embedding + 无监督聚类（k-means / agglomerative，配合 bge-m3）；
- B. LLM 直接对论文列表做主题分组（论文量 ≤ 50 时更省事，可先用这个）。
"""

from __future__ import annotations

from typing import Any


def cluster_by_llm(
    paper_infos: list[dict[str, Any]],
    client: Any = None,
    max_groups: int = 6,
) -> list[dict[str, Any]]:
    """（TODO 阶段2）用 LLM 把论文分成 max_groups 个主题组。

    Returns:
        [{"topic": "主题名", "paper_indices": [0, 3, 7], "summary": "组内共性"}, ...]
    """
    raise NotImplementedError("阶段 2 实现：LLM 主题分组")


# TODO(阶段2): embedding + agglomerative 聚类
#   def cluster_by_embedding(...) -> list[dict]: ...
