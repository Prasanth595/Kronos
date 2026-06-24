"""Smoke test for the MCP server: spawn it over stdio and call each tool.

Verifies the four tools are exposed and that responses carry the honesty framing.
"""
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server.py"],
        cwd=PROJECT_ROOT,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("TOOLS:", names)
            assert set(names) == {"list_instruments", "get_forecast",
                                  "get_accuracy", "refresh_actuals"}, names

            r = await session.call_tool("list_instruments", {})
            text = r.content[0].text
            print("\n--- list_instruments (head) ---")
            print(text[:400])
            assert "PAST DAILY PRICE CANDLES ONLY" in text

            r = await session.call_tool("get_forecast",
                                        {"instrument": "gold", "pred_len": 4, "n_samples": 6})
            text = r.content[0].text
            print("\n--- get_forecast gold (head) ---")
            print(text[:600])
            assert "DISTRIBUTION" in text
            assert "CAVEAT" in text

            r = await session.call_tool("get_accuracy", {"instrument": "gold"})
            print("\n--- get_accuracy gold ---")
            print(r.content[0].text[:300])

            r = await session.call_tool("refresh_actuals", {})
            print("\n--- refresh_actuals ---")
            print(r.content[0].text[:200])

    print("\n[OK] MCP server smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
