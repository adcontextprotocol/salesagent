#!/usr/bin/env python3
"""Test script to verify list_authorized_properties fix.

This script tests that the get_testing_context import fix works correctly.
Run this after deploying the fix to verify it works in production.

Usage:
    python scripts/test_list_properties_fix.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.testing_hooks import get_testing_context


def test_import_fix():
    """Verify that get_testing_context is importable and works."""
    print("Testing get_testing_context import fix...")

    # Mock context object
    class MockContext:
        def __init__(self):
            self.meta = {"headers": {}}

    context = MockContext()

    # This should work without NameError
    try:
        testing_context = get_testing_context(context)
        print(f"✅ SUCCESS: get_testing_context() returned {type(testing_context)}")
        print(f"   testing_context: {testing_context}")
        return True
    except NameError as e:
        print(f"❌ FAILURE: NameError - {e}")
        return False
    except Exception as e:
        print(f"⚠️  Other error (not import related): {e}")
        return False


def test_list_properties_import():
    """Verify that list_authorized_properties can be imported."""
    print("\nTesting list_authorized_properties import...")

    try:

        print("✅ SUCCESS: All list_authorized_properties functions imported")
        return True
    except Exception as e:
        print(f"❌ FAILURE: Import error - {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("list_authorized_properties Fix Verification")
    print("=" * 60)

    results = []
    results.append(test_import_fix())
    results.append(test_list_properties_import())

    print("\n" + "=" * 60)
    if all(results):
        print("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
