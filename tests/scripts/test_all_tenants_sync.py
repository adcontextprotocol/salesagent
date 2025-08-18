#!/usr/bin/env python3
"""
Test script for syncing all tenants or a specific tenant like Scribd
"""

import os
import sys
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from db_config import get_db_connection


def get_superadmin_api_key():
    """Get the superadmin API key from the database"""
    conn = get_db_connection()
    cursor = conn.execute(
        """
        SELECT config_value
        FROM superadmin_config
        WHERE config_key = 'api_key'
    """
    )
    result = cursor.fetchone()
    conn.close()
    return result["config_value"] if result else None


def get_gam_tenants(tenant_filter=None):
    """Get all GAM-enabled tenants, optionally filtered by name"""
    conn = get_db_connection()
    query = """
        SELECT t.tenant_id, t.name, t.subdomain
        FROM tenants t
        JOIN adapter_config ac ON t.tenant_id = ac.tenant_id
        WHERE ac.adapter_type = 'google_ad_manager'
    """
    params = []

    if tenant_filter:
        query += " AND (LOWER(t.name) LIKE ? OR LOWER(t.subdomain) LIKE ?)"
        filter_lower = f"%{tenant_filter.lower()}%"
        params = [filter_lower, filter_lower]

    query += " ORDER BY t.name"

    cursor = conn.execute(query, params) if params else conn.execute(query)
    tenants = cursor.fetchall()
    conn.close()
    return tenants


def sync_tenant(api_key, base_url, tenant):
    """Sync a single tenant and return results"""
    tenant_id = tenant["tenant_id"]
    headers = {"X-API-Key": api_key}

    print(f"\n{'='*60}")
    print(f"🏢 Tenant: {tenant['name']} (ID: {tenant_id})")
    if tenant.get("subdomain"):
        print(f"   Subdomain: {tenant['subdomain']}")
    print(f"{'='*60}")

    # Check current status
    status_url = f"{base_url}/api/v1/sync/status/{tenant_id}"
    try:
        response = requests.get(status_url, headers=headers)
        if response.status_code == 200:
            status_data = response.json()
            print(f"📊 Current Status: {status_data.get('status', 'unknown')}")
            if status_data.get("last_sync"):
                last_sync = datetime.fromisoformat(status_data["last_sync"].replace("Z", "+00:00"))
                print(f"   Last sync: {last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
            if status_data.get("summary"):
                summary = status_data["summary"]
                print(
                    f"   Current inventory: {summary.get('ad_units', 0)} ad units, "
                    f"{summary.get('custom_targeting_keys', 0)} targeting keys"
                )
    except Exception as e:
        print(f"⚠️  Could not get current status: {e}")

    # Trigger sync
    print("\n🔄 Triggering sync...")
    trigger_url = f"{base_url}/api/v1/sync/trigger/{tenant_id}"

    try:
        response = requests.post(trigger_url, headers=headers, json={"sync_type": "incremental"})

        if response.status_code == 200:
            result = response.json()
            sync_id = result.get("sync_id")
            print(f"   ✅ Sync triggered! ID: {sync_id}")

            # Monitor progress
            print("   Monitoring progress...")
            max_wait = 60  # seconds
            start_time = time.time()

            while (time.time() - start_time) < max_wait:
                time.sleep(5)

                response = requests.get(status_url, headers=headers)
                if response.status_code == 200:
                    status_data = response.json()
                    current_status = status_data.get("status", "unknown")

                    if current_status == "completed":
                        print("   ✅ Sync completed!")
                        if status_data.get("summary"):
                            summary = status_data["summary"]
                            print(
                                f"   Results: {summary.get('ad_units', 0)} ad units, "
                                f"{summary.get('custom_targeting_keys', 0)} targeting keys, "
                                f"{summary.get('custom_targeting_values', 0)} targeting values"
                            )
                        return True
                    elif current_status == "failed":
                        print("   ❌ Sync failed!")
                        if status_data.get("error_message"):
                            print(f"   Error: {status_data['error_message']}")
                        return False
                    else:
                        elapsed = int(time.time() - start_time)
                        print(f"   ⏳ Still running... ({elapsed}s)", end="\r")

            print(f"\n   ⏰ Sync still running after {max_wait}s - check UI for results")
            return None

        else:
            print(f"   ❌ Failed to trigger sync: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Test sync for all tenants or specific tenant")
    parser.add_argument("--tenant", help="Filter by tenant name (e.g., scribd)")
    parser.add_argument("--all", action="store_true", help="Sync all tenants")
    args = parser.parse_args()

    # Get configuration
    api_key = get_superadmin_api_key()
    if not api_key:
        print("❌ No superadmin API key found. The server needs to be started at least once.")
        return

    # When running in Docker, use the admin-ui service name
    if os.path.exists("/.dockerenv"):
        # We're inside a Docker container
        api_port = os.environ.get("ADMIN_UI_PORT", 8003)
        base_url = f"http://admin-ui:{api_port}"
    else:
        api_port = os.environ.get("ADMIN_UI_PORT", 8001)
        base_url = f"http://localhost:{api_port}"

    print("🚀 AdCP Multi-Tenant Sync Test")
    print(f"🔧 Using API endpoint: {base_url}")
    print(f"🔑 API Key: {api_key[:8]}...")

    # Get tenants
    tenants = get_gam_tenants(args.tenant)
    if not tenants:
        if args.tenant:
            print(f"\n❌ No GAM-enabled tenants found matching '{args.tenant}'")
        else:
            print("\n❌ No GAM-enabled tenants found")
        return

    print(f"\n📋 Found {len(tenants)} GAM-enabled tenant(s):")
    for tenant in tenants:
        print(f"   - {tenant['name']} (ID: {tenant['tenant_id']})")

    # Confirm if multiple tenants
    if len(tenants) > 1 and not args.all:
        print("\n⚠️  Multiple tenants found. Use --all to sync all of them.")
        response = input("Continue with all tenants? (y/N): ")
        if response.lower() != "y":
            print("Aborted.")
            return

    # Sync each tenant
    results = {"success": 0, "failed": 0, "timeout": 0}

    for tenant in tenants:
        result = sync_tenant(api_key, base_url, tenant)
        if result is True:
            results["success"] += 1
        elif result is False:
            results["failed"] += 1
        else:
            results["timeout"] += 1

    # Summary
    print(f"\n{'='*60}")
    print("📊 Summary:")
    print(f"   ✅ Successful: {results['success']}")
    print(f"   ❌ Failed: {results['failed']}")
    print(f"   ⏰ Timed out: {results['timeout']}")
    print(f"   📋 Total: {len(tenants)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
