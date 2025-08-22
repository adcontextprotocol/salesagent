# \!/usr/bin/env python3
"""
Simple test of ADK agent to verify it loads and functions are callable.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_adk_import():
    """Test that the ADK agent can be imported."""
    print("Testing ADK agent import...")
    try:
        from src.adk.adcp_agent.agent import root_agent

        print(f"✅ Successfully imported root_agent: {root_agent.name}")
        print(f"   Model: {root_agent.model}")
        print(f"   Tools: {len(root_agent.tools)} tools available")
        for tool in root_agent.tools:
            print(f"   - {tool.name if hasattr(tool, 'name') else tool}")
        return True
    except Exception as e:
        print(f"❌ Failed to import: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_function_definitions():
    """Test that the AdCP functions are defined."""
    print("\nTesting function definitions...")
    try:
        from src.adk.adcp_agent.agent import (
            add_creative_assets,
            check_media_buy_status,
            create_media_buy,
            get_products,
            get_signals,
        )

        functions = [
            ("get_products", get_products),
            ("create_media_buy", create_media_buy),
            ("check_media_buy_status", check_media_buy_status),
            ("get_signals", get_signals),
            ("add_creative_assets", add_creative_assets),
        ]

        for name, func in functions:
            print(f"✅ {name}: {func.__doc__.strip().split('.')[0] if func.__doc__ else 'Defined'}")

        return True
    except Exception as e:
        print(f"❌ Failed to import functions: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("ADK Agent Simple Test")
    print("=" * 60)

    success = True
    success = test_adk_import() and success
    success = test_function_definitions() and success

    print("\n" + "=" * 60)
    if success:
        print(r"✅ All tests passed\! ADK agent is properly configured.")
    else:
        print("❌ Some tests failed. Check the errors above.")

    sys.exit(0 if success else 1)
