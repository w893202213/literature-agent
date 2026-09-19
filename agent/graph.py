"""LangGraph 状态图组装（阶段 2）。

流程（对齐 PROJECT_PLAN 第 3 节架构图）：
    plan → search → filter → download → parse → extract
         → cluster → table → review → verify → output
    download/parse/extract 失败均记录 errors 后继续（条件边跳过失败项）。

阶段 0 先只验证 LangGraph 环境：跑通 ToolNode + 假工具的 demo，
此文件到时再从 demo 逐步长成完整图。
"""

from __future__ import annotations

from typing import Any

import httpx2
import config
from agent.state import PipelineState, new_state
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode


def build_graph():
    """构建并编译完整流水线图（阶段 2）。

    结构（对齐 PROJECT_PLAN 架构图）：
        START → planner → search → filter → process
             → summarize（对比表）→ review（综述+核验）→ output → END

    设计（面试可讲）：
    - 图管理"阶段流转"，节点内部"批量处理"：单篇失败在 process 节点内消化
      （复用 pipeline 的 skip 容错），图层面不感知单篇粒度；
    - 每节点写 JSONL 日志（tools.logger），可观测验收；
    - 状态对象 PipelineState 贯穿全流程（agent/state.py）。

    Returns:
        编译后的 LangGraph 应用：app.invoke(new_state(topic, ...))
    """
    from agent.nodes import (
        node_filter,
        node_output,
        node_planner,
        node_process,
        node_review,
        node_search,
        node_summarize,
    )

    graph = StateGraph(PipelineState)
    graph.add_node("planner", node_planner)
    graph.add_node("search", node_search)
    graph.add_node("filter", node_filter)
    graph.add_node("process", node_process)
    graph.add_node("summarize", node_summarize)
    graph.add_node("review", node_review)
    graph.add_node("output", node_output)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "search")
    graph.add_edge("search", "filter")
    graph.add_edge("filter", "process")
    graph.add_edge("process", "summarize")
    graph.add_edge("summarize", "review")
    graph.add_edge("review", "output")
    graph.add_edge("output", END)
    return graph.compile()


def run_agent_pipeline(
    topic: str,
    max_papers: int = 10,
    source: str = "openalex",
    min_score: int = 3,
    year_from: int | None = None,
) -> dict[str, Any]:
    """端到端跑 Agent 流水线（图版），返回最终状态中的关键结果。

    Args:
        topic: 研究主题。
        max_papers: 搜索候选上限。
        source: 搜索源（openalex 默认 / arxiv）。
        min_score: 相关性打分阈值。
        year_from: 年份下限。

    Returns:
        {"run_id", "searched", "filtered", "ok", "failed", "errors",
         "step_timings", "filter_stats", "output"}
    """
    app = build_graph()
    state = new_state(topic, max_papers=max_papers, source=source,
                      min_score=min_score, year_from=year_from)
    final = app.invoke(state)
    out = final.get("output") or {}
    return {
        "run_id": final.get("run_id"),
        "searched": out.get("searched"),
        "filtered": out.get("filtered"),
        "ok": len(final.get("extracted") or {}),
        "failed": len([e for e in final.get("errors") or [] if e[0] == "process"]),
        "errors": final.get("errors") or [],
        "step_timings": (final.get("meta") or {}).get("step_timings", {}),
        "filter_stats": out.get("filter_stats"),
        "output": out,
    }


# ---- 阶段 0：LangGraph 环境验证 demo ----
# 与 scripts/react_demo.py 的手写 ReAct 对比，取舍结论已写入 README「阶段 0 结论」。
def build_demo_graph() -> Any:
    """阶段 0 最小 demo 图：LLM 调用假工具（查天气）。

    结构（对比手写 ReAct，见 README）：
        START → agent(LLM bind_tools) ──有 tool_calls──> tools(ToolNode) ──> agent
                                          └──无 tool_calls──> END

    Returns:
        编译后的 LangGraph 应用，`app.invoke({"messages": [("human", "查询合肥天气")]})`。
    """
    @tool
    def fake_weather_tool(city: str) -> str:
        """查询指定城市的天气。"""
        fake_data = {"合肥": "晴 24°C", "北京": "多云 18°C", "上海": "小雨 22°C"}
        return fake_data.get(city, f"暂无{city}的天气数据")

    # 复用统一直连策略（见 client.py / config.USE_PROXY）
    llm_kwargs: dict[str, Any] = {}
    if not config.settings.use_proxy:
        llm_kwargs["http_client"] = httpx2.Client(trust_env=False)

    llm = ChatOpenAI(
        base_url=config.settings.openai_base_url,
        api_key=config.settings.openai_api_key,
        model=config.settings.model,
        temperature=0.0,
        **llm_kwargs,
    )
    llm_with_tools = llm.bind_tools([fake_weather_tool])

    def call_model(state: MessagesState) -> dict[str, Any]:
        """节点 1：模型决定是否调用工具（原生 function calling，无需文本解析）。"""
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    def should_continue(state: MessagesState) -> str:
        """条件边：模型输出带 tool_calls → 进 tools；否则结束。"""
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode([fake_weather_tool]))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def run_demo_langgraph(query: str = "查询合肥天气") -> str:
    """跑一次 LangGraph 版天气 demo，返回最终回答。"""
    app = build_demo_graph()
    final_state = app.invoke({"messages": [("human", query)]})
    return str(final_state["messages"][-1].content)
