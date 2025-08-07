#!/usr/bin/env python3
"""
Quick script to check all tenants and their adapter configurations
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_config import get_db_connection

def check_all_tenants():
    """List all tenants and their configurations"""
    conn = get_db_connection()
    
    # Get all tenants
    cursor = conn.execute("""
        SELECT t.tenant_id, t.name, t.subdomain, t.ad_server,
               ac.adapter_type, ac.gam_network_code
        FROM tenants t
        LEFT JOIN adapter_config ac ON t.tenant_id = ac.tenant_id
        ORDER BY t.name
    """)
    
    tenants = cursor.fetchall()
    conn.close()
    
    print("📋 All Tenants in Database:")
    print("=" * 80)
    
    for tenant in tenants:
        print(f"\nTenant: {tenant['name']}")
        print(f"  ID: {tenant['tenant_id']}")
        print(f"  Subdomain: {tenant['subdomain'] or 'None'}")
        print(f"  Ad Server: {tenant['ad_server'] or 'None configured'}")
        if tenant['adapter_type']:
            print(f"  Adapter: {tenant['adapter_type']}")
            if tenant['gam_network_code']:
                print(f"  GAM Network Code: {tenant['gam_network_code']}")
    
    print("\n" + "=" * 80)
    print(f"Total tenants: {len(tenants)}")
    
    # Check for sync status
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT s.tenant_id, t.name, s.status, s.started_at, s.completed_at, s.summary
        FROM sync_jobs s
        JOIN tenants t ON s.tenant_id = t.tenant_id
        WHERE s.sync_id IN (
            SELECT MAX(sync_id) 
            FROM sync_jobs 
            GROUP BY tenant_id
        )
        ORDER BY s.started_at DESC
    """)
    
    syncs = cursor.fetchall()
    conn.close()
    
    if syncs:
        print("\n📊 Latest Sync Status:")
        print("=" * 80)
        for sync in syncs:
            print(f"\n{sync['name']}:")
            print(f"  Status: {sync['status']}")
            print(f"  Started: {sync['started_at']}")
            if sync['completed_at']:
                print(f"  Completed: {sync['completed_at']}")
            if sync['summary']:
                import json
                summary = json.loads(sync['summary'])
                print(f"  Inventory: {summary.get('ad_units', 0)} ad units, "
                      f"{summary.get('custom_targeting_keys', 0)} targeting keys")

if __name__ == "__main__":
    check_all_tenants()