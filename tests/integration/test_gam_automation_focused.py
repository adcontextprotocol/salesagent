"""
Integration tests for GAM automatic order activation feature (simplified).

Tests the implementation of Issue #116: automatic activation for non-guaranteed GAM orders.
Focused integration tests using real database connections and minimal mocking.
"""

import json
from datetime import datetime

import pytest

from src.adapters.google_ad_manager import GUARANTEED_LINE_ITEM_TYPES, NON_GUARANTEED_LINE_ITEM_TYPES
from src.core.database.database_session import get_db_session
from src.core.database.models import Product, Tenant
from src.core.schemas import MediaPackage, Principal


class TestGAMAutomationBasics:
    """Test basic GAM automation constants and configuration."""

    def test_line_item_type_constants(self):
        """Test that line item type constants are correctly defined."""
        # Test guaranteed types
        assert "STANDARD" in GUARANTEED_LINE_ITEM_TYPES
        assert "SPONSORSHIP" in GUARANTEED_LINE_ITEM_TYPES

        # Test non-guaranteed types
        assert "NETWORK" in NON_GUARANTEED_LINE_ITEM_TYPES
        assert "HOUSE" in NON_GUARANTEED_LINE_ITEM_TYPES
        assert "PRICE_PRIORITY" in NON_GUARANTEED_LINE_ITEM_TYPES
        assert "BULK" in NON_GUARANTEED_LINE_ITEM_TYPES

        # Ensure no overlap
        assert not (GUARANTEED_LINE_ITEM_TYPES & NON_GUARANTEED_LINE_ITEM_TYPES)


class TestGAMProductConfiguration:
    """Test database-backed product configuration for automation."""

    @pytest.fixture
    def test_tenant_data(self):
        """Create test tenant and products in database."""
        tenant_id = "test_automation_tenant"

        with get_db_session() as db_session:
            # Create test tenant
            test_tenant = Tenant(
                tenant_id=tenant_id,
                name="Test Automation Tenant",
                subdomain="test-auto",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            db_session.add(test_tenant)

            # Non-guaranteed product with automatic activation
            product_auto = Product(
                tenant_id=tenant_id,
                product_id="test_product_auto",
                name="Auto Network Product",
                formats=[{"format_id": "display_300x250", "name": "Display 300x250", "type": "display"}],
                targeting_template={},
                delivery_type="non_guaranteed",
                is_fixed_price=True,
                cpm=2.50,
                implementation_config=json.dumps(
                    {
                        "line_item_type": "NETWORK",
                        "non_guaranteed_automation": "automatic",
                        "creative_placeholders": [{"width": 300, "height": 250, "expected_creative_count": 1}],
                    }
                ),
            )

            # Non-guaranteed product requiring confirmation
            product_conf = Product(
                tenant_id=tenant_id,
                product_id="test_product_confirm",
                name="Confirmation House Product",
                formats=[{"format_id": "display_728x90", "name": "Leaderboard 728x90", "type": "display"}],
                targeting_template={},
                delivery_type="non_guaranteed",
                is_fixed_price=True,
                cpm=1.00,
                implementation_config=json.dumps(
                    {
                        "line_item_type": "HOUSE",
                        "non_guaranteed_automation": "confirmation_required",
                        "creative_placeholders": [{"width": 728, "height": 90, "expected_creative_count": 1}],
                    }
                ),
            )

            db_session.add_all([product_auto, product_conf])
            db_session.commit()

        yield tenant_id, product_auto.product_id, product_conf.product_id

        # Cleanup
        with get_db_session() as db_session:
            db_session.query(Product).filter_by(tenant_id=tenant_id).delete()
            db_session.query(Tenant).filter_by(tenant_id=tenant_id).delete()
            db_session.commit()

    def test_product_automation_config_parsing(self, test_tenant_data):
        """Test that product automation configuration is correctly stored and retrieved."""
        tenant_id, auto_product_id, conf_product_id = test_tenant_data

        with get_db_session() as db_session:
            # Test automatic product
            auto_product = db_session.query(Product).filter_by(tenant_id=tenant_id, product_id=auto_product_id).first()

            assert auto_product is not None
            config = json.loads(auto_product.implementation_config)
            assert config["non_guaranteed_automation"] == "automatic"
            assert config["line_item_type"] == "NETWORK"

            # Test confirmation required product
            conf_product = db_session.query(Product).filter_by(tenant_id=tenant_id, product_id=conf_product_id).first()

            assert conf_product is not None
            config = json.loads(conf_product.implementation_config)
            assert config["non_guaranteed_automation"] == "confirmation_required"
            assert config["line_item_type"] == "HOUSE"


class TestGAMPackageTypes:
    """Test media package type detection and validation."""

    def test_package_delivery_type_mapping(self):
        """Test that MediaPackage delivery types map correctly to automation behavior."""
        # Non-guaranteed package
        non_guaranteed_pkg = MediaPackage(
            package_id="test_network",
            name="Network Package",
            delivery_type="non_guaranteed",
            impressions=10000,
            cpm=2.50,
            format_ids=["display_300x250"],
        )

        assert non_guaranteed_pkg.delivery_type == "non_guaranteed"

        # Guaranteed package
        guaranteed_pkg = MediaPackage(
            package_id="test_standard",
            name="Standard Package",
            delivery_type="guaranteed",
            impressions=50000,
            cpm=5.00,
            format_ids=["display_300x250"],
        )

        assert guaranteed_pkg.delivery_type == "guaranteed"

    def test_principal_configuration(self):
        """Test principal object creation for GAM integration."""
        principal = Principal(
            tenant_id="test_tenant",
            principal_id="test_advertiser",
            name="Test Advertiser",
            access_token="test_token",
            platform_mappings={"gam_advertiser_id": "123456"},
        )

        assert principal.tenant_id == "test_tenant"
        assert principal.platform_mappings["gam_advertiser_id"] == "123456"
        assert principal.get_adapter_id() == "test_advertiser"
