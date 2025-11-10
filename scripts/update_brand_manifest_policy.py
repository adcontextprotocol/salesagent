#!/usr/bin/env python3
"""Update brand_manifest_policy for all tenants to require_auth.

This makes brand_manifest optional for all tenants, which is useful for testing
and matches the B2B model where advertisers need auth but not necessarily a
brand manifest for every request.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant


def update_all_tenants_to_require_auth():
    """Update all tenants to use require_auth policy."""
    with get_db_session() as session:
        # Get all tenants
        stmt = select(Tenant)
        tenants = session.scalars(stmt).all()

        print(f"Found {len(tenants)} tenants")

        updated_count = 0
        for tenant in tenants:
            old_policy = tenant.brand_manifest_policy
            if old_policy != "require_auth":
                tenant.brand_manifest_policy = "require_auth"
                print(f"  Updated tenant '{tenant.name}' ({tenant.tenant_id}): {old_policy} -> require_auth")
                updated_count += 1
            else:
                print(f"  Tenant '{tenant.name}' ({tenant.tenant_id}): already set to require_auth")

        if updated_count > 0:
            session.commit()
            print(f"\n✅ Successfully updated {updated_count} tenant(s) to require_auth policy")
        else:
            print("\n✅ All tenants already using require_auth policy")

        return updated_count


def main():
    """Main entry point."""
    print("Updating brand_manifest_policy for all tenants...\n")
    try:
        update_all_tenants_to_require_auth()
    except Exception as e:
        print(f"\n❌ Error updating tenants: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
