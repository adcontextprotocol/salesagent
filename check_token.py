#!/usr/bin/env python3

"""Script to check if a specific token exists in the database."""

import sys

from src.core.database.database_session import get_db_session
from src.core.database.models import Principal, Tenant


def check_token(token):
    """Check if a token exists in the database."""
    try:
        with get_db_session() as session:
            # Check if token exists
            principal = session.query(Principal).filter_by(access_token=token).first()

            if principal:
                print(f"✅ Token found: Principal '{principal.principal_id}' in tenant '{principal.tenant_id}'")
                # Check if tenant is active
                tenant = session.query(Tenant).filter_by(tenant_id=principal.tenant_id).first()
                if tenant:
                    print(f"✅ Tenant: '{tenant.name}' (active: {tenant.is_active})")
                    return True
                else:
                    print("❌ Tenant not found!")
                    return False
            else:
                print("❌ Token not found in database")

                # Show first 3 tokens for reference
                all_principals = session.query(Principal).limit(3).all()
                print("\nFirst 3 tokens in database:")
                for p in all_principals:
                    print(f"  {p.access_token[:20]}... -> {p.principal_id} (tenant: {p.tenant_id})")
                return False

    except Exception as e:
        print(f"❌ Database error: {e}")
        return False


if __name__ == "__main__":
    token = "UhwoigyVKdd6GT8hS04cc51ckGfi8qXpZL6OvS2i2cU"
    if len(sys.argv) > 1:
        token = sys.argv[1]

    print(f"Checking token: {token}")
    result = check_token(token)
    sys.exit(0 if result else 1)
