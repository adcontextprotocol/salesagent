#!/usr/bin/env python3
"""Comprehensive AdCP schema compliance testing.

This test suite validates all AdCP fields, variations, and edge cases
to ensure full specification compliance across all possible configurations.
"""

import pytest

from tests.e2e.adcp_schema_validator import AdCPSchemaValidator, SchemaValidationError


@pytest.fixture
async def validator():
    """Create AdCP schema validator for testing."""
    return AdCPSchemaValidator(adcp_version="v1")


class TestProductCompliance:
    """Test Product model compliance with all AdCP spec fields."""

    @pytest.mark.asyncio
    async def test_minimal_product_compliance(self, validator):
        """Test minimal required Product fields."""
        minimal_product = {
            "product_id": "test_minimal",
            "name": "Minimal Product",
            "description": "A minimal test product",
            "format_ids": ["display_300x250"],
            "property_tags": ["premium_display"],  # Format IDs per AdCP spec
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
        }

        response = {"adcp_version": "1.0.0", "products": [minimal_product]}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_comprehensive_product_compliance(self, validator):
        """Test Product with all possible AdCP fields populated."""
        comprehensive_product = {
            "product_id": "test_comprehensive",
            "name": "Comprehensive Product",
            "description": "A product with all AdCP fields populated for testing",
            "format_ids": [
                "display_300x250",  # Medium Rectangle
                "video_preroll",  # Pre-Roll Video
            ],
            "property_tags": ["premium_display"],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "cpm": 12.50,
            "min_spend": 1000.0,
            "measurement": {
                "type": "brand_lift",
                "attribution": "deterministic_purchase",
                "window": "30_days",
                "reporting": "real_time_api",
            },
            "creative_policy": {
                "co_branding": "required",
                "landing_page": "retailer_site_only",
                "templates_available": True,
            },
            "is_custom": False,
            "brief_relevance": "This product matches your brief because it targets premium inventory with brand lift measurement",
            "expires_at": "2025-12-31T23:59:59Z",
        }

        response = {"adcp_version": "1.0.0", "products": [comprehensive_product]}
        try:
            await validator.validate_response("get-products", response)
        except Exception as e:
            print("\n❌ Comprehensive product validation failed:")
            print(f"Error: {str(e)}")
            if hasattr(e, "validation_errors"):
                print("Detailed errors:")
                for error in e.validation_errors:
                    print(f"  - {error}")
            raise

    @pytest.mark.asyncio
    async def test_delivery_type_variations(self, validator):
        """Test both guaranteed and non_guaranteed delivery types."""
        products = [
            {
                "product_id": "guaranteed_product",
                "name": "Guaranteed Product",
                "description": "A guaranteed delivery product",
                "format_ids": ["display_300x250"],
                "property_tags": ["premium_display"],
                "delivery_type": "guaranteed",
                "is_fixed_price": True,
                "cpm": 15.0,
            },
            {
                "product_id": "non_guaranteed_product",
                "name": "Non-Guaranteed Product",
                "description": "A non-guaranteed delivery product",
                "format_ids": ["display_728x90"],
                "property_tags": ["premium_display"],
                "delivery_type": "non_guaranteed",
                "is_fixed_price": False,
            },
        ]

        response = {"adcp_version": "1.0.0", "products": products}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_measurement_variations(self, validator):
        """Test all measurement type variations."""
        measurement_types = [
            {
                "type": "incremental_sales_lift",
                "attribution": "deterministic_purchase",
                "reporting": "weekly_dashboard",
            },
            {"type": "brand_lift", "attribution": "probabilistic", "window": "7_days", "reporting": "real_time_api"},
            {
                "type": "foot_traffic",
                "attribution": "deterministic_purchase",
                "window": "30_days",
                "reporting": "weekly_dashboard",
            },
        ]

        products = []
        for i, measurement in enumerate(measurement_types):
            products.append(
                {
                    "product_id": f"measurement_test_{i}",
                    "name": f"Measurement Test {i}",
                    "description": f"Testing measurement type: {measurement['type']}",
                    "format_ids": ["display_300x250"],
                    "property_tags": ["premium_display"],
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "measurement": measurement,
                }
            )

        response = {"adcp_version": "1.0.0", "products": products}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_creative_policy_variations(self, validator):
        """Test all creative policy variations."""
        creative_policies = [
            {"co_branding": "required", "landing_page": "any", "templates_available": True},
            {"co_branding": "optional", "landing_page": "retailer_site_only", "templates_available": False},
            {"co_branding": "none", "landing_page": "must_include_retailer", "templates_available": True},
        ]

        products = []
        for i, policy in enumerate(creative_policies):
            products.append(
                {
                    "product_id": f"policy_test_{i}",
                    "name": f"Policy Test {i}",
                    "description": f"Testing creative policy: {policy['co_branding']}",
                    "format_ids": ["display_300x250"],
                    "property_tags": ["premium_display"],
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "creative_policy": policy,
                }
            )

        response = {"adcp_version": "1.0.0", "products": products}
        await validator.validate_response("get-products", response)


