#!/usr/bin/env python
"""Test the signals agent test_connection functionality."""
import asyncio
import sys


async def main():
    """Test signals agent registry test_connection method."""
    from src.core.signals_agent_registry import SignalsAgentRegistry

    # Create registry
    registry = SignalsAgentRegistry()

    # Test with a non-existent agent (should fail gracefully)
    print("Testing connection to non-existent agent...")
    result = await registry.test_connection(
        agent_url="http://localhost:9999/mcp",
        auth={"type": "bearer", "credentials": "test-token"},
        auth_header="Authorization",
    )

    print(f"Result: {result}")
    print(f"Success: {result.get('success')}")

    if result.get("success"):
        print(f"✅ Connection successful! Signal count: {result.get('signal_count')}")
        return 0
    else:
        print(f"❌ Connection failed: {result.get('error')}")
        # This is expected for a non-existent endpoint, so we'll check if it failed gracefully
        if "Connection failed" in result.get("error", "") or "timeout" in result.get("error", "").lower():
            print("✅ Failed gracefully as expected (connection refused/timeout)")
            return 0
        else:
            print("⚠️  Unexpected error format")
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
