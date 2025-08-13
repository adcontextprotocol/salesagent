#!/usr/bin/env python3
"""Quick script to get tokens from the database."""

from db_config import get_db_connection
import json

def get_tokens():
    conn = get_db_connection()
    
    print("\n🔑 TENANT TOKENS\n" + "="*50)
    
    # Get tenants
    cursor = conn.execute("""
        SELECT tenant_id, name, subdomain, config 
        FROM tenants 
        WHERE is_active = ?
    """, (True,))
    
    for row in cursor.fetchall():
        tenant_id, name, subdomain, config = row
        if isinstance(config, str):
            config = json.loads(config)
        
        print(f"\n📍 Tenant: {name}")
        print(f"   ID: {tenant_id}")
        print(f"   URL: http://{subdomain}.localhost:8080")
        admin_token = config.get('admin_token', 'Not found')
        print(f"   Admin Token: {admin_token}")
        
        # Get principals for this tenant
        pcursor = conn.execute("""
            SELECT principal_id, name, access_token 
            FROM principals 
            WHERE tenant_id = ?
        """, (tenant_id,))
        
        print(f"\n   Principals:")
        for prow in pcursor.fetchall():
            pid, pname, token = prow
            print(f"   - {pname}: {token}")
    
    conn.close()
    
    print("\n\n💡 Example API calls:")
    print("   curl -H \"x-adcp-auth: [TOKEN]\" http://localhost:8080/mcp/tools/get_products")
    print("\n")

if __name__ == "__main__":
    get_tokens()