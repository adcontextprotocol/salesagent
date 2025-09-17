#!/usr/bin/env python3
"""
Production setup script for AdCP Sales Agent.
Sets up Scribd and Wonderstruck tenants with proper configuration.
"""

import sys

from src.core.database.database_session import get_db_session
from src.core.database.models import Principal, Product, Tenant


def verify_tenant_setup():
    """Verify both tenants are properly configured."""

    print("🔍 Verifying tenant configuration...")

    with get_db_session() as session:
        # Check Scribd
        scribd = session.query(Tenant).filter_by(subdomain="scribd").first()
        if not scribd:
            print("❌ Scribd tenant not found!")
            return False

        scribd_principals = session.query(Principal).filter_by(tenant_id=scribd.tenant_id).all()
        scribd_products = session.query(Product).filter_by(tenant_id=scribd.tenant_id).all()

        print(f"✅ Scribd: {len(scribd_principals)} principals, {len(scribd_products)} products")

        # Check Wonderstruck
        wonderstruck = session.query(Tenant).filter_by(subdomain="wonderstruck").first()
        if not wonderstruck:
            print("❌ Wonderstruck tenant not found!")
            return False

        wonderstruck_principals = session.query(Principal).filter_by(tenant_id=wonderstruck.tenant_id).all()
        wonderstruck_products = session.query(Product).filter_by(tenant_id=wonderstruck.tenant_id).all()

        print(f"✅ Wonderstruck: {len(wonderstruck_principals)} principals, {len(wonderstruck_products)} products")

        # Verify key configurations
        issues = []

        if scribd.subdomain == "localhost":
            issues.append("Scribd still using 'localhost' subdomain (should be 'scribd')")

        if wonderstruck.subdomain == "localhost":
            issues.append("Wonderstruck still using 'localhost' subdomain (should be 'wonderstruck')")

        if len(scribd_products) == 0:
            issues.append("Scribd has no products configured")

        if len(wonderstruck_products) == 0:
            issues.append("Wonderstruck has no products configured")

        if issues:
            print("⚠️  Issues found:")
            for issue in issues:
                print(f"   - {issue}")
            return False

        return True


def setup_missing_scribd_products():
    """Set up products for Scribd if missing."""

    with get_db_session() as session:
        scribd_products = session.query(Product).filter_by(tenant_id="tenant_scribd").all()

        if len(scribd_products) > 0:
            print(f"✅ Scribd already has {len(scribd_products)} products")
            return True

        print("🔧 Setting up Scribd products...")

        # Import the setup script
        from scripts.setup_scribd_products import setup_scribd_products

        setup_scribd_products()

        return True


def get_tenant_access_tokens():
    """Get access tokens for both tenants."""

    print("🔑 Getting access tokens...")

    with get_db_session() as session:
        scribd = session.query(Tenant).filter_by(subdomain="scribd").first()
        wonderstruck = session.query(Tenant).filter_by(subdomain="wonderstruck").first()

        scribd_principals = session.query(Principal).filter_by(tenant_id=scribd.tenant_id).all()
        wonderstruck_principals = session.query(Principal).filter_by(tenant_id=wonderstruck.tenant_id).all()

        print("\\n📊 SCRIBD ACCESS TOKENS:")
        print(f"   Tenant ID: {scribd.tenant_id}")
        print(f"   Admin Token: {scribd.admin_token}")
        for principal in scribd_principals:
            print(f"   Principal '{principal.name}': {principal.access_token}")

        print("\\n📊 WONDERSTRUCK ACCESS TOKENS:")
        print(f"   Tenant ID: {wonderstruck.tenant_id}")
        print(f"   Admin Token: {wonderstruck.admin_token}")
        for principal in wonderstruck_principals:
            print(f"   Principal '{principal.name}': {principal.access_token}")

        return {
            "scribd": {
                "tenant_id": scribd.tenant_id,
                "admin_token": scribd.admin_token,
                "principals": [(p.name, p.access_token) for p in scribd_principals],
            },
            "wonderstruck": {
                "tenant_id": wonderstruck.tenant_id,
                "admin_token": wonderstruck.admin_token,
                "principals": [(p.name, p.access_token) for p in wonderstruck_principals],
            },
        }


def main():
    """Main setup function."""

    print("🚀 AdCP Sales Agent - Production Setup")
    print("======================================")

    # Step 1: Verify current setup
    if not verify_tenant_setup():
        print("❌ Tenant verification failed!")
        sys.exit(1)

    # Step 2: Set up missing Scribd products
    if not setup_missing_scribd_products():
        print("❌ Failed to set up Scribd products!")
        sys.exit(1)

    # Step 3: Get access tokens
    tokens = get_tenant_access_tokens()

    print("\\n✅ Production setup complete!")
    print("\\n📋 Next Steps:")
    print("   1. Update DNS for sales-agent.scope3.com")
    print("   2. Set up Fly.io certificates")
    print("   3. Run regression tests")
    print("   4. Deploy latest code")

    print("\\n🔧 Test Commands:")
    print("   # Test Scribd")
    scribd_token = (
        tokens["scribd"]["principals"][0][1] if tokens["scribd"]["principals"] else tokens["scribd"]["admin_token"]
    )
    print(
        f'   curl -H "x-adcp-auth: {scribd_token}" -H "x-adcp-tenant: scribd" https://adcp-sales-agent.fly.dev/mcp/tools/get_products'
    )

    print("   # Test Wonderstruck")
    wonderstruck_token = (
        tokens["wonderstruck"]["principals"][0][1]
        if tokens["wonderstruck"]["principals"]
        else tokens["wonderstruck"]["admin_token"]
    )
    print(
        f'   curl -H "x-adcp-auth: {wonderstruck_token}" -H "x-adcp-tenant: wonderstruck" https://adcp-sales-agent.fly.dev/mcp/tools/get_products'
    )


if __name__ == "__main__":
    main()
