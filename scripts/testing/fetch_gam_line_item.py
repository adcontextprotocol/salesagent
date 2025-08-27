#!/usr/bin/env python3
"""Test script to fetch GAM line item data."""

import json

import requests

# Configuration
BASE_URL = "http://localhost:8014"
TENANT_ID = "tenant_demo_1"
LINE_ITEM_ID = "7047822666"


def main():
    # First, we need to authenticate
    # For testing, we'll use test authentication mode if available
    # or try to get a session through the API

    session = requests.Session()

    # Try to authenticate (this would normally require OAuth)
    # For now, let's try accessing the endpoint directly
    # In production, you'd need proper authentication

    url = f"{BASE_URL}/api/tenant/{TENANT_ID}/gam/line-item/{LINE_ITEM_ID}"

    print(f"Fetching line item {LINE_ITEM_ID} from tenant {TENANT_ID}...")
    print(f"URL: {url}")
    print()

    try:
        # Try without auth first (might work if test mode is enabled)
        response = session.get(url)

        if response.status_code == 401 or response.status_code == 302:
            print("Authentication required. Please ensure you're logged in to the Admin UI.")
            print("Visit http://localhost:8014 and login first.")
            return

        if response.status_code == 200:
            data = response.json()

            print("=== LINE ITEM DATA ===")
            print(json.dumps(data, indent=2))

            # Save to file for easier viewing
            with open(f"line_item_{LINE_ITEM_ID}.json", "w") as f:
                json.dump(data, f, indent=2)
            print(f"\nFull response saved to line_item_{LINE_ITEM_ID}.json")

            # Show summary
            if "line_item" in data:
                li = data["line_item"]
                print("\n=== SUMMARY ===")
                print(f"Line Item ID: {li.get('id')}")
                print(f"Name: {li.get('name')}")
                print(f"Status: {li.get('status')}")
                print(f"Type: {li.get('lineItemType')}")
                print(f"Order ID: {li.get('orderId')}")

            if "media_product_json" in data:
                print("\n=== MEDIA PRODUCT JSON ===")
                print(json.dumps(data["media_product_json"], indent=2))

        else:
            print(f"Error: HTTP {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
