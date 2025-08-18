#!/usr/bin/env python3
"""Test script for the super admin API."""

import os
import sys

import pytest
import requests

pytestmark = pytest.mark.integration


def test_superadmin_api(base_url=None):
    """Test the super admin API endpoints."""

    # Get base URL from environment or use default
    if not base_url:
        port = os.environ.get("ADMIN_UI_PORT", "8001")
        base_url = f"http://localhost:{port}"

    print("Super Admin API Test Script")
    print(f"Using base URL: {base_url}")
    print("=" * 50)

    # Step 1: Initialize API key (only works once)
    print("\n1. Initializing super admin API key...")
    try:
        resp = requests.post(f"{base_url}/api/v1/superadmin/init-api-key")
        if resp.status_code == 201:
            data = resp.json()
            api_key = data["api_key"]
            print(f"✓ API key created: {api_key}")
            print(f"⚠️  {data['warning']}")
        elif resp.status_code == 409:
            print("✓ API key already initialized")
            print("Please provide the API key as a command line argument:")
            print(f"  python {sys.argv[0]} <api_key>")
            if len(sys.argv) > 1:
                api_key = sys.argv[1]
                print(f"Using provided API key: {api_key[:10]}...")
            else:
                return
        else:
            print(f"✗ Failed to initialize API key: {resp.status_code} - {resp.text}")
            return
    except Exception as e:
        print(f"✗ Error: {e}")
        return

    # Set up headers with API key
    headers = {"X-Superadmin-API-Key": api_key, "Content-Type": "application/json"}

    # Step 2: Test health check
    print("\n2. Testing health check...")
    try:
        resp = requests.get(f"{base_url}/api/v1/superadmin/health", headers=headers)
        if resp.status_code == 200:
            print(f"✓ Health check passed: {resp.json()}")
        else:
            print(f"✗ Health check failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Step 3: List existing tenants
    print("\n3. Listing existing tenants...")
    try:
        resp = requests.get(f"{base_url}/api/v1/superadmin/tenants", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Found {data['count']} tenants:")
            for tenant in data["tenants"]:
                print(f"  - {tenant['name']} ({tenant['tenant_id']}) - {tenant['ad_server']}")
        else:
            print(f"✗ Failed to list tenants: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Step 4: Create a test tenant with GAM
    print("\n4. Creating a test tenant with Google Ad Manager...")
    tenant_data = {
        "name": "Test Publisher via API",
        "subdomain": "test-api-publisher",
        "ad_server": "google_ad_manager",
        "gam_network_code": "123456789",
        "gam_refresh_token": "test_refresh_token_here",
        "authorized_emails": ["test@example.com"],
        "authorized_domains": ["example.com"],
    }

    try:
        resp = requests.post(f"{base_url}/api/v1/superadmin/tenants", headers=headers, json=tenant_data)
        if resp.status_code == 201:
            created_tenant = resp.json()
            tenant_id = created_tenant["tenant_id"]
            print(f"✓ Created tenant: {created_tenant['name']} ({tenant_id})")
            print(f"  Admin token: {created_tenant['admin_token']}")
            print(f"  Admin UI URL: {created_tenant['admin_ui_url']}")
            if "default_principal_token" in created_tenant:
                print(f"  Default principal token: {created_tenant['default_principal_token']}")
        else:
            print(f"✗ Failed to create tenant: {resp.status_code} - {resp.text}")
            # Try to get existing tenant ID for further tests
            resp = requests.get(f"{base_url}/api/v1/superadmin/tenants", headers=headers)
            if resp.status_code == 200 and resp.json()["count"] > 0:
                tenant_id = resp.json()["tenants"][0]["tenant_id"]
            else:
                return
    except Exception as e:
        print(f"✗ Error: {e}")
        return

    # Step 5: Get tenant details
    print(f"\n5. Getting details for tenant {tenant_id}...")
    try:
        resp = requests.get(f"{base_url}/api/v1/superadmin/tenants/{tenant_id}", headers=headers)
        if resp.status_code == 200:
            tenant_details = resp.json()
            print("✓ Tenant details:")
            print(f"  Name: {tenant_details['name']}")
            print(f"  Subdomain: {tenant_details['subdomain']}")
            print(f"  Ad Server: {tenant_details['ad_server']}")
            if "adapter_config" in tenant_details:
                print("  Adapter configured: Yes")
                if tenant_details["ad_server"] == "google_ad_manager":
                    print(f"    GAM Network: {tenant_details['adapter_config'].get('gam_network_code')}")
                    print(f"    Has refresh token: {tenant_details['adapter_config'].get('has_refresh_token')}")
        else:
            print(f"✗ Failed to get tenant details: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Step 6: Update tenant
    print(f"\n6. Updating tenant {tenant_id}...")
    update_data = {
        "billing_plan": "premium",
        "max_daily_budget": 50000,
        "adapter_config": {"gam_company_id": "test_company_123", "gam_trafficker_id": "test_trafficker_456"},
    }

    try:
        resp = requests.put(f"{base_url}/api/v1/superadmin/tenants/{tenant_id}", headers=headers, json=update_data)
        if resp.status_code == 200:
            print("✓ Tenant updated successfully")
        else:
            print(f"✗ Failed to update tenant: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Step 7: Demonstrate OAuth flow integration
    print("\n7. OAuth Flow Integration Example:")
    print("   In your Scope3 app:")
    print("   1. User clicks 'Add AdCP Media Agent' → 'Set one up for me' → 'GAM'")
    print("   2. OAuth button triggers GAM OAuth flow")
    print("   3. On successful OAuth, get refresh token")
    print("   4. Call POST /api/v1/superadmin/tenants with:")
    print("      - gam_refresh_token: <oauth_refresh_token>")
    print("      - gam_network_code: <from_oauth_or_user_input>")
    print("   5. Redirect user to the admin_ui_url returned in response")

    print("\n" + "=" * 50)
    print("Test completed!")


if __name__ == "__main__":
    test_superadmin_api()
