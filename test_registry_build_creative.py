"""Test CreativeAgentRegistry.build_creative method."""

import asyncio
import os
from src.core.creative_agent_registry import get_creative_agent_registry


async def test_registry_build_creative():
    """Test the build_creative method via CreativeAgentRegistry."""

    # Get Gemini API key from environment
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("❌ GEMINI_API_KEY environment variable not set")
        return

    print("🔗 Testing CreativeAgentRegistry.build_creative()")
    print("=" * 60)

    # Get registry instance
    registry = get_creative_agent_registry()

    # Test build_creative
    agent_url = "https://creative.adcontextprotocol.org"
    format_id = "display_300x250_generative"

    print(f"\nCalling build_creative:")
    print(f"  Agent: {agent_url}")
    print(f"  Format: {format_id}")
    print(f"  Message: Create ad for sustainable coffee brand")
    print()

    try:
        result = await registry.build_creative(
            agent_url=agent_url,
            format_id=format_id,
            message="Create a display ad for EcoBean Coffee - a sustainable coffee brand. Use green tones and modern design.",
            gemini_api_key=gemini_api_key,
            promoted_offerings={
                "brand_name": "EcoBean Coffee",
                "brand_description": "Sustainable, organic coffee roasted in small batches",
                "products": [
                    {
                        "name": "Morning Blend",
                        "description": "Smooth, medium roast with notes of chocolate and caramel"
                    }
                ]
            },
            finalize=True
        )

        print("✅ SUCCESS!")
        print("=" * 60)
        print(f"\nStatus: {result.get('status')}")
        print(f"Message: {result.get('message')}")
        print(f"Context ID: {result.get('context_id')}")

        creative_output = result.get('creative_output', {})
        if creative_output:
            print(f"\nCreative Output:")
            print(f"  Type: {creative_output.get('type')}")
            print(f"  Format ID: {creative_output.get('format_id')}")

            data = creative_output.get('data', {})
            if data:
                print(f"  Output Format: {data.get('format_id')}")
                assets = data.get('assets', {})
                print(f"  Assets: {list(assets.keys())}")

                # Check if we got an image
                for asset_name, asset_data in assets.items():
                    asset_type = asset_data.get('asset_type')
                    url = asset_data.get('url', '')
                    print(f"    {asset_name}: {asset_type}")
                    if url.startswith('data:image'):
                        print(f"      ✅ Generated image (base64 data URI)")
                    else:
                        print(f"      URL: {url[:100]}...")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_registry_build_creative())
