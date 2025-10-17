#!/usr/bin/env python3
import asyncio
import json
import sys

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def main():
    try:
        print("Connecting to creative agent...", file=sys.stderr)
        transport = StreamableHttpTransport(url="https://creative.adcontextprotocol.org/mcp")
        client = Client(transport=transport)

        async with client:
            print("Calling list_creative_formats...", file=sys.stderr)
            result = await client.call_tool("list_creative_formats", {})

            print(f"Got result, has structured_content: {hasattr(result, 'structured_content')}", file=sys.stderr)
            data = result.structured_content

            print(f"Data type: {type(data)}", file=sys.stderr)
            print(f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}", file=sys.stderr)

            if "formats" in data and data["formats"]:
                print(f"Found {len(data['formats'])} formats", file=sys.stderr)
                # Find display_300x250_image
                for fmt in data["formats"]:
                    if fmt.get("format_id", {}).get("id") == "display_300x250_image":
                        print("Found display_300x250_image format!")
                        print(json.dumps(fmt, indent=2, default=str))
                        break
            else:
                print("No formats found!", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()


asyncio.run(main())
