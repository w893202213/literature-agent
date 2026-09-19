"""MCP server 连通性验证：stdio 拉起 server，调用不联网工具。

用法：python scripts/verify_mcp.py
用 mcp.client.stdio 启动本项目的 MCP server，调用 normalize_title 工具
验证协议连通（不触发网络请求）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"✅ MCP server 连通，注册工具 {len(tools.tools)} 个：")
            for t in tools.tools:
                print(f"  - {t.name}")

            # 调用不联网工具验证协议
            res = await session.call_tool(
                "normalize_title_tool", {"title": "Foo-Bar: A Study v2"}
            )
            print(f"\n✅ normalize_title 调用结果: {res.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
