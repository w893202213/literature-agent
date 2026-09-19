"""全流程状态对象（LangGraph 的 State）。

设计原则：
- 状态是各节点之间传递的唯一载体，节点只读写自己的字段；
- 错误信息进 errors 列表 + 日志，单篇失败不中断整体流程；
- 所有阶段共用这一个状态，便于可视化调试与日志导出。
"""

from __future__ import annotations

from typing import Any, TypedDict

from tools.io import run_id


class PipelineState(TypedDict, total=False):
    """端到端流程状态。

    plan:     Planner 输出的任务规划（搜索词、限制条件等）
    papers:   搜索结果列表（tools.search_arxiv.SearchResult.to_dict()）
    filtered: 筛选去重后的论文列表
    downloads: {arxiv_id: 本地 PDF 路径}（失败项不在其中）
    extracted: {arxiv_id: PaperInfo dict}
    clusters:  聚类结果 [{topic, paper_indices, summary}]
    tables:   对比表格（Markdown 与 CSV 文本）
    review:   综述初稿（Markdown）
    verified: 引用核验结果 [{ref, arxiv_id, status}]
    errors:   [(step, arxiv_id|None, message)] —— 失败恢复的依据
    meta:     运行统计 {tokens, cost, step_timings: {step: seconds}}
    messages: 与 LLM 的对话历史（阶段 0 ReAct demo 用）
    """

    # 输入
    run_id: str
    topic: str
    seed_papers: list[str]          # 种子论文 arxiv_id（可选）
    max_papers: int
    source: str                     # 搜索源：openalex / arxiv
    min_score: int                  # 相关性打分阈值
    year_from: int | None           # 年份下限

    # 中间产物
    plan: dict[str, Any]
    papers: list[dict[str, Any]]
    filtered: list[dict[str, Any]]
    downloads: dict[str, str]       # arxiv_id -> 本地路径
    extracted: dict[str, dict[str, Any]]  # arxiv_id -> PaperInfo
    clusters: list[dict[str, Any]]
    tables: dict[str, str]          # {"markdown": str, "csv": str}
    review: str
    verified: list[dict[str, Any]]

    # 错误与统计
    errors: list[tuple[str, str | None, str]]
    meta: dict[str, Any]
    output: dict[str, Any]          # output 节点生成的运行汇总


def new_state(topic: str, seed_papers: list[str] | None = None,
              max_papers: int = 50, source: str = "openalex",
              min_score: int = 3, year_from: int | None = None) -> PipelineState:
    """构造初始状态。"""
    return {
        "run_id": run_id(),
        "topic": topic,
        "seed_papers": seed_papers or [],
        "max_papers": max_papers,
        "source": source,
        "min_score": min_score,
        "year_from": year_from,
        "plan": {},
        "papers": [],
        "filtered": [],
        "downloads": {},
        "extracted": {},
        "clusters": [],
        "tables": {},
        "review": "",
        "verified": [],
        "errors": [],
        "meta": {"tokens": 0, "cost": 0.0, "step_timings": {}},
    }
