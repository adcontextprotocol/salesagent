#!/usr/bin/env python3
"""Quick script to get tokens from the database."""

from src.core.database.database_session import get_db_session
from src.core.database.models import Principal, Tenant


def get_tokens():
    with get_db_session() as session:
        print("\n🔑 TENANT TOKENS\n" + "=" * 50)

        # Get tenants
        tenants = session.query(Tenant).filter(Tenant.is_active).all()

        for tenant in tenants:
            print(f"\n📍 Tenant: {tenant.name}")
            print(f"   ID: {tenant.tenant_id}")
            print(f"   URL: http://{tenant.subdomain}.localhost:8080")
            admin_token = tenant.admin_token or "Not found"
            print(f"   Admin Token: {admin_token}")

            # Get principals for this tenant
            principals = session.query(Principal).filter(Principal.tenant_id == tenant.tenant_id).all()

            print("\n   Principals:")
            for principal in principals:
                print(f"   - {principal.name}: {principal.access_token}")

        print("\n\n💡 Example API calls:")
        print('   curl -H "x-adcp-auth: [TOKEN]" http://localhost:8080/mcp/tools/get_products')
        print("\n")


if __name__ == "__main__":
    get_tokens()
