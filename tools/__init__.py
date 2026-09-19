"""tools —— 文献综述 Agent 的工具链。

每个工具模块保持独立可测、无内部状态，便于：
1. 单元测试（tests/test_tools.py）
2. 被 LangGraph 节点调用（agent/nodes.py）
3. 被 MCP server 包装暴露（mcp_server/server.py）

工具清单：
- schemas                 PaperInfo JSON Schema + 校验
- search_arxiv            ArXiv 搜索
- search_semanticscholar  Semantic Scholar 搜索（引用数/venue）
- fetch_pdf               下载 PDF
- parse_pdf               PyMuPDF 全文提取
- extract_paper_info      LLM 结构化提取
- dedupe                  标题归一化 + embedding 去重
- cluster                 主题聚类（阶段 2）
"""