class TestFormatCompliance:
    """Test Format model compliance with all AdCP spec variations."""

    @pytest.mark.asyncio
    async def test_format_type_variations(self, validator):
        """Test all format types defined in AdCP spec."""
        format_types = ["audio", "video", "display", "native", "dooh"]

        products = []
        for format_type in format_types:
            products.append(
                {
                    "product_id": f"{format_type}_product",
                    "name": f"{format_type.title()} Product",
                    "description": f"Product for {format_type} formats",
                    "format_ids": [f"{format_type}_test"],
                    "property_tags": ["premium_display"],
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                }
            )

        response = {"adcp_version": "1.0.0", "products": products}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_format_with_assets_required(self, validator):
        """Test Format with assets_required for composite formats."""
        format_with_assets = {
            "format_id": "native_composite",
            "name": "Native Composite Format",
            "type": "native",
            "is_standard": True,
            "assets_required": [
                {"asset_type": "headline", "quantity": 1, "requirements": {"max_characters": 50, "required": True}},
                {
                    "asset_type": "image",
                    "quantity": 2,
                    "requirements": {"min_width": 300, "min_height": 200, "format_ids": ["jpg", "png"]},
                },
            ],
        }

        product = {
            "product_id": "native_test",
            "name": "Native Test Product",
            "description": "Testing native format with required assets",
            "format_ids": ["native_composite"],
            "property_tags": ["premium_display"],  # Format ID per updated AdCP spec
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
        }

        response = {"adcp_version": "1.0.0", "products": [product]}
        await validator.validate_response("get-products", response)


class TestEdgeCasesAndValidation:
    """Test edge cases and validation rules."""

    @pytest.mark.asyncio
    async def test_empty_products_list(self, validator):
        """Test valid empty products response."""
        response = {"adcp_version": "1.0.0", "products": []}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_invalid_delivery_type(self, validator):
        """Test that invalid delivery_type is rejected."""
        invalid_product = {
            "product_id": "invalid_delivery",
            "name": "Invalid Product",
            "description": "Product with invalid delivery type",
            "format_ids": ["display_300x250"],
            "property_tags": ["premium_display"],
            "delivery_type": "invalid_type",  # Invalid value
            "is_fixed_price": True,
        }

        response = {"adcp_version": "1.0.0", "products": [invalid_product]}

        with pytest.raises(SchemaValidationError):
            await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_custom_format_ids_allowed(self, validator):
        """Test that custom/arbitrary format IDs are accepted (schema doesn't validate against enum)."""
        custom_format_product = {
            "product_id": "custom_format",
            "name": "Custom Format Product",
            "description": "Product with custom format ID",
            "format_ids": ["custom_format_xyz"],  # Custom format IDs are allowed
            "property_tags": ["premium_display"],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
        }

        response = {"adcp_version": "1.0.0", "products": [custom_format_product]}

        # Should pass - schema accepts any string as format_id
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, validator):
        """Test that missing required fields are rejected."""
        incomplete_product = {
            "product_id": "incomplete",
            "name": "Incomplete Product",
            # Missing required fields: description, formats, delivery_type, is_fixed_price
        }

        response = {"adcp_version": "1.0.0", "products": [incomplete_product]}

        with pytest.raises(SchemaValidationError):
            await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_additional_properties_rejected(self, validator):
        """Test that additional properties are rejected due to additionalProperties: false."""
        product_with_extra_field = {
            "product_id": "extra_field",
            "name": "Product with Extra Field",
            "description": "This product has an extra field",
            "format_ids": ["display_300x250"],
            "property_tags": ["premium_display"],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "non_spec_field": "This field is not in the AdCP spec",  # Should be rejected
        }

        response = {"adcp_version": "1.0.0", "products": [product_with_extra_field]}

        with pytest.raises(SchemaValidationError):
            await validator.validate_response("get-products", response)


class TestRealWorldScenarios:
    """Test realistic product configurations that mirror production usage."""

    @pytest.mark.asyncio
    async def test_premium_homepage_takeover(self, validator):
        """Test premium homepage takeover product configuration."""
        homepage_product = {
            "product_id": "homepage_takeover_premium",
            "name": "Homepage Takeover - Premium",
            "description": "Premium guaranteed placement on homepage with brand lift measurement and co-branding requirements",
            "format_ids": ["display_970x250"],
            "property_tags": ["premium_display"],  # Billboard format
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "cpm": 45.0,
            "min_spend": 5000.0,
            "measurement": {
                "type": "brand_lift",
                "attribution": "deterministic_purchase",
                "window": "30_days",
                "reporting": "real_time_api",
            },
            "creative_policy": {"co_branding": "required", "landing_page": "any", "templates_available": True},
            "is_custom": False,
            "brief_relevance": "Premium homepage placement provides maximum brand visibility with guaranteed impressions and brand lift measurement for your awareness campaign",
        }

        response = {"adcp_version": "1.0.0", "products": [homepage_product]}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_video_preroll_campaign(self, validator):
        """Test video pre-roll product with complete video requirements."""
        video_product = {
            "product_id": "video_preroll_standard",
            "name": "Video Pre-Roll Standard",
            "description": "Standard 15-30 second pre-roll video with completion rate measurement and VAST compliance",
            "format_ids": ["video_preroll_16_9"],
            "property_tags": ["premium_display"],  # Pre-Roll Video 16:9
            "delivery_type": "non_guaranteed",
            "is_fixed_price": False,
            "min_spend": 2000.0,
            "measurement": {
                "type": "video_completion_rate",
                "attribution": "probabilistic",
                "window": "7_days",
                "reporting": "real_time_api",
            },
            "creative_policy": {"co_branding": "optional", "landing_page": "any", "templates_available": False},
            "is_custom": False,
        }

        response = {"adcp_version": "1.0.0", "products": [video_product]}
        await validator.validate_response("get-products", response)
