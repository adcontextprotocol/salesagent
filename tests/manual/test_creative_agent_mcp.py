#!/usr/bin/env python3
"""
Manual test script to directly test creative agent MCP endpoints.

This bypasses our integration test schema issues and directly verifies
the creative agent works correctly.

Usage:
    # Make sure creative agent is running
    docker-compose up -d creative-agent

    # Run this script
    python tests/manual/test_creative_agent_mcp.py
"""

import asyncio
import json

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def test_creative_agent():
    """Test creative agent MCP endpoints directly."""

    # Connect to creative agent MCP server
    url = "http://localhost:8095/mcp/"
    print(f"Connecting to creative agent at {url}")

    transport = StreamableHttpTransport(url=url)
    client = Client(transport=transport)

    async with client:
        print("\n" + "=" * 80)
        print("1. Testing list_formats tool")
        print("=" * 80)

        try:
            formats = await client.call_tool("list_formats", {})
            print("\n✅ list_formats succeeded!")
            print(f"\nFormats returned: {len(formats.get('formats', []))}")

            # Print first 5 formats to see structure
            for i, fmt in enumerate(formats.get("formats", [])[:5]):
                print(f"\nFormat {i+1}:")
                print(f"  format_id: {fmt.get('format_id')}")
                print(f"  name: {fmt.get('name')}")
                print(f"  media_type: {fmt.get('media_type')}")
                if "dimensions" in fmt:
                    print(f"  dimensions: {fmt['dimensions']}")

            # Check for expected IAB formats
            format_ids = [f.get("format_id") for f in formats.get("formats", [])]
            expected_formats = ["display_300x250", "display_728x90", "video_640x480", "native_article"]

            print("\n\nChecking for expected standard formats:")
            for expected in expected_formats:
                if expected in format_ids:
                    print(f"  ✅ {expected} - FOUND")
                else:
                    print(f"  ❌ {expected} - MISSING")

        except Exception as e:
            print(f"\n❌ list_formats failed: {e}")
            import traceback

            traceback.print_exc()

        print("\n" + "=" * 80)
        print("2. Testing preview_creative tool")
        print("=" * 80)

        # Test with a minimal valid creative manifest
        test_manifest = {
            "format_id": "display_300x250",
            "assets": {"image": "https://via.placeholder.com/300x250", "clickthrough_url": "https://example.com"},
            "metadata": {"advertiser": "Test Advertiser", "campaign": "Test Campaign"},
        }

        print("\nTest manifest:")
        print(json.dumps(test_manifest, indent=2))

        try:
            preview = await client.call_tool("preview_creative", {"creative_manifest": test_manifest})

            print("\n✅ preview_creative succeeded!")
            print("\nPreview result structure:")
            print(json.dumps(preview, indent=2))

            # Check for required fields
            if "previews" in preview:
                print("\n✅ Has 'previews' field")
                print(f"   Number of previews: {len(preview['previews'])}")

                if preview["previews"]:
                    first_preview = preview["previews"][0]
                    print("\nFirst preview:")
                    print(f"  format_id: {first_preview.get('format_id')}")
                    print(f"  preview_url: {first_preview.get('preview_url')}")
                    print(f"  dimensions: {first_preview.get('dimensions')}")
            else:
                print("\n❌ Missing 'previews' field!")

            if "validation_errors" in preview:
                if preview["validation_errors"]:
                    print(f"\n⚠️  Validation errors: {preview['validation_errors']}")
                else:
                    print("\n✅ No validation errors")

        except Exception as e:
            print(f"\n❌ preview_creative failed: {e}")
            import traceback

            traceback.print_exc()

        print("\n" + "=" * 80)
        print("3. Testing preview_creative with invalid format")
        print("=" * 80)

        invalid_manifest = {"format_id": "invalid_format_9999", "assets": {}, "metadata": {}}

        try:
            preview = await client.call_tool("preview_creative", {"creative_manifest": invalid_manifest})

            print("\n✅ preview_creative returned (expected validation errors)")
            print("\nResult:")
            print(json.dumps(preview, indent=2))

            if preview.get("validation_errors"):
                print("\n✅ Got expected validation errors")
            else:
                print("\n⚠️  Expected validation errors but got none")

        except Exception as e:
            print(f"\n⚠️  preview_creative raised exception (might be expected): {e}")


if __name__ == "__main__":
    print("=" * 80)
    print("Creative Agent MCP Direct Test")
    print("=" * 80)
    print("\nThis script tests the creative agent MCP endpoints directly")
    print("to verify the agent works correctly.\n")

    asyncio.run(test_creative_agent())

    print("\n" + "=" * 80)
    print("Testing Complete")
    print("=" * 80)
