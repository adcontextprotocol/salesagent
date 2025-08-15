#!/usr/bin/env python3
"""
Test script for the Sync API
Demonstrates how to use the API without UI interaction
"""

import os
import sys
import time
import json
import requests
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_config import get_db_connection

def get_superadmin_api_key():
    """Get the superadmin API key from the database"""
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT config_value 
        FROM superadmin_config 
        WHERE config_key = 'api_key'
    """)
    result = cursor.fetchone()
    conn.close()
    return result['config_value'] if result else None

def get_gam_tenants():
    """Get all GAM-enabled tenants"""
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT t.tenant_id, t.name 
        FROM tenants t
        JOIN adapter_config ac ON t.tenant_id = ac.tenant_id
        WHERE ac.adapter_type = 'google_ad_manager'
        ORDER BY t.name
    """)
    tenants = cursor.fetchall()
    conn.close()
    return tenants

def test_sync_api():
    """Test the sync API endpoints"""
    # Get configuration
    api_key = get_superadmin_api_key()
    if not api_key:
        print("❌ No superadmin API key found. The server needs to be started at least once.")
        return
    
    api_port = os.environ.get('ADMIN_UI_PORT', 8001)
    base_url = f"http://localhost:{api_port}"
    
    print(f"🔧 Using API endpoint: {base_url}")
    print(f"🔑 API Key: {api_key[:8]}...")
    print()
    
    # Get GAM tenants
    tenants = get_gam_tenants()
    if not tenants:
        print("❌ No GAM-enabled tenants found")
        return
        
    print(f"📋 Found {len(tenants)} GAM-enabled tenant(s):")
    for tenant in tenants:
        print(f"   - {tenant['name']} (ID: {tenant['tenant_id']})")
    print()
    
    # Test with the first tenant
    test_tenant = tenants[0]
    tenant_id = test_tenant['tenant_id']
    print(f"🧪 Testing with tenant: {test_tenant['name']}")
    print()
    
    # 1. Check current sync status
    print("1️⃣ Checking current sync status...")
    status_url = f"{base_url}/api/v1/sync/status/{tenant_id}"
    headers = {'X-API-Key': api_key}
    
    try:
        response = requests.get(status_url, headers=headers)
        if response.status_code == 200:
            status_data = response.json()
            print(f"   Status: {status_data.get('status', 'unknown')}")
            if status_data.get('last_sync'):
                last_sync = datetime.fromisoformat(status_data['last_sync'].replace('Z', '+00:00'))
                print(f"   Last sync: {last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
            if status_data.get('summary'):
                summary = status_data['summary']
                print(f"   Summary: {summary.get('ad_units', 0)} ad units, "
                      f"{summary.get('custom_targeting_keys', 0)} targeting keys")
        else:
            print(f"   ❌ Failed to get status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    print()
    
    # 2. Trigger a new sync
    print("2️⃣ Triggering a new sync...")
    trigger_url = f"{base_url}/api/v1/sync/trigger/{tenant_id}"
    
    try:
        response = requests.post(
            trigger_url, 
            headers=headers,
            json={'sync_type': 'incremental'}  # Use incremental for faster testing
        )
        
        if response.status_code == 200:
            result = response.json()
            sync_id = result.get('sync_id')
            print(f"   ✅ Sync triggered successfully!")
            print(f"   Sync ID: {sync_id}")
            print(f"   Status: {result.get('status')}")
        else:
            print(f"   ❌ Failed to trigger sync: {response.status_code}")
            print(f"   Response: {response.text}")
            return
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    print()
    
    # 3. Poll for completion
    print("3️⃣ Monitoring sync progress...")
    max_attempts = 30  # Max 5 minutes
    attempt = 0
    
    while attempt < max_attempts:
        time.sleep(10)  # Check every 10 seconds
        attempt += 1
        
        try:
            response = requests.get(status_url, headers=headers)
            if response.status_code == 200:
                status_data = response.json()
                current_status = status_data.get('status', 'unknown')
                
                print(f"   [{attempt:02d}] Status: {current_status}", end='')
                
                if current_status == 'running':
                    print(" ⏳")
                elif current_status == 'completed':
                    print(" ✅")
                    if status_data.get('summary'):
                        summary = status_data['summary']
                        print(f"   Summary: {summary.get('ad_units', 0)} ad units, "
                              f"{summary.get('custom_targeting_keys', 0)} targeting keys, "
                              f"{summary.get('custom_targeting_values', 0)} targeting values")
                    break
                elif current_status == 'failed':
                    print(" ❌")
                    if status_data.get('error_message'):
                        print(f"   Error: {status_data['error_message']}")
                    break
                else:
                    print(f" ❓")
            else:
                print(f"   ❌ Failed to check status: {response.status_code}")
                break
                
        except Exception as e:
            print(f"   ❌ Error checking status: {e}")
            break
    
    if attempt >= max_attempts:
        print("   ⏰ Timeout - sync is taking longer than expected")
    
    print()
    print("✅ Test complete!")
    
    # 4. Show all recent syncs
    print()
    print("4️⃣ Recent sync history:")
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT sync_id, sync_type, status, started_at, completed_at,
               summary, error_message
        FROM sync_jobs
        WHERE tenant_id = ?
        ORDER BY started_at DESC
        LIMIT 5
    """, (tenant_id,))
    
    syncs = cursor.fetchall()
    conn.close()
    
    for sync in syncs:
        started = datetime.fromisoformat(sync['started_at'])
        print(f"\n   Sync {sync['sync_id'][:8]}...")
        print(f"   Type: {sync['sync_type']}, Status: {sync['status']}")
        print(f"   Started: {started.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if sync['completed_at']:
            completed = datetime.fromisoformat(sync['completed_at'])
            duration = (completed - started).total_seconds()
            print(f"   Duration: {duration:.1f} seconds")
        
        if sync['summary']:
            summary = json.loads(sync['summary'])
            print(f"   Results: {summary.get('ad_units', 0)} ad units, "
                  f"{summary.get('custom_targeting_keys', 0)} keys")
        
        if sync['error_message']:
            print(f"   Error: {sync['error_message']}")

if __name__ == "__main__":
    print("🚀 AdCP Sync API Test Script")
    print("=" * 50)
    test_sync_api()