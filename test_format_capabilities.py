"""Test what list_creative_formats tells us about format capabilities."""

import asyncio
import json
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def test_format_capabilities():
    """Check what capabilities formats expose."""
    agent_url = "https://creative.adcontextprotocol.org"

    print(f"🔗 Connecting to creative agent: {agent_url}")

    transport = StreamableHttpTransport(url=f"{agent_url}/mcp")
    client = Client(transport=transport)

    try:
        async with client:
            print("\n" + "=" * 60)
            print("CALLING: list_creative_formats")
            print("=" * 60)

            # Get all formats
            result = await client.call_tool("list_creative_formats", {})

            # Parse the result
            if isinstance(result.content, list) and result.content:
                content = result.content[0]
                if hasattr(content, "text"):
                    data = json.loads(content.text)
                    formats = data.get("formats", [])

                    print(f"\n📊 Found {len(formats)} formats")
                    print("=" * 60)

                    # Look for formats that support build_creative
                    generative_formats = []
                    static_formats = []

                    for fmt in formats:
                        format_id = fmt.get("format_id")
                        format_type = fmt.get("type")
                        is_generative = fmt.get("is_generative", False)
                        capabilities = fmt.get("capabilities", {})

                        if is_generative:
                            generative_formats.append(fmt)
                        else:
                            static_formats.append(fmt)

                    # Show generative formats (support build_creative)
                    print(f"\n🤖 GENERATIVE FORMATS ({len(generative_formats)}):")
                    print("=" * 60)
                    for fmt in generative_formats[:5]:  # Show first 5
                        print(f"\n  {fmt.get('format_id')}")
                        print(f"  Name: {fmt.get('name')}")
                        print(f"  Type: {fmt.get('type')}")
                        caps = fmt.get('capabilities', {})
                        print(f"  Capabilities:")
                        for cap_name, cap_value in caps.items():
                            print(f"    - {cap_name}: {cap_value}")

                    # Show static formats (traditional upload)
                    print(f"\n\n📁 STATIC FORMATS ({len(static_formats)}):")
                    print("=" * 60)
                    for fmt in static_formats[:5]:  # Show first 5
                        print(f"\n  {fmt.get('format_id')}")
                        print(f"  Name: {fmt.get('name')}")
                        print(f"  Type: {fmt.get('type')}")
                        caps = fmt.get('capabilities', {})
                        if caps:
                            print(f"  Capabilities:")
                            for cap_name, cap_value in caps.items():
                                print(f"    - {cap_name}: {cap_value}")

                    # Look for specific capability fields
                    print("\n\n🔍 CHECKING FOR CAPABILITY PATTERNS:")
                    print("=" * 60)

                    # Check first format in detail
                    if formats:
                        first_format = formats[0]
                        print(f"\nDetailed view of: {first_format.get('format_id')}")
                        print(json.dumps(first_format, indent=2))

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_format_capabilities())
