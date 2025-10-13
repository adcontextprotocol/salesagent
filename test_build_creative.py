"""Test calling build_creative from the creative agent."""

import asyncio
import json
import os
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def test_build_creative():
    """Test the build_creative tool from the creative agent."""
    agent_url = "https://creative.adcontextprotocol.org"

    # Get Gemini API key from environment
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("❌ GEMINI_API_KEY environment variable not set")
        print("   The creative agent requires YOUR API key (they don't pay for API calls)")
        return

    print(f"🔗 Connecting to creative agent: {agent_url}")
    print(f"🔑 Using Gemini API key: {gemini_api_key[:10]}...")

    transport = StreamableHttpTransport(url=f"{agent_url}/mcp")
    client = Client(transport=transport)

    try:
        async with client:
            print("\n" + "=" * 60)
            print("CALLING: build_creative")
            print("=" * 60)

            # Call build_creative with a simple test
            # Try a simpler format first - static display ad
            result = await client.call_tool(
                "build_creative",
                {
                    "message": "Create a simple display ad for EcoBean Coffee - a sustainable coffee brand. Use a clean, modern design with green tones. Include the tagline 'Freshly Roasted, Sustainably Sourced'.",
                    "format_id": "display_300x250_image",  # Try static format first
                    "gemini_api_key": gemini_api_key,
                    "promoted_offerings": {
                        "brand_name": "EcoBean Coffee",
                        "brand_description": "Sustainable, organic coffee roasted in small batches",
                        "products": [
                            {
                                "name": "Morning Blend",
                                "description": "Smooth, medium roast with notes of chocolate and caramel"
                            }
                        ]
                    },
                    "output_mode": "manifest",
                    "finalize": True  # Finalize to get the full result
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
                    if "creative_manifest" in data:
                        print("\n✅ Creative manifest generated!")
                        manifest = data["creative_manifest"]
                        print(f"   Format: {manifest.get('format_id')}")
                        print(f"   Assets: {len(manifest.get('assets', []))} asset(s)")

                    if "context_id" in data:
                        print(f"\n🔄 Context ID for refinement: {data['context_id']}")

                    if "preview_url" in data:
                        print(f"\n🖼️  Preview URL: {data['preview_url']}")
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
    asyncio.run(test_build_creative())
