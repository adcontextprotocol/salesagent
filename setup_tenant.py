#!/usr/bin/env python3
"""
Simple CLI to set up a tenant for AdCP Sales Agent server.
Makes multi-tenant setup as easy as single-tenant.
"""

import json
import argparse
from datetime import datetime
import secrets
import sys
from db_config import get_db_connection, DatabaseConfig

def create_tenant(args):
    """Create a new tenant with sensible defaults."""
    
    # Generate defaults if not provided
    tenant_id = args.tenant_id or args.name.lower().replace(' ', '_')
    subdomain = args.subdomain or tenant_id
    
    # Default configuration based on adapter
    if args.adapter == "mock":
        config = {
            "adapters": {
                "mock": {
                    "enabled": True,
                    "dry_run": False
                }
            }
        }
    elif args.adapter == "google_ad_manager":
        config = {
            "adapters": {
                "google_ad_manager": {
                    "enabled": True,
                    "network_code": args.gam_network_code,
                    "company_id": args.gam_company_id,
                    "refresh_token": args.gam_refresh_token,
                    "manual_approval_required": args.manual_approval
                }
            }
        }
    elif args.adapter == "kevel":
        config = {
            "adapters": {
                "kevel": {
                    "enabled": True,
                    "network_id": args.kevel_network_id,
                    "api_key": args.kevel_api_key,
                    "manual_approval_required": args.manual_approval
                }
            }
        }
    
    # Add common configuration
    config.update({
        "creative_engine": {
            "auto_approve_formats": ["display_300x250", "display_728x90"],
            "human_review_required": not args.auto_approve_all
        },
        "features": {
            "max_daily_budget": args.max_daily_budget,
            "enable_aee_signals": True
        },
        "admin_token": args.admin_token or secrets.token_urlsafe(32)
    })
    
    # Create tenant record
    conn = get_db_connection()
    db_config = DatabaseConfig.get_db_config()
    
    # Check if tenant exists
    cursor = conn.execute("SELECT tenant_id FROM tenants WHERE tenant_id = ?", (tenant_id,))
    if cursor.fetchone():
        print(f"Error: Tenant '{tenant_id}' already exists")
        sys.exit(1)
    
    # Insert tenant
    conn.execute("""
        INSERT INTO tenants (
            tenant_id, name, subdomain, config, 
            created_at, updated_at, is_active, billing_plan
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tenant_id,
        args.name,
        subdomain,
        json.dumps(config),
        datetime.now().isoformat(),
        datetime.now().isoformat(),
        True if db_config['type'] == 'sqlite' else 1,
        "standard"
    ))
    
    # Create admin principal
    admin_token = secrets.token_urlsafe(32)
    conn.execute("""
        INSERT INTO principals (
            tenant_id, principal_id, name, 
            platform_mappings, access_token
        ) VALUES (?, ?, ?, ?, ?)
    """, (
        tenant_id,
        f"{tenant_id}_admin",
        f"{args.name} Admin",
        json.dumps({}),
        admin_token
    ))
    
    conn.connection.commit()
    conn.close()
    
    print(f"""
✅ Tenant created successfully!

Tenant ID: {tenant_id}
Name: {args.name}
Subdomain: {subdomain}

🌐 Access URL: http://{subdomain}.localhost:8080

🔑 Admin Token: {config['admin_token']}
   (Use this as x-adcp-auth header for admin operations)

🔑 Principal Token: {admin_token}
   (Use this for regular API operations)

📝 To update configuration:
   python manage_tenant.py update {tenant_id} --key "features.max_daily_budget" --value 50000

🚀 Start the server:
   python run_server.py
""")

def main():
    parser = argparse.ArgumentParser(description='Set up AdCP Sales Agent tenant')
    parser.add_argument('name', help='Tenant display name (e.g., "New York Times")')
    parser.add_argument('--tenant-id', help='Tenant ID (default: generated from name)')
    parser.add_argument('--subdomain', help='Subdomain (default: same as tenant ID)')
    parser.add_argument('--adapter', choices=['mock', 'google_ad_manager', 'kevel'], 
                       default='mock', help='Primary ad server adapter')
    
    # Adapter-specific options
    parser.add_argument('--gam-network-code', help='Google Ad Manager network code')
    parser.add_argument('--gam-company-id', help='Google Ad Manager company ID')
    parser.add_argument('--gam-refresh-token', help='Google Ad Manager OAuth refresh token')
    parser.add_argument('--kevel-network-id', help='Kevel network ID')
    parser.add_argument('--kevel-api-key', help='Kevel API key')
    
    # Common options
    parser.add_argument('--manual-approval', action='store_true', 
                       help='Require manual approval for operations')
    parser.add_argument('--auto-approve-all', action='store_true',
                       help='Auto-approve all creative formats')
    parser.add_argument('--max-daily-budget', type=int, default=10000,
                       help='Maximum daily budget (default: 10000)')
    parser.add_argument('--admin-token', help='Admin token (default: generated)')
    
    args = parser.parse_args()
    
    # Validate adapter-specific requirements
    if args.adapter == 'google_ad_manager':
        if not args.gam_network_code:
            parser.error("--gam-network-code required for Google Ad Manager")
        if not args.gam_refresh_token:
            parser.error("--gam-refresh-token required for Google Ad Manager (OAuth refresh token)")
    if args.adapter == 'kevel' and not args.kevel_network_id:
        parser.error("--kevel-network-id required for Kevel")
    
    create_tenant(args)

if __name__ == '__main__':
    main()