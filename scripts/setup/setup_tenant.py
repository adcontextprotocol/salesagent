#!/usr/bin/env python3
"""
Simple CLI to set up a tenant for AdCP Sales Agent server.
Makes multi-tenant setup as easy as single-tenant.
"""

import argparse
import secrets
import sys

from src.core.database.database_session import get_db_session
from src.core.database.models import AdapterConfig, Tenant


def create_tenant(args):
    """Create a new tenant with sensible defaults."""

    # Generate defaults if not provided
    tenant_id = args.tenant_id or args.name.lower().replace(" ", "_")
    subdomain = args.subdomain or tenant_id

    # Extract configuration values
    auto_approve_formats = ["display_300x250", "display_728x90"]
    human_review_required = not args.auto_approve_all
    max_daily_budget = args.max_daily_budget
    admin_token = args.admin_token or secrets.token_urlsafe(32)

    # Policy settings
    policy_settings = {
        "enabled": True,
        "require_manual_review": False,
        "prohibited_advertisers": [],
        "prohibited_categories": [],
        "prohibited_tactics": [],
    }

    with get_db_session() as session:
        # Check if tenant exists
        existing = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if existing:
            print(f"Error: Tenant '{tenant_id}' already exists")
            sys.exit(1)

        # Create tenant with new schema
        tenant = Tenant(
            tenant_id=tenant_id,
            name=args.name,
            subdomain=subdomain,
            ad_server=args.adapter,
            max_daily_budget=max_daily_budget,
            enable_aee_signals=True,
            admin_token=admin_token,
            auto_approve_formats=auto_approve_formats,
            human_review_required=human_review_required,
            policy_settings=policy_settings,
            is_active=True,
            billing_plan="standard",
        )
        session.add(tenant)

        # Insert adapter configuration based on adapter type
        if args.adapter == "google_ad_manager":
            adapter_config = AdapterConfig(
                tenant_id=tenant_id,
                adapter_type="google_ad_manager",
                gam_network_code=args.gam_network_code,
                gam_refresh_token=args.gam_refresh_token,
                gam_manual_approval_required=args.manual_approval,
            )
            session.add(adapter_config)
        elif args.adapter == "kevel":
            adapter_config = AdapterConfig(
                tenant_id=tenant_id,
                adapter_type="kevel",
                kevel_network_id=args.kevel_network_id,
                kevel_api_key=args.kevel_api_key,
                kevel_manual_approval_required=args.manual_approval,
            )
            session.add(adapter_config)
        elif args.adapter == "mock":
            adapter_config = AdapterConfig(tenant_id=tenant_id, adapter_type="mock", mock_dry_run=False)
            session.add(adapter_config)

        session.commit()

    print(
        f"""
✅ Tenant (Publisher) created successfully!

Publisher: {args.name}
Tenant ID: {tenant_id}
Subdomain: {subdomain}

🌐 Admin UI: http://localhost:8001
   (Login with your Google account to manage this publisher)

📝 Next Steps:
1. Access the Admin UI to complete setup
2. Configure your ad server integration (if not done)
3. Create principals for each advertiser who will buy inventory
4. Share API tokens with advertisers to access the MCP API

💡 Remember: Principals represent advertisers, not the publisher.
   Each advertiser gets their own principal with unique API access.

📝 To update configuration:
   python manage_tenant.py update {tenant_id} --key "features.max_daily_budget" --value 50000

🚀 Start the server:
   python scripts/run_server.py
"""
    )


def main():
    parser = argparse.ArgumentParser(description="Set up AdCP Sales Agent tenant")
    parser.add_argument("name", help='Tenant display name (e.g., "New York Times")')
    parser.add_argument("--tenant-id", help="Tenant ID (default: generated from name)")
    parser.add_argument("--subdomain", help="Subdomain (default: same as tenant ID)")
    parser.add_argument(
        "--adapter", choices=["mock", "google_ad_manager", "kevel"], default="mock", help="Primary ad server adapter"
    )

    # Adapter-specific options
    parser.add_argument(
        "--gam-network-code",
        help="Google Ad Manager network code (optional - will be auto-detected from refresh token)",
    )
    parser.add_argument(
        "--gam-refresh-token", help="Google Ad Manager OAuth refresh token (advertisers are now selected per principal)"
    )
    parser.add_argument("--kevel-network-id", help="Kevel network ID")
    parser.add_argument("--kevel-api-key", help="Kevel API key")

    # Common options
    parser.add_argument("--manual-approval", action="store_true", help="Require manual approval for operations")
    parser.add_argument("--auto-approve-all", action="store_true", help="Auto-approve all creative formats")
    parser.add_argument("--max-daily-budget", type=int, default=10000, help="Maximum daily budget (default: 10000)")
    parser.add_argument("--admin-token", help="Admin token (default: generated)")

    args = parser.parse_args()

    # Validate adapter-specific requirements
    if args.adapter == "google_ad_manager":
        # Network code is optional - can be auto-detected from refresh token
        if not args.gam_refresh_token:
            print("Warning: No refresh token provided for Google Ad Manager.")
            print("You'll need to configure GAM credentials through the Admin UI.")
    if args.adapter == "kevel" and not args.kevel_network_id:
        parser.error("--kevel-network-id required for Kevel")

    create_tenant(args)


if __name__ == "__main__":
    main()
