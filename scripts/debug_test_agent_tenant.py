#!/usr/bin/env python3
"""
Debug script to check test-agent.adcontextprotocol.org tenant configuration.

Usage:
    fly ssh console -a adcp-sales-agent
    python scripts/debug_test_agent_tenant.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant


def main():
    print("\n" + "=" * 80)
    print("🔍 Checking test-agent.adcontextprotocol.org tenant configuration")
    print("=" * 80 + "\n")

    with get_db_session() as session:
        # 1. Check all active tenants
        print("📋 All active tenants:")
        print("-" * 80)
        stmt = select(Tenant).where(Tenant.is_active).order_by(Tenant.subdomain)
        active_tenants = session.scalars(stmt).all()

        if not active_tenants:
            print("❌ No active tenants found!")
            return

        for tenant in active_tenants:
            print(f"\nTenant: {tenant.tenant_id}")
            print(f"  Subdomain: {tenant.subdomain}")
            print(f"  Virtual Host: {tenant.virtual_host or '(not set)'}")
            print(f"  Active: {tenant.is_active}")
            print(f"  Created: {tenant.created_at}")

        print("\n" + "-" * 80)
        print(f"Total active tenants: {len(active_tenants)}")

        # 2. Check specifically for test-agent virtual host
        print("\n" + "=" * 80)
        print("🎯 Looking for test-agent.adcontextprotocol.org...")
        print("=" * 80 + "\n")

        stmt = select(Tenant).filter_by(virtual_host="test-agent.adcontextprotocol.org", is_active=True)
        test_agent_tenant = session.scalars(stmt).first()

        if test_agent_tenant:
            print("✅ FOUND tenant with virtual_host='test-agent.adcontextprotocol.org'")
            print(f"   Tenant ID: {test_agent_tenant.tenant_id}")
            print(f"   Subdomain: {test_agent_tenant.subdomain}")
            print(f"   Virtual Host: {test_agent_tenant.virtual_host}")
        else:
            print("❌ NO tenant found with virtual_host='test-agent.adcontextprotocol.org'")

        # 3. Check for similar virtual hosts
        print("\n" + "=" * 80)
        print("🔎 Checking for similar virtual hosts...")
        print("=" * 80 + "\n")

        stmt = select(Tenant).where(Tenant.is_active, Tenant.virtual_host.isnot(None))
        tenants_with_vhost = session.scalars(stmt).all()

        if tenants_with_vhost:
            print("Tenants with virtual_host configured:")
            for tenant in tenants_with_vhost:
                match_indicator = (
                    "⭐ THIS ONE?"
                    if "test-agent" in tenant.virtual_host.lower() or "adcontextprotocol" in tenant.virtual_host.lower()
                    else ""
                )
                print(f"  - {tenant.subdomain}: {tenant.virtual_host} {match_indicator}")
        else:
            print("No tenants have virtual_host configured")

        # 4. Recommendations
        print("\n" + "=" * 80)
        print("💡 Recommendations")
        print("=" * 80 + "\n")

        if not test_agent_tenant:
            print("To fix the 'No tenant context' error:")
            print("1. Find the tenant that SHOULD be test-agent (check Admin UI at test-agent.adcontextprotocol.org)")
            print("2. Update that tenant's virtual_host:")
            print("   - Go to Admin UI → Tenant Settings → Account")
            print("   - Set Virtual Host to: test-agent.adcontextprotocol.org")
            print("\nOR run this SQL:")
            print("   UPDATE tenants SET virtual_host='test-agent.adcontextprotocol.org'")
            print("   WHERE subdomain='<correct-subdomain>';")
        else:
            print("✅ Configuration looks correct!")
            print("   If still seeing errors, check nginx/Approximated configuration.")


if __name__ == "__main__":
    main()
