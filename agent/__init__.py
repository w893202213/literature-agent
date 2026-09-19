"""agent —— LangGraph 编排层。

职责：把 tools/ 里的工具编排成端到端流程，含任务规划与失败恢复。
状态定义见 state.py，节点实现见 nodes.py，图组装见 graph.py。

阶段 0 还会在此目录旁手写一个 ReAct loop（scripts/react_demo.py）理解原理，
然后与 LangGraph 版对比，记录取舍结论（面试可讲）。
"""
