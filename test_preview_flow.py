#!/usr/bin/env python3
"""Test script to trace creative preview generation flow."""

import asyncio
import json

from src.core.creative_agent_registry import get_creative_agent_registry


async def test_preview_generation():
    """Test preview generation for a simple HTML creative."""

    registry = get_creative_agent_registry()

    # Test with a simple HTML display creative
    agent_url = "https://creative.adcontextprotocol.org"
    format_id = "display_336x280_html"

    # Minimal creative manifest for HTML format
    # Note: The manifest should NOT include format_id (it's a parameter to preview_creative)
    # Assets should be a dictionary with role keys per AdCP spec
    # The creative agent expects role name based on asset_type: "html_creative" for html assets
    creative_manifest = {
        "name": "Test HTML Creative",
        "assets": {
            "html_creative": {
                "asset_type": "html",
                "content": "<div style='width:336px;height:280px;background:#f0f0f0;display:flex;align-items:center;justify-content:center;font-family:Arial;'>Test Ad</div>",
            }
        },
    }

    print("🔍 Testing preview generation...")
    print(f"   Agent: {agent_url}")
    print(f"   Format: {format_id}")
    print(f"   Manifest: {json.dumps(creative_manifest, indent=2)}")
    print()

    try:
        preview_result = await registry.preview_creative(
            agent_url=agent_url, format_id=format_id, creative_manifest=creative_manifest
        )

        print("✅ Preview result received:")
        print(json.dumps(preview_result, indent=2))

        # Check for expected structure
        if preview_result and preview_result.get("previews"):
            print(f"\n✅ Found {len(preview_result['previews'])} preview variants")

            first_preview = preview_result["previews"][0]
            renders = first_preview.get("renders", [])

            if renders:
                first_render = renders[0]
                preview_url = first_render.get("preview_url")
                dimensions = first_render.get("dimensions", {})

                print(f"   Preview URL: {preview_url}")
                print(f"   Dimensions: {dimensions.get('width')}x{dimensions.get('height')}")
            else:
                print("⚠️  No renders in first preview")
        else:
            print("❌ No previews in result!")
            print(f"   Result keys: {list(preview_result.keys()) if preview_result else 'None'}")

    except Exception as e:
        print("❌ Error during preview generation:")
        print(f"   {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_preview_generation())
