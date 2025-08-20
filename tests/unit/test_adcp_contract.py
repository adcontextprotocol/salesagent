"""Contract tests to ensure database models match AdCP protocol schemas.

These tests verify that:
1. Database models have all required fields for AdCP schemas
2. Field types are compatible
3. Data can be correctly transformed between models and schemas
4. AdCP protocol requirements are met
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from models import Principal as PrincipalModel  # noqa: validate-model-imports  # Need both for contract test
from models import Product as ProductModel
from schemas import (
    CreateMediaBuyRequest,
    Format,
    GetProductsRequest,
    GetProductsResponse,
)
from schemas import (
    Principal as PrincipalSchema,
)
from schemas import (
    Product as ProductSchema,
)


class TestAdCPContract:
    """Test that models and schemas align with AdCP protocol requirements."""

    def test_product_model_to_schema(self):
        """Test that Product model can be converted to AdCP Product schema."""
        # Create a model instance with all required fields
        model = ProductModel(
            tenant_id="test_tenant",
            product_id="test_product",
            name="Test Product",
            description="A test product for AdCP protocol",
            formats=[
                {
                    "format_id": "display_300x250",
                    "name": "Medium Rectangle",
                    "type": "display",
                    "description": "Standard display format",
                    "width": 300,
                    "height": 250,
                    "delivery_options": {"hosted": None, "vast": None},
                }
            ],
            targeting_template={"geo_country": {"values": ["US", "CA"], "required": False}},
            delivery_type="guaranteed",  # AdCP: guaranteed or non_guaranteed
            is_fixed_price=True,
            cpm=Decimal("10.50"),
            price_guidance=None,
            is_custom=False,
            expires_at=None,
            countries=["US", "CA"],
            implementation_config={"internal": "config"},
        )

        # Convert to dict (simulating database retrieval)
        model_dict = {
            "product_id": model.product_id,
            "name": model.name,
            "description": model.description,
            "formats": model.formats,
            "delivery_type": model.delivery_type,
            "is_fixed_price": model.is_fixed_price,
            "cpm": float(model.cpm) if model.cpm else None,
            "price_guidance": model.price_guidance,
            "is_custom": model.is_custom,
            "expires_at": model.expires_at,
        }

        # Should be convertible to AdCP schema
        schema = ProductSchema(**model_dict)

        # Verify AdCP required fields
        assert schema.product_id == "test_product"
        assert schema.name == "Test Product"
        assert schema.description == "A test product for AdCP protocol"
        assert schema.delivery_type in ["guaranteed", "non_guaranteed"]
        assert len(schema.formats) > 0

        # Verify format structure matches AdCP
        format_obj = schema.formats[0]
        assert format_obj.format_id == "display_300x250"
        assert format_obj.type in ["display", "video", "audio", "native"]

    def test_product_with_price_guidance(self):
        """Test product with price_guidance (non-guaranteed in AdCP)."""
        model = ProductModel(
            tenant_id="test_tenant",
            product_id="test_ng_product",
            name="Non-Guaranteed Product",
            description="AdCP non-guaranteed product",
            formats=[
                {
                    "format_id": "video_15s",
                    "name": "15 Second Video",
                    "type": "video",
                    "description": "Video ad format",
                    "duration": 15,
                    "delivery_options": {"vast": {"mime_types": ["video/mp4"]}},
                }
            ],
            targeting_template={},
            delivery_type="non_guaranteed",
            is_fixed_price=False,
            cpm=None,
            price_guidance={
                "floor": 5.0,
                "p50": 10.0,
                "p75": 15.0,
                "p90": 20.0,
            },
            is_custom=False,
            expires_at=None,
            countries=["US"],
            implementation_config=None,
        )

        model_dict = {
            "product_id": model.product_id,
            "name": model.name,
            "description": model.description,
            "formats": model.formats,
            "delivery_type": model.delivery_type,
            "is_fixed_price": model.is_fixed_price,
            "cpm": None,
            "price_guidance": model.price_guidance,
            "is_custom": model.is_custom,
            "expires_at": model.expires_at,
        }

        schema = ProductSchema(**model_dict)

        # AdCP requires non_guaranteed products to have price_guidance
        assert schema.delivery_type == "non_guaranteed"
        assert schema.price_guidance is not None
        assert schema.price_guidance.floor == 5.0
        assert schema.cpm is None  # Should not have fixed CPM

    def test_principal_model_to_schema(self):
        """Test that Principal model matches AdCP authentication requirements."""
        model = PrincipalModel(
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Test Advertiser",
            access_token="secure_token_123",
            platform_mappings={
                "google_ad_manager": {"advertiser_id": "123456"},
                "mock": {"id": "test"},
            },
        )

        # Convert to schema format
        schema = PrincipalSchema(
            principal_id=model.principal_id,
            name=model.name,
            platform_mappings=model.platform_mappings,
        )

        # Test AdCP authentication
        assert schema.principal_id == "test_principal"
        assert schema.name == "Test Advertiser"

        # Test adapter ID retrieval (AdCP requirement for multi-platform support)
        assert schema.get_adapter_id("gam") == "123456"
        assert schema.get_adapter_id("google_ad_manager") == "123456"
        assert schema.get_adapter_id("mock") == "test"

    def test_adcp_get_products_request(self):
        """Test AdCP get_products request requirements."""
        # AdCP requires both brief and promoted_offering
        request = GetProductsRequest(
            brief="Looking for display ads on news sites",
            promoted_offering="B2B SaaS company selling analytics software",
        )

        assert request.brief is not None
        assert request.promoted_offering is not None

        # Should fail without promoted_offering (AdCP requirement)
        with pytest.raises(ValueError):
            GetProductsRequest(brief="Just a brief")

    def test_adcp_create_media_buy_request(self):
        """Test AdCP create_media_buy request structure."""
        start_date = datetime.now() + timedelta(days=1)
        end_date = datetime.now() + timedelta(days=30)

        request = CreateMediaBuyRequest(
            product_ids=["product_1", "product_2"],
            budget=5000.0,
            start_date=start_date.date(),
            end_date=end_date.date(),
            targeting_overlay={
                "geo_country_any_of": ["US", "CA"],
                "device_type_any_of": ["desktop", "mobile"],
                "signals": ["sports_enthusiasts", "auto_intenders"],
            },
        )

        # Verify AdCP requirements
        assert len(request.product_ids) > 0
        assert request.budget > 0
        # Also verify backward compatibility
        assert request.total_budget == request.budget
        assert request.flight_end_date > request.flight_start_date

        # Targeting overlay should support signals (AdCP v2.4)
        assert hasattr(request.targeting_overlay, "signals")
        assert request.targeting_overlay.signals == ["sports_enthusiasts", "auto_intenders"]

    def test_format_schema_compliance(self):
        """Test that Format schema matches AdCP specifications."""
        format_data = {
            "format_id": "native_feed",
            "name": "Native Feed Ad",
            "type": "native",
            "description": "Native advertisement in content feed",
            "delivery_options": {
                "hosted": {"preview_url": "https://example.com/preview"},
            },
            # Assets should follow the correct schema structure
            "assets": [],  # Native assets are optional
        }

        format_obj = Format(**format_data)

        # AdCP format requirements
        assert format_obj.format_id is not None
        assert format_obj.type in ["display", "video", "audio", "native"]
        assert format_obj.description is not None
        assert format_obj.delivery_options is not None

    def test_field_mapping_consistency(self):
        """Test that field names are consistent between models and schemas."""
        # These fields should map correctly
        model_to_schema_mapping = {
            # Model field -> Schema field
            "product_id": "product_id",
            "name": "name",
            "description": "description",
            "delivery_type": "delivery_type",  # Must be "guaranteed" or "non_guaranteed"
            "is_fixed_price": "is_fixed_price",
            "cpm": "cpm",
            "price_guidance": "price_guidance",
            "formats": "formats",
            "is_custom": "is_custom",
            "expires_at": "expires_at",
        }

        # Create test data
        model = ProductModel(
            tenant_id="test",
            product_id="test_mapping",
            name="Test",
            description="Test product",
            formats=[],
            targeting_template={},
            delivery_type="guaranteed",
            is_fixed_price=True,
            cpm=10.0,
            price_guidance=None,
            is_custom=False,
            expires_at=None,
            countries=["US"],
            implementation_config=None,
        )

        # Verify each field maps correctly
        for model_field, schema_field in model_to_schema_mapping.items():
            assert hasattr(model, model_field), f"Model missing field: {model_field}"
            assert schema_field in ProductSchema.model_fields, f"Schema missing field: {schema_field}"

    def test_adcp_delivery_type_values(self):
        """Test that delivery_type uses AdCP-compliant values."""
        # AdCP specifies exactly these two values
        valid_delivery_types = ["guaranteed", "non_guaranteed"]

        # Test valid values
        for delivery_type in valid_delivery_types:
            product = ProductSchema(
                product_id="test",
                name="Test",
                description="Test",
                formats=[],
                delivery_type=delivery_type,
                is_fixed_price=True,
                cpm=10.0,
            )
            assert product.delivery_type in valid_delivery_types

        # Invalid values should fail
        with pytest.raises(ValueError):
            ProductSchema(
                product_id="test",
                name="Test",
                description="Test",
                formats=[],
                delivery_type="programmatic",  # Not AdCP compliant
                is_fixed_price=True,
                cpm=10.0,
            )

    def test_adcp_response_excludes_internal_fields(self):
        """Test that AdCP responses don't expose internal fields."""
        products = [
            ProductSchema(
                product_id="test",
                name="Test Product",
                description="Test",
                formats=[],
                delivery_type="guaranteed",
                is_fixed_price=True,
                cpm=10.0,
                implementation_config={"internal": "data"},  # Should be excluded
            )
        ]

        response = GetProductsResponse(products=products)
        response_dict = response.model_dump()

        # Verify implementation_config is excluded from response
        for product in response_dict["products"]:
            assert "implementation_config" not in product, "Internal config should not be in AdCP response"

    def test_adcp_signal_support(self):
        """Test AdCP v2.4 signal support in targeting."""
        request = CreateMediaBuyRequest(
            product_ids=["test_product"],
            budget=1000.0,
            start_date=datetime.now().date(),
            end_date=(datetime.now() + timedelta(days=7)).date(),
            targeting_overlay={
                "signals": [
                    "sports_enthusiasts",
                    "auto_intenders_q1_2025",
                    "high_income_households",
                ],
                "aee_signals": {  # Renamed from provided_signals in v2.4
                    "custom_audience_1": "abc123",
                    "lookalike_model": "xyz789",
                },
            },
        )

        # Verify signals are supported
        assert hasattr(request.targeting_overlay, "signals")
        assert request.targeting_overlay.signals == [
            "sports_enthusiasts",
            "auto_intenders_q1_2025",
            "high_income_households",
        ]
        # Note: aee_signals was passed but might be mapped to key_value_pairs in the Targeting model


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
