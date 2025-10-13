"""Minimal database initialization for CI/CD testing."""

import os
import sys
from pathlib import Path

# Add the project root directory to Python path to ensure imports work
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def init_db_ci():
    """Initialize database with migrations only for CI testing."""
    try:
        # Import here to ensure path is set up first
        import uuid
        from datetime import UTC, datetime

        from sqlalchemy import select

        from scripts.ops.migrate import run_migrations
        from src.core.database.database_session import get_db_session
        from src.core.database.models import CurrencyLimit, Principal, Product, Tenant

        print("Applying database migrations for CI...")
        run_migrations()
        print("Database migrations applied successfully")

        # Create a default tenant for CI tests
        print("Creating default tenant for CI...")
        with get_db_session() as session:
            # First, check if CI test tenant already exists
            stmt = select(Tenant).filter_by(subdomain="ci-test")
            existing_tenant = session.scalars(stmt).first()

            if existing_tenant:
                print(f"CI test tenant already exists (ID: {existing_tenant.tenant_id})")
                tenant_id = existing_tenant.tenant_id

                # Check if principal exists for this tenant
                stmt_principal = select(Principal).filter_by(tenant_id=tenant_id, access_token="ci-test-token")
                existing_principal = session.scalars(stmt_principal).first()
                if not existing_principal:
                    # Create principal if it doesn't exist
                    principal_id = str(uuid.uuid4())
                    principal = Principal(
                        principal_id=principal_id,
                        tenant_id=tenant_id,
                        name="CI Test Principal",
                        access_token="ci-test-token",
                        platform_mappings={"mock": {"advertiser_id": "test-advertiser"}},
                    )
                    session.add(principal)
                    print(f"Created principal (ID: {principal_id}) for existing tenant")

                # Check if currency limit exists for this tenant
                stmt_currency = select(CurrencyLimit).filter_by(tenant_id=tenant_id, currency_code="USD")
                existing_currency = session.scalars(stmt_currency).first()
                if not existing_currency:
                    # Create currency limit if it doesn't exist
                    currency_limit = CurrencyLimit(
                        tenant_id=tenant_id,
                        currency_code="USD",
                        min_package_budget=1000.0,
                        max_daily_package_spend=10000.0,
                    )
                    session.add(currency_limit)
                    print("Created currency limit for existing tenant")

                session.commit()  # Commit before creating products to avoid autoflush
            else:
                tenant_id = str(uuid.uuid4())

                # Create default tenant
                now = datetime.now(UTC)
                tenant = Tenant(
                    tenant_id=tenant_id,
                    name="CI Test Tenant",
                    subdomain="ci-test",
                    billing_plan="test",
                    ad_server="mock",
                    enable_axe_signals=True,
                    auto_approve_formats=["display_300x250", "display_728x90"],
                    human_review_required=False,
                    created_at=now,
                    updated_at=now,
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

                # Create default currency limit
                currency_limit = CurrencyLimit(
                    tenant_id=tenant_id,
                    currency_code="USD",
                    min_package_budget=1000.0,
                    max_daily_package_spend=10000.0,
                )
                session.add(currency_limit)

                session.commit()  # Commit before creating products to avoid autoflush
                print(f"Created tenant (ID: {tenant_id}), principal (ID: {principal_id}), and currency limit")

            # Create default products for testing
            print("Creating default products for CI...")
            products_data = [
                {
                    "product_id": "prod_display_premium",
                    "name": "Premium Display Advertising",
                    "description": "High-impact display ads across premium content",
                    "formats": ["display_300x250", "display_728x90", "display_160x600"],
                    "targeting_template": {"geo": ["US"], "device_type": "any"},
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "cpm": 15.0,
                },
                {
                    "product_id": "prod_video_premium",
                    "name": "Premium Video Advertising",
                    "description": "Pre-roll video ads with guaranteed completion rates",
                    "formats": ["video_15s", "video_30s"],
                    "targeting_template": {"geo": ["US"], "device_type": "any"},
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "cpm": 25.0,
                },
            ]

            for p in products_data:
                # Check if product already exists
                stmt = select(Product).filter_by(tenant_id=tenant_id, product_id=p["product_id"])
                existing_product = session.scalars(stmt).first()

                if not existing_product:
                    product = Product(
                        tenant_id=tenant_id,
                        product_id=p["product_id"],
                        name=p["name"],
                        description=p["description"],
                        formats=p["formats"],
                        targeting_template=p["targeting_template"],
                        delivery_type=p["delivery_type"],
                        is_fixed_price=p["is_fixed_price"],
                        cpm=p.get("cpm"),
                        property_tags=["all_inventory"],  # Required per AdCP spec
                    )
                    session.add(product)
                    print(f"  Created product: {p['name']}")
                else:
                    print(f"  Product already exists: {p['name']}")

            session.commit()
            print(
                f"Created default tenant (ID: {tenant_id}), principal (ID: {principal_id}), and {len(products_data)} products"
            )

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
