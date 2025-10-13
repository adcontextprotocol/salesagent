"""Test calling preview_creative from the creative agent."""

import asyncio
import json
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def test_preview_creative():
    """Test the preview_creative tool from the creative agent."""
    agent_url = "https://creative.adcontextprotocol.org"

    print(f"🔗 Connecting to creative agent: {agent_url}")

    transport = StreamableHttpTransport(url=f"{agent_url}/mcp")
    client = Client(transport=transport)

    try:
        async with client:
            print("\n" + "=" * 60)
            print("CALLING: preview_creative")
            print("=" * 60)

            # Create a simple creative manifest for preview
            # Note: assets is a dictionary keyed by asset role
            creative_manifest = {
                "format_id": "display_300x250_image",
                "assets": {
                    "main_visual": {
                        "asset_type": "image",
                        "url": "https://picsum.photos/300/250",
                        "dimensions": {"width": 300, "height": 250}
                    }
                },
                "click_through_url": "https://example.com"
            }

            # Call preview_creative
            result = await client.call_tool(
                "preview_creative",
                {
                    "format_id": "display_300x250_image",
                    "creative_manifest": creative_manifest
                }
            )

            print("\n📦 RESULT:")
            print("=" * 60)

            # Parse the result
            if isinstance(result.content, list) and result.content:
                content = result.content[0]
                if hasattr(content, "text"):
                    data = json.loads(content.text)
                    print(json.dumps(data, indent=2))

                    # Highlight key parts
                    if "previews" in data:
                        print(f"\n✅ {len(data['previews'])} preview(s) generated!")
                        for i, preview in enumerate(data["previews"]):
                            print(f"\n   Preview {i+1}:")
                            print(f"   - URL: {preview.get('preview_url')}")
                            print(f"   - Type: {preview.get('preview_type')}")
                            if "dimensions" in preview:
                                dims = preview["dimensions"]
                                print(f"   - Size: {dims.get('width')}x{dims.get('height')}")
                else:
                    print(content)
            else:
                print(result)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"   Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_preview_creative())
