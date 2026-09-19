"""MCP server 实现（阶段 2 加分项，限时 1 周）。

TODO(阶段2):
1. 安装 mcp 依赖并启用 requirements.txt 中对应行；
2. 用 FastMCP 注册工具，例如：

    from mcp.server.fastmcp import FastMCP
    from tools.search_arxiv import search_arxiv

    mcp = FastMCP("literature-agent")

    @mcp.tool()
    def search_arxiv_tool(query: str, max_results: int = 20) -> list[dict]:
        return [r.to_dict() for r in search_arxiv(query, max_results)]

    if __name__ == "__main__":
        mcp.run()   # 默认 stdio 传输，可被 MCP client 直接拉起

3. 若超时未完成，删除本目录并将取舍结论写进 README。
"""
