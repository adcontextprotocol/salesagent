#!/usr/bin/env python3
"""Test script to verify MCP client connectivity with various servers.

This tests our MCP connection logic against known-good MCP servers to isolate
whether the issue is with our client code or with specific servers.
"""

import asyncio
import sys
from dataclasses import dataclass

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


@dataclass
class TestServer:
    name: str
    url: str
    description: str


# Known MCP servers to test
TEST_SERVERS = [
    TestServer(
        name="Creative Agent",
        url="https://creative.adcontextprotocol.org/mcp",
        description="AdCP creative agent (known good)",
    ),
    TestServer(
        name="Audience Agent",
        url="https://audience-agent.fly.dev",
        description="Audience/signals agent (has compatibility issues)",
    ),
    TestServer(
        name="Local Sales Agent (MCP)",
        url="http://localhost:8100/mcp",
        description="Our own MCP server running in Docker",
    ),
]


async def test_mcp_server(server: TestServer) -> dict:
    """Test connection to a single MCP server.

    Returns:
        dict with test results
    """
    result = {
        "name": server.name,
        "url": server.url,
        "success": False,
        "error": None,
        "tools": [],
        "server_info": None,
    }

    try:
        print(f"\n{'='*60}")
        print(f"Testing: {server.name}")
        print(f"URL: {server.url}")
        print(f"Description: {server.description}")
        print(f"{'='*60}")

        # Create transport and client
        transport = StreamableHttpTransport(url=server.url)
        client = Client(transport=transport)

        async with client:
            print("✅ Connection established")
            print("✅ Session initialized")

            # Get server info
            if hasattr(client, "server_info"):
                result["server_info"] = client.server_info
                print(f"   Server: {client.server_info}")

            # List available tools
            try:
                print("   Requesting tool list...")
                tools_result = await client.list_tools()
                print(f"   Raw tools_result type: {type(tools_result)}")

                # FastMCP client.list_tools() returns a list directly, not a response object
                if isinstance(tools_result, list):
                    result["tools"] = [tool.name for tool in tools_result]
                    print(f"✅ Listed {len(result['tools'])} tools:")
                    for tool in result["tools"][:5]:  # Show first 5
                        print(f"   - {tool}")
                    if len(result["tools"]) > 5:
                        print(f"   ... and {len(result['tools']) - 5} more")
                else:
                    print(f"⚠️  Unexpected tools_result type: {type(tools_result)}")
                    print(f"   Content: {tools_result}")
            except Exception as e:
                print(f"⚠️  Could not list tools: {e}")
                import traceback

                traceback.print_exc()

            # Try a simple tool call if tools are available
            if result["tools"]:
                tool_name = result["tools"][0]
                print(f"\n   Attempting to call tool: {tool_name}")
                try:
                    # Try with minimal params
                    tool_result = await client.call_tool(tool_name, {})
                    print("   ✅ Tool call succeeded")
                    print(f"   Result type: {type(tool_result)}")
                except Exception as e:
                    print(f"   ⚠️  Tool call failed: {e}")

            result["success"] = True
            print(f"\n✅ SUCCESS: {server.name} is working!")

    except Exception as e:
        result["error"] = str(e)
        print(f"\n❌ FAILED: {type(e).__name__}: {e}")

    return result


async def main():
    """Run all MCP server tests."""
    print("\n" + "=" * 60)
    print("MCP CLIENT CONNECTIVITY TEST")
    print("=" * 60)
    print("\nTesting our MCP client against known servers...")
    print("This will help isolate whether issues are with our client")
    print("or with specific server implementations.")

    results = []
    for server in TEST_SERVERS:
        result = await test_mcp_server(server)
        results.append(result)
        await asyncio.sleep(1)  # Brief pause between tests

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    success_count = sum(1 for r in results if r["success"])
    total_count = len(results)

    for result in results:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"\n{status} {result['name']}")
        print(f"   URL: {result['url']}")
        if result["success"]:
            print(f"   Tools: {len(result['tools'])} available")
            if result["server_info"]:
                print(f"   Server: {result['server_info']}")
        else:
            print(f"   Error: {result['error']}")

    print(f"\n{'='*60}")
    print(f"Results: {success_count}/{total_count} servers working")
    print(f"{'='*60}\n")

    # Exit with error code if any tests failed
    sys.exit(0 if success_count == total_count else 1)


if __name__ == "__main__":
    asyncio.run(main())
