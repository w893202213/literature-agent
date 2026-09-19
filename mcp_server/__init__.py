"""mcp_server —— 把 search/parse 等工具包装成 MCP server（阶段 2 加分项）。

规划（限时 1 周，超时退化为直调 + 文档说明取舍）：
- 用官方 Python SDK（mcp 包，见 requirements.txt 可选依赖）；
- 暴露工具：search_arxiv / search_semanticscholar / fetch_pdf / parse_pdf /
  extract_paper_info / dedupe；
- 保留直调路径（tools/ 可直接被 LangGraph 节点调用），
  能讲清“直调 vs MCP 通道”两种方式的取舍。
"""
