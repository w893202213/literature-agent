"""MCP server：把文献综述工具链包装成标准 MCP 工具（阶段 2 加分项）。

用途（面试可讲）：
- 工具链（tools/）既能在项目内被 LangGraph 节点直调（编排式），
  也能以 MCP 标准协议暴露给任意 MCP client（Claude Desktop / 自研 Agent）；
- "直调 vs MCP"的取舍：直调零开销、类型安全；MCP 跨进程、跨语言、
  标准协议——本项目保留直调为主，MCP 作为对外开放通道。

启动：python -m mcp_server.server   （默认 stdio 传输）
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

server = MCPServer(name="literature-agent")


@server.tool()
def search_openalex_tool(query: str, per_page: int = 20) -> list[dict]:
    """按关键词搜索 OpenAlex 学术论文（无 key、限流宽松），返回论文元数据。"""
    from tools.search_openalex import search_openalex

    return [r.to_dict() for r in search_openalex(query, per_page=per_page)]


@server.tool()
def search_arxiv_tool(query: str, max_results: int = 20) -> list[dict]:
    """按关键词搜索 arXiv 论文（REST API + 缓存 + 限流重试）。"""
    from tools.search_arxiv import search_arxiv

    return [r.to_dict() for r in search_arxiv(query, max_results=max_results)]


@server.tool()
def fetch_pdf_tool(pdf_url: str) -> dict:
    """下载 PDF 到本地缓存，返回保存路径；失败返回错误信息。"""
    from tools.fetch_pdf import fetch_pdf

    path = fetch_pdf(pdf_url)
    if path is None:
        return {"status": "error", "message": "下载失败（可能 403/网络错误）"}
    return {"status": "ok", "path": str(path)}


@server.tool()
def parse_pdf_tool(pdf_path: str, max_chars: int = 3000) -> dict:
    """解析本地 PDF 全文（双栏排序），返回字符数与开头文本。"""
    from tools.parse_pdf import parse_pdf

    text = parse_pdf(pdf_path)
    if text is None:
        return {"status": "error", "message": "解析失败（加密/损坏/无文本）"}
    return {"status": "ok", "total_chars": len(text), "preview": text[:max_chars]}


@server.tool()
def extract_paper_info_tool(full_text: str) -> dict:
    """从论文全文提取结构化信息（title/method/datasets/results 等），含 meta。"""
    from tools.extract_paper_info import extract_paper_info

    info, meta = extract_paper_info(full_text)
    return {"paper": info, "meta": meta}


@server.tool()
def normalize_title_tool(title: str) -> str:
    """标题归一化（小写/去空白/去 arXiv 版本号/去标点），用于去重比较。"""
    from tools.dedupe import normalize_title

    return normalize_title(title)


if __name__ == "__main__":
    server.run()  # 默认 stdio 传输，可被 MCP client 直接拉起
