#!/usr/bin/env python3
"""Test that sync_creatives accepts webhook_url parameter."""

import asyncio
import sys
from datetime import UTC, datetime

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def test_sync_creatives_with_webhook():
    """Test sync_creatives with webhook_url parameter."""

    # Use local MCP server
    headers = {
        "x-adcp-auth": "f68ZhutgGiHEMwHo8jKlr0heEsptkmElRVNfzYiz1IY",  # Default tenant token
    }

    transport = StreamableHttpTransport(url="http://localhost:8085/mcp/", headers=headers)

    async with Client(transport=transport) as client:
        print("✓ Connected to MCP server")

        # Create a test creative
        test_creative = {
            "creative_id": f"test_webhook_{datetime.now(UTC).timestamp()}",
            "name": "Test Creative with Webhook",
            "format_id": "display_300x250",
            "url": "https://example.com/test-ad.jpg",
            "click_url": "https://example.com/click",
            "width": 300,
            "height": 250,
        }

        print("\n📤 Calling sync_creatives with webhook_url parameter...")
        print(f"   Creative: {test_creative['name']}")
        print("   Webhook: https://webhook.example.com/notify")

        try:
            result = await client.call_tool(
                "sync_creatives", {"creatives": [test_creative], "webhook_url": "https://webhook.example.com/notify"}
            )

            print("\n✅ SUCCESS! Server accepted webhook_url parameter")
            print("\n📊 Result:")
            print(f"   {result}")

            return True

        except Exception as e:
            print(f"\n❌ FAILED: {e}")
            if "webhook_url" in str(e) and "Unexpected keyword argument" in str(e):
                print("\n🔍 Diagnosis: Server doesn't accept webhook_url parameter yet")
                print("   - Check if server was restarted after code changes")
                print("   - Verify _sync_creatives_impl() has webhook_url parameter")
            return False


if __name__ == "__main__":
    success = asyncio.run(test_sync_creatives_with_webhook())
    sys.exit(0 if success else 1)
