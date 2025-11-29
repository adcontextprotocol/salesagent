#!/usr/bin/env python3
"""
Test A2A discovery endpoints without authentication using python-a2a library.

This verifies that list_creative_formats, list_authorized_properties, and get_products
work without requiring authentication tokens.

Usage:
    # Make sure A2A server is running on port 8091
    python scripts/test_a2a_discovery_no_auth.py
"""

import sys

from a2a import A2AClient
from a2a.types import DataPart, Message, Part


def test_list_creative_formats():
    """Test list_creative_formats without auth."""
    print("\n=== Testing list_creative_formats (no auth) ===")

    client = A2AClient("http://localhost:8091")

    # Create explicit skill invocation message
    message = Message(role="user", parts=[Part(root=DataPart(data={"skill": "list_creative_formats", "input": {}}))])

    try:
        response = client.send_message(message)
        print("✅ SUCCESS: list_creative_formats works without auth")
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_list_authorized_properties():
    """Test list_authorized_properties without auth."""
    print("\n=== Testing list_authorized_properties (no auth) ===")

    client = A2AClient("http://localhost:8091")

    message = Message(
        role="user", parts=[Part(root=DataPart(data={"skill": "list_authorized_properties", "input": {}}))]
    )

    try:
        response = client.send_message(message)
        print("✅ SUCCESS: list_authorized_properties works without auth")
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_get_products():
    """Test get_products without auth."""
    print("\n=== Testing get_products (no auth) ===")

    client = A2AClient("http://localhost:8091")

    message = Message(
        role="user", parts=[Part(root=DataPart(data={"skill": "get_products", "input": {"brief": "test campaign"}}))]
    )

    try:
        response = client.send_message(message)
        print("✅ SUCCESS: get_products works without auth")
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def test_create_media_buy_should_fail():
    """Test create_media_buy without auth (should fail)."""
    print("\n=== Testing create_media_buy (no auth - should fail) ===")

    client = A2AClient("http://localhost:8091")

    message = Message(
        role="user",
        parts=[Part(root=DataPart(data={"skill": "create_media_buy", "input": {"product_ids": ["prod_1"]}}))],
    )

    try:
        response = client.send_message(message)
        print(f"❌ UNEXPECTED: create_media_buy should require auth but succeeded: {response}")
        return False
    except Exception as e:
        if "Authentication" in str(e) or "authentication" in str(e):
            print("✅ SUCCESS: create_media_buy correctly requires auth")
            return True
        else:
            print(f"❌ FAILED with unexpected error: {e}")
            return False


def main() -> bool:
    """Run all tests and return True if all passed, False otherwise."""
    print("Testing A2A Discovery Endpoints Without Authentication")
    print("=" * 60)
    print("Using python-a2a library (standard A2AClient)")
    print()

    results = []
    results.append(("list_creative_formats", test_list_creative_formats()))
    results.append(("list_authorized_properties", test_list_authorized_properties()))
    results.append(("get_products", test_get_products()))
    results.append(("create_media_buy (should fail)", test_create_media_buy_should_fail()))

    print("\n" + "=" * 60)
    print("SUMMARY:")
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    all_passed = all(result[1] for result in results)
    print()
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")

    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test script error: {e}")
        print("\nMake sure the A2A server is running on http://localhost:8091")
        sys.exit(1)
