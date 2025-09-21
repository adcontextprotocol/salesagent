#!/usr/bin/env python3
"""Fix tenant virtual_host configuration."""

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant


def fix_wonderstruck_tenant():
    """Fix the virtual_host for the wonderstruck tenant."""
    with get_db_session() as session:
        tenant = session.query(Tenant).filter(Tenant.tenant_id == "tenant_wonderstruck").first()
        if tenant:
            print(f"Current tenant: {tenant.name}")
            print(f"Current subdomain: {tenant.subdomain}")
            print(f"Current virtual_host: {tenant.virtual_host}")

            # Update to correct virtual host
            tenant.virtual_host = "wonderstruck.sales-agent.scope3.com"
            session.commit()
            print(f"✅ Updated virtual_host to: {tenant.virtual_host}")
        else:
            print("❌ Tenant not found")


if __name__ == "__main__":
    fix_wonderstruck_tenant()
