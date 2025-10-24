#!/usr/bin/env python3
"""Show detailed platform mappings for all principals in a tenant."""

import json
import sys

from src.core.database.database_session import get_db_session
from src.core.database.models import Principal, Tenant


def show_mappings(tenant_name=None):
    with get_db_session() as session:
        if tenant_name:
            tenant = session.query(Tenant).filter_by(name=tenant_name).first()
            if not tenant:
                print(f"Tenant '{tenant_name}' not found")
                return
            principals = session.query(Principal).filter_by(tenant_id=tenant.tenant_id).all()
        else:
            principals = session.query(Principal).all()

        for principal in principals:
            print(f"\n{'=' * 80}")
            print(f"Name: {principal.name}")
            print(f"Principal ID: {principal.principal_id}")
            print(f"Tenant ID: {principal.tenant_id}")
            print("\nPlatform Mappings:")
            print(json.dumps(principal.platform_mappings, indent=2))


if __name__ == "__main__":
    tenant_name = sys.argv[1] if len(sys.argv) > 1 else None
    show_mappings(tenant_name)
