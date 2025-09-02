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
            "formats": [{"format_id": "display_300x250", "name": "Medium Rectangle"}],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
        }

        response = {"products": [minimal_product]}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_comprehensive_product_compliance(self, validator):
        """Test Product with all possible AdCP fields populated."""
        comprehensive_product = {
            "product_id": "test_comprehensive",
            "name": "Comprehensive Product",
            "description": "A product with all AdCP fields populated for testing",
            "formats": [
                {
                    "format_id": "display_300x250",
                    "name": "Medium Rectangle",
                    "type": "display",
                    "is_standard": True,
                    "iab_specification": "IAB Display Standard",
                    "requirements": {
                        "width": 300,
                        "height": 250,
                        "file_types": ["jpg", "png", "gif"],
                        "max_file_size": "150kb",
                    },
                },
                {
                    "format_id": "video_preroll",
                    "name": "Pre-Roll Video",
                    "type": "video",
                    "is_standard": True,
                    "requirements": {
                        "duration_min": 15,
                        "duration_max": 30,
                        "aspect_ratio": "16:9",
                        "codecs": ["H.264", "H.265"],
                    },
                    "assets_required": [
                        {
                            "asset_type": "video_file",
                            "quantity": 1,
                            "requirements": {"format": "mp4", "bitrate_min": 1000, "bitrate_max": 5000},
                        }
                    ],
                },
            ],
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

        response = {"products": [comprehensive_product]}
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
                "formats": [{"format_id": "display_300x250", "name": "Rectangle"}],
                "delivery_type": "guaranteed",
                "is_fixed_price": True,
                "cpm": 15.0,
            },
            {
                "product_id": "non_guaranteed_product",
                "name": "Non-Guaranteed Product",
                "description": "A non-guaranteed delivery product",
                "formats": [{"format_id": "display_728x90", "name": "Leaderboard"}],
                "delivery_type": "non_guaranteed",
                "is_fixed_price": False,
            },
        ]

        response = {"products": products}
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
                    "formats": [{"format_id": "display_300x250", "name": "Rectangle"}],
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "measurement": measurement,
                }
            )

        response = {"products": products}
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
                    "formats": [{"format_id": "display_300x250", "name": "Rectangle"}],
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "creative_policy": policy,
                }
            )

        response = {"products": products}
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
                    "formats": [
                        {
                            "format_id": f"{format_type}_test",
                            "name": f"{format_type.title()} Format",
                            "type": format_type,
                            "is_standard": True,
                        }
                    ],
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                }
            )

        response = {"products": products}
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
                    "requirements": {"min_width": 300, "min_height": 200, "formats": ["jpg", "png"]},
                },
            ],
        }

        product = {
            "product_id": "native_test",
            "name": "Native Test Product",
            "description": "Testing native format with required assets",
            "formats": [format_with_assets],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
        }

        response = {"products": [product]}
        await validator.validate_response("get-products", response)


class TestEdgeCasesAndValidation:
    """Test edge cases and validation rules."""

    @pytest.mark.asyncio
    async def test_empty_products_list(self, validator):
        """Test valid empty products response."""
        response = {"products": []}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_invalid_delivery_type(self, validator):
        """Test that invalid delivery_type is rejected."""
        invalid_product = {
            "product_id": "invalid_delivery",
            "name": "Invalid Product",
            "description": "Product with invalid delivery type",
            "formats": [{"format_id": "display_300x250", "name": "Rectangle"}],
            "delivery_type": "invalid_type",  # Invalid value
            "is_fixed_price": True,
        }

        response = {"products": [invalid_product]}

        with pytest.raises(SchemaValidationError):
            await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_invalid_format_type(self, validator):
        """Test that invalid format type is rejected."""
        invalid_product = {
            "product_id": "invalid_format",
            "name": "Invalid Format Product",
            "description": "Product with invalid format type",
            "formats": [
                {"format_id": "invalid_format", "name": "Invalid Format", "type": "invalid_type"}  # Invalid value
            ],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
        }

        response = {"products": [invalid_product]}

        with pytest.raises(SchemaValidationError):
            await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, validator):
        """Test that missing required fields are rejected."""
        incomplete_product = {
            "product_id": "incomplete",
            "name": "Incomplete Product",
            # Missing required fields: description, formats, delivery_type, is_fixed_price
        }

        response = {"products": [incomplete_product]}

        with pytest.raises(SchemaValidationError):
            await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_additional_properties_rejected(self, validator):
        """Test that additional properties are rejected due to additionalProperties: false."""
        product_with_extra_field = {
            "product_id": "extra_field",
            "name": "Product with Extra Field",
            "description": "This product has an extra field",
            "formats": [{"format_id": "display_300x250", "name": "Rectangle"}],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "non_spec_field": "This field is not in the AdCP spec",  # Should be rejected
        }

        response = {"products": [product_with_extra_field]}

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
            "formats": [
                {
                    "format_id": "display_970x250",
                    "name": "Billboard",
                    "type": "display",
                    "is_standard": True,
                    "iab_specification": "IAB Rising Stars",
                    "requirements": {"width": 970, "height": 250, "max_file_size": "200kb", "animation_length_max": 30},
                }
            ],
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

        response = {"products": [homepage_product]}
        await validator.validate_response("get-products", response)

    @pytest.mark.asyncio
    async def test_video_preroll_campaign(self, validator):
        """Test video pre-roll product with complete video requirements."""
        video_product = {
            "product_id": "video_preroll_standard",
            "name": "Video Pre-Roll Standard",
            "description": "Standard 15-30 second pre-roll video with completion rate measurement and VAST compliance",
            "formats": [
                {
                    "format_id": "video_preroll_16_9",
                    "name": "Pre-Roll Video 16:9",
                    "type": "video",
                    "is_standard": True,
                    "iab_specification": "VAST 4.0",
                    "requirements": {
                        "aspect_ratio": "16:9",
                        "duration_min_seconds": 15,
                        "duration_max_seconds": 30,
                        "bitrate_min": 1500,
                        "bitrate_max": 8000,
                        "codecs": ["H.264", "H.265"],
                        "container": "mp4",
                    },
                    "assets_required": [
                        {
                            "asset_type": "video_file",
                            "quantity": 1,
                            "requirements": {"format": "mp4", "codec": "H.264", "audio_required": True},
                        },
                        {
                            "asset_type": "companion_banner",
                            "quantity": 1,
                            "requirements": {"width": 300, "height": 250, "formats": ["jpg", "png"]},
                        },
                    ],
                }
            ],
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

        response = {"products": [video_product]}
        await validator.validate_response("get-products", response)
