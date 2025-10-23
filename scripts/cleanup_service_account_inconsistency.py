#!/usr/bin/env python3
"""
Utility script to check and fix service account consistency between database and GCP.

Usage:
    # Check consistency only (dry run)
    uv run python scripts/cleanup_service_account_inconsistency.py --check

    # Fix inconsistencies by deleting orphaned GCP accounts
    uv run python scripts/cleanup_service_account_inconsistency.py --fix

    # Fix specific tenant
    uv run python scripts/cleanup_service_account_inconsistency.py --fix --tenant weather
"""

import argparse
import os
import sys

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import AdapterConfig
from src.services.gcp_service_account_service import GCPServiceAccountService


def check_consistency(tenant_id=None, fix=False):
    """Check (and optionally fix) service account consistency."""
    gcp_project_id = os.environ.get("GCP_PROJECT_ID")
    if not gcp_project_id:
        print("ERROR: GCP_PROJECT_ID environment variable not set")
        sys.exit(1)

    service = GCPServiceAccountService(gcp_project_id=gcp_project_id)

    with get_db_session() as session:
        # Get all adapter configs (or specific tenant)
        stmt = select(AdapterConfig)
        if tenant_id:
            stmt = stmt.filter_by(tenant_id=tenant_id)

        configs = session.scalars(stmt).all()

        if not configs:
            print(f"No adapter configs found{f' for tenant {tenant_id}' if tenant_id else ''}")
            return

        print("\n" + "=" * 80)
        print("SERVICE ACCOUNT CONSISTENCY CHECK")
        print("=" * 80)

        inconsistencies = []

        for config in configs:
            tenant_id = config.tenant_id
            db_email = config.gam_service_account_email
            has_json = bool(config.gam_service_account_json)

            # Expected email
            account_id = f"adcp-sales-{tenant_id}".lower()
            if len(account_id) > 30:
                account_id = account_id[:30]
            expected_email = f"{account_id}@{gcp_project_id}.iam.gserviceaccount.com"

            print(f"\nTenant: {tenant_id}")
            print(f"  Expected email: {expected_email}")
            print(f"  Database email: {db_email or 'NONE'}")
            print(f"  Has credentials: {has_json}")

            # Check GCP
            try:
                gcp_account = service._get_service_account_if_exists(expected_email)

                if gcp_account and not db_email:
                    print("  ⚠️  INCONSISTENT: Exists in GCP but NOT in database")
                    print("     This happened when key creation failed after account creation")
                    inconsistencies.append(("orphaned_in_gcp", tenant_id, expected_email))

                elif not gcp_account and db_email:
                    print("  ⚠️  INCONSISTENT: Exists in database but NOT in GCP")
                    print("     This should not happen - database entry is stale")
                    inconsistencies.append(("orphaned_in_db", tenant_id, db_email))

                elif gcp_account and db_email:
                    if db_email == expected_email:
                        print("  ✓  CONSISTENT: Exists in both GCP and database")
                    else:
                        print(f"  ⚠️  MISMATCH: DB has {db_email}, expected {expected_email}")
                        inconsistencies.append(("mismatch", tenant_id, db_email, expected_email))

                else:
                    print("  ✓  CONSISTENT: No service account (clean state)")

            except Exception as e:
                print(f"  ❌  ERROR checking GCP: {e}")

        print("\n" + "=" * 80)
        print(f"SUMMARY: Found {len(inconsistencies)} inconsistencies")
        print("=" * 80)

        if inconsistencies and not fix:
            print("\nTo fix these issues, run with --fix flag")
            print("Note: Fixing will DELETE orphaned service accounts from GCP")
            return

        if inconsistencies and fix:
            print("\nFIXING INCONSISTENCIES...")
            for issue_type, *details in inconsistencies:
                if issue_type == "orphaned_in_gcp":
                    tenant_id, email = details
                    print(f"\n  Deleting orphaned service account from GCP: {email}")
                    try:
                        service._delete_service_account_from_gcp(email)
                        print("    ✓ Deleted successfully")
                    except Exception as e:
                        print(f"    ❌ Failed to delete: {e}")

                elif issue_type == "orphaned_in_db":
                    tenant_id, email = details
                    print(f"\n  Clearing stale database entry for tenant {tenant_id}")
                    try:
                        with get_db_session() as fix_session:
                            stmt = select(AdapterConfig).filter_by(tenant_id=tenant_id)
                            cfg = fix_session.scalars(stmt).first()
                            if cfg:
                                cfg.gam_service_account_email = None
                                cfg.gam_service_account_json = None
                                fix_session.commit()
                                print("    ✓ Cleared successfully")
                    except Exception as e:
                        print(f"    ❌ Failed to clear: {e}")

            print("\n" + "=" * 80)
            print("FIX COMPLETE - Run check again to verify")
            print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Check and fix service account consistency")
    parser.add_argument("--check", action="store_true", help="Check consistency only (default)")
    parser.add_argument("--fix", action="store_true", help="Fix inconsistencies")
    parser.add_argument("--tenant", help="Check/fix specific tenant only")

    args = parser.parse_args()

    # Default to check mode if nothing specified
    if not args.check and not args.fix:
        args.check = True

    check_consistency(tenant_id=args.tenant, fix=args.fix)


if __name__ == "__main__":
    main()
