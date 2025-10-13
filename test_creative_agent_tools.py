"""Test script to discover what tools the creative agent actually exposes."""

import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def discover_creative_agent_tools():
    """Connect to the creative agent and list available tools."""
    agent_url = "https://creative.adcontextprotocol.org"

    print(f"Connecting to creative agent: {agent_url}")

    transport = StreamableHttpTransport(url=f"{agent_url}/mcp")
    client = Client(transport=transport)

    try:
        async with client:
            # List all available tools
            print("\n" + "=" * 60)
            print("AVAILABLE TOOLS:")
            print("=" * 60)

            # Try to get tool list
            tools = await client.list_tools()

            for tool in tools:
                print(f"\n📦 {tool.name}")
                if hasattr(tool, 'description') and tool.description:
                    print(f"   {tool.description}")
                if hasattr(tool, 'inputSchema'):
                    print(f"   Schema: {tool.inputSchema}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"   Type: {type(e).__name__}")


if __name__ == "__main__":
    asyncio.run(discover_creative_agent_tools())
