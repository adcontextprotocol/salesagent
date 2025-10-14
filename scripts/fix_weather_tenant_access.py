#!/usr/bin/env python3
"""
Fix Weather tenant access issue.

This script helps diagnose and fix access control issues for the Weather tenant.

Usage:
    # Check current status
    python scripts/fix_weather_tenant_access.py --check

    # Add domain authorization (gives access to all @weather.com users)
    python scripts/fix_weather_tenant_access.py --add-domain weather.com

    # Add specific email
    python scripts/fix_weather_tenant_access.py --add-email yoon.lee@weather.com

    # Add Jay Lee as admin with domain access
    python scripts/fix_weather_tenant_access.py --fix-all
"""

import argparse
import logging
import sys

from sqlalchemy import select

from src.admin.domain_access import (
    add_authorized_domain,
    add_authorized_email,
    ensure_user_in_tenant,
)
from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def find_weather_tenant() -> Tenant | None:
    """Find the Weather tenant."""
    with get_db_session() as session:
        stmt = select(Tenant).where(Tenant.name.ilike("%weather%"))
        return session.scalars(stmt).first()


def check_tenant_access(tenant: Tenant) -> dict:
    """Check current access configuration for tenant."""
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "subdomain": tenant.subdomain,
        "authorized_domains": tenant.authorized_domains or [],
        "authorized_emails": tenant.authorized_emails or [],
        "is_active": tenant.is_active,
    }


def check_status():
    """Check current status of Weather tenant access."""
    tenant = find_weather_tenant()

    if not tenant:
        logger.error("❌ Weather tenant not found in database")
        return False

    logger.info(f"✅ Found Weather tenant: {tenant.tenant_id}")

    access = check_tenant_access(tenant)
    logger.info(f"   Name: {access['name']}")
    logger.info(f"   Subdomain: {access['subdomain']}")
    logger.info(f"   Active: {access['is_active']}")
    logger.info(f"   Authorized Domains: {access['authorized_domains']}")
    logger.info(f"   Authorized Emails: {access['authorized_emails']}")

    # Check for users
    with get_db_session() as session:
        stmt = select(User).filter_by(tenant_id=tenant.tenant_id)
        users = session.scalars(stmt).all()
        logger.info(f"   Users: {len(users)}")
        for user in users:
            logger.info(f"     - {user.email} ({user.role}, active={user.is_active})")

    return True


def add_domain(domain: str):
    """Add domain to Weather tenant authorization."""
    tenant = find_weather_tenant()

    if not tenant:
        logger.error("❌ Weather tenant not found in database")
        return False

    logger.info(f"Adding domain {domain} to tenant {tenant.tenant_id}")

    if add_authorized_domain(str(tenant.tenant_id), domain):
        logger.info(f"✅ Successfully added domain {domain}")
        logger.info(f"   All users with @{domain} emails now have access")
        return True
    else:
        logger.error(f"❌ Failed to add domain {domain}")
        return False


def add_email(email: str):
    """Add email to Weather tenant authorization."""
    tenant = find_weather_tenant()

    if not tenant:
        logger.error("❌ Weather tenant not found in database")
        return False

    logger.info(f"Adding email {email} to tenant {tenant.tenant_id}")

    if add_authorized_email(str(tenant.tenant_id), email):
        logger.info(f"✅ Successfully added email {email}")
        return True
    else:
        logger.error(f"❌ Failed to add email {email}")
        return False


def fix_all():
    """Complete fix: add domain and Jay Lee as admin."""
    tenant = find_weather_tenant()

    if not tenant:
        logger.error("❌ Weather tenant not found in database")
        logger.info("   The tenant needs to be created first.")
        return False

    logger.info("🔧 Fixing Weather tenant access...")

    # Add domain
    logger.info("1. Adding weather.com domain...")
    if add_authorized_domain(str(tenant.tenant_id), "weather.com"):
        logger.info("   ✅ Domain added")
    else:
        logger.error("   ❌ Failed to add domain")

    # Add Jay Lee's email
    logger.info("2. Adding Jay Lee's email...")
    jay_email = "yoon.lee@weather.com"
    if add_authorized_email(str(tenant.tenant_id), jay_email):
        logger.info("   ✅ Email added")
    else:
        logger.error("   ❌ Failed to add email")

    # Create user record for Jay Lee
    logger.info("3. Creating admin user for Jay Lee...")
    try:
        user = ensure_user_in_tenant(jay_email, str(tenant.tenant_id), role="admin", name="Jay Lee")
        logger.info(f"   ✅ User created: {user.email} (role: {user.role})")
    except Exception as e:
        logger.error(f"   ❌ Failed to create user: {e}")

    logger.info("\n🎉 Weather tenant access fix complete!")
    logger.info("   Next steps:")
    logger.info("   1. Jay Lee should be able to access the Weather tenant now")
    logger.info("   2. Any user with @weather.com email can access the tenant")
    logger.info("   3. Jay Lee can add more admins through the admin UI")

    return True


def main():
    parser = argparse.ArgumentParser(description="Fix Weather tenant access")
    parser.add_argument("--check", action="store_true", help="Check current status")
    parser.add_argument("--add-domain", type=str, help="Add domain to authorized list")
    parser.add_argument("--add-email", type=str, help="Add email to authorized list")
    parser.add_argument("--fix-all", action="store_true", help="Apply complete fix")

    args = parser.parse_args()

    if args.check:
        success = check_status()
    elif args.add_domain:
        success = add_domain(args.add_domain)
    elif args.add_email:
        success = add_email(args.add_email)
    elif args.fix_all:
        success = fix_all()
    else:
        parser.print_help()
        return

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
