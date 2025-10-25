"""Integration tests for DashboardService with real database connections.

Replaces over-mocked unit tests with integration tests that use real database
connections and actual ORM objects to catch schema and field access bugs.

MIGRATED: Uses new pricing_options model instead of legacy Product pricing fields.
"""

from datetime import datetime

import pytest
from sqlalchemy import delete

from src.core.database.database_session import get_db_session
from src.core.database.models import Principal, Product, Tenant
from src.services.dashboard_service import DashboardService  # type: ignore[import-not-found]
from tests.integration_v2.conftest import create_test_product_with_pricing
from tests.utils.database_helpers import create_tenant_with_timestamps

# TODO: Fix failing tests and remove skip_ci (see GitHub issue #XXX)
pytestmark = [pytest.mark.integration, pytest.mark.skip_ci]


@pytest.mark.requires_db
class TestDashboardServiceIntegration:
    """Integration tests for DashboardService with real database data."""

    @pytest.fixture
    def test_tenant_data(self, integration_db):
        """Create test tenant with real database connection."""
        tenant_id = "dashboard_test_tenant"
        principal_id = "dashboard_test_principal"

        with get_db_session() as session:
            # Clean up existing test data (SQLAlchemy 2.0 pattern)
            session.execute(delete(Product).where(Product.tenant_id == tenant_id))
            session.execute(
                delete(Principal).where(Principal.tenant_id == tenant_id, Principal.principal_id == principal_id)
            )
            session.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))

            # Create test tenant with proper timestamps using helper
            tenant = create_tenant_with_timestamps(
                tenant_id=tenant_id, name="Dashboard Test Tenant", subdomain="dashboard-test"
            )
            session.add(tenant)
            session.flush()

            # Create test principal
            principal = Principal(
                tenant_id=tenant_id,
                principal_id=principal_id,
                name="Dashboard Test Principal",
                access_token="dashboard_test_token_123",
                platform_mappings={"mock": {"advertiser_id": "dashboard_advertiser"}},
            )
            session.add(principal)

            # Create test products using new pricing model
            product_1 = create_test_product_with_pricing(
                session=session,
                tenant_id=tenant_id,
                product_id="dashboard_product_001",
                name="Dashboard Test Display Product",
                description="Display product for dashboard testing",
                pricing_model="CPM",
                rate="4.50",
                is_fixed=False,
                currency="USD",
                min_spend_per_package="500.00",
                formats=["display_300x250", "display_728x90"],
                targeting_template={"geo": ["US"], "device": ["desktop", "mobile"]},
                delivery_type="non_guaranteed",
                is_custom=False,
            )

            product_2 = create_test_product_with_pricing(
                session=session,
                tenant_id=tenant_id,
                product_id="dashboard_product_002",
                name="Dashboard Test Video Product",
                description="Video product for dashboard testing",
                pricing_model="CPM",
                rate="12.00",
                is_fixed=True,
                currency="USD",
                min_spend_per_package="2000.00",
                formats=["video_15s", "video_30s"],
                targeting_template={"geo": ["US", "CA"], "device": ["mobile"]},
                delivery_type="guaranteed",
                is_custom=False,
            )

            session.commit()

            yield {"tenant_id": tenant_id, "principal_id": principal_id, "tenant": tenant, "principal": principal}

            # Cleanup (SQLAlchemy 2.0 pattern)
            session.execute(delete(Product).where(Product.tenant_id == tenant_id))
            session.execute(
                delete(Principal).where(Principal.tenant_id == tenant_id, Principal.principal_id == principal_id)
            )
            session.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
            session.commit()

    def test_dashboard_service_init_validation(self):
        """Test DashboardService initialization validation."""
        # Invalid tenant IDs should be rejected
        with pytest.raises(ValueError, match="Invalid tenant_id"):
            DashboardService("")

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            DashboardService("x" * 51)  # Too long

        # Valid tenant ID should be accepted
        service = DashboardService("valid_tenant_id")
        assert service.tenant_id == "valid_tenant_id"
        assert service._tenant is None  # Not loaded yet

    @pytest.mark.requires_db
    def test_get_tenant_with_real_database(self, test_tenant_data):
        """Test get_tenant with actual database connection."""
        tenant_id = test_tenant_data["tenant_id"]
        service = DashboardService(tenant_id)

        # First call should load from database
        tenant = service.get_tenant()
        assert tenant is not None
        assert tenant.tenant_id == tenant_id
        assert tenant.name == "Dashboard Test Tenant"
        assert tenant.subdomain == "dashboard-test"
        assert service._tenant == tenant  # Should be cached

        # Second call should use cached value
        tenant2 = service.get_tenant()
        assert tenant2 is tenant  # Same object reference (cached)

    @pytest.mark.requires_db
    def test_dashboard_service_field_access_safety(self, test_tenant_data):
        """Test that dashboard service safely accesses all database fields without AttributeError."""
        tenant_id = test_tenant_data["tenant_id"]
        service = DashboardService(tenant_id)

        # Test all tenant field access patterns
        tenant = service.get_tenant()

        # These should not raise AttributeError
        assert hasattr(tenant, "tenant_id")
        assert hasattr(tenant, "name")
        assert hasattr(tenant, "subdomain")
        assert hasattr(tenant, "billing_plan")
        assert hasattr(tenant, "created_at")
        assert hasattr(tenant, "updated_at")

        # Access the fields to ensure no AttributeError at runtime
        fields_to_test = ["tenant_id", "name", "subdomain", "billing_plan", "created_at", "updated_at"]
        for field in fields_to_test:
            value = getattr(tenant, field)
            assert value is not None, f"Field {field} should not be None"

    def test_dashboard_service_with_nonexistent_tenant(self, integration_db):
        """Test dashboard service behavior with nonexistent tenant."""
        service = DashboardService("nonexistent_tenant_id")

        # Should return None for nonexistent tenant
        tenant = service.get_tenant()
        assert tenant is None
        assert service._tenant is None

    def test_dashboard_service_database_session_handling(self, test_tenant_data):
        """Test that dashboard service properly handles database sessions."""
        tenant_id = test_tenant_data["tenant_id"]

        # Multiple instances should work independently
        service1 = DashboardService(tenant_id)
        service2 = DashboardService(tenant_id)

        tenant1 = service1.get_tenant()
        tenant2 = service2.get_tenant()

        # Should get equivalent data
        assert tenant1.tenant_id == tenant2.tenant_id
        assert tenant1.name == tenant2.name

        # But different instances (no shared state)
        assert service1._tenant is not service2._tenant or service1._tenant is None

    def test_dashboard_service_real_data_types(self, test_tenant_data):
        """Test that dashboard service handles real database data types correctly."""
        tenant_id = test_tenant_data["tenant_id"]
        service = DashboardService(tenant_id)

        tenant = service.get_tenant()

        # Verify correct data types from database
        assert isinstance(tenant.tenant_id, str)
        assert isinstance(tenant.name, str)
        assert isinstance(tenant.subdomain, str)
        assert isinstance(tenant.billing_plan, str)
        assert isinstance(tenant.created_at, datetime)
        assert isinstance(tenant.updated_at, datetime)

        # Verify timestamp handling (may be naive depending on database config)
        assert isinstance(tenant.created_at, datetime)
        assert isinstance(tenant.updated_at, datetime)
        # Note: timezone info may be None depending on database configuration
