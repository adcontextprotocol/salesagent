"""Minimal database initialization for CI/CD testing."""

import os
import sys
from pathlib import Path

# Add the current directory to Python path to ensure imports work
sys.path.insert(0, str(Path(__file__).parent))


def init_db_ci():
    """Initialize database with migrations only for CI testing."""
    try:
        # Import here to ensure path is set up first
        import uuid

        from database_session import get_db_session
        from migrate import run_migrations

        from src.core.database.models import AuthorizedProperty, CurrencyLimit, Principal, Tenant

        print("Applying database migrations for CI...")
        run_migrations()
        print("Database migrations applied successfully")

        # Create a default tenant for CI tests
        print("Creating default tenant for CI...")
        with get_db_session() as session:
            # First, check if CI test tenant already exists
            existing = session.query(Tenant).filter_by(subdomain="ci-test").first()

            if existing:
                print(f"CI test tenant already exists (ID: {existing.tenant_id}), skipping creation")
                return

            tenant_id = str(uuid.uuid4())

            # Create default tenant
            tenant = Tenant(
                tenant_id=tenant_id,
                name="CI Test Tenant",
                subdomain="ci-test",
                billing_plan="test",
                ad_server="mock",
                enable_axe_signals=True,
                auto_approve_formats=["display_300x250", "display_728x90"],
                human_review_required=False,
            )
            session.add(tenant)

            # Create a default principal for the tenant
            principal_id = str(uuid.uuid4())
            principal = Principal(
                principal_id=principal_id,
                tenant_id=tenant_id,
                name="CI Test Principal",
                access_token="ci-test-token",
                platform_mappings={"mock": {"advertiser_id": "test-advertiser"}},
            )
            session.add(principal)

            # Add currency limits (required for setup checklist)
            for currency in ["USD", "EUR", "GBP"]:
                currency_limit = CurrencyLimit(
                    tenant_id=tenant_id,
                    currency_code=currency,
                    min_package_budget=0.0,
                    max_daily_package_spend=100000.0,
                )
                session.add(currency_limit)

            # Add authorized property (required for setup checklist)
            authorized_property = AuthorizedProperty(
                tenant_id=tenant_id,
                property_id="ci-test-property",
                property_name="CI Test Property",
                property_url="https://example.com",
                is_approved=True,
            )
            session.add(authorized_property)

            session.commit()
            print(f"Created default tenant (ID: {tenant_id}) and principal (ID: {principal_id})")
            print("Added currency limits: USD, EUR, GBP")
            print("Added authorized property: ci-test-property")

        print("Database initialized successfully")
    except ImportError as e:
        print(f"Import error: {e}")
        print(f"Python path: {sys.path}")
        print(f"Current directory: {os.getcwd()}")
        sys.exit(1)
    except Exception as e:
        print(f"Error during initialization: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    init_db_ci()
