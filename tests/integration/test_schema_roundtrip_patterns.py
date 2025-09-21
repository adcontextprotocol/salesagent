#!/usr/bin/env python3
"""
Schema Roundtrip Test Patterns for All MCP Tools

This module provides reusable test patterns to validate schema roundtrip conversions
across all MCP tools, preventing validation errors like the "formats field required" bug.

Key Patterns Tested:
1. Object → model_dump_internal() → apply_testing_hooks() → Object(**dict)
2. Object → model_dump() → external API validation
3. Database → ORM Model → Schema → API Response
4. AdCP spec compliance after roundtrip conversions

Usage:
    from tests.integration.test_schema_roundtrip_patterns import SchemaRoundtripValidator

    validator = SchemaRoundtripValidator()
    validator.test_model_roundtrip(YourSchema, test_data)
"""

from decimal import Decimal
from typing import Any

import pytest

from src.core.schemas import (
    Budget,
    Creative,
    CreativePolicy,
    Measurement,
    Product,
    Signal,
    SignalDeployment,
    SignalPricing,
    Targeting,
)
from src.core.testing_hooks import TestingContext, apply_testing_hooks


class SchemaRoundtripValidator:
    """Utility class for testing schema roundtrip conversions."""

    def test_model_roundtrip(self, model_class: type, test_data: dict[str, Any]) -> None:
        """
        Test the complete roundtrip pattern for any Pydantic model.

        This tests the pattern that all MCP tools use:
        1. Create model object
        2. Convert to internal dict
        3. Pass through testing hooks
        4. Reconstruct model object
        5. Validate AdCP compliance
        """
        # Step 1: Create original model object
        original_model = model_class(**test_data)

        # Step 2: Convert to internal representation
        internal_dict = original_model.model_dump_internal()

        # Step 3: Simulate testing hooks processing
        testing_ctx = TestingContext(dry_run=True, test_session_id="roundtrip_test")
        response_data = {"items": [internal_dict]}  # Generic container
        processed_response = apply_testing_hooks(response_data, testing_ctx, "test_operation")

        # Step 4: Reconstruct model objects (critical failure point)
        processed_dicts = processed_response["items"]
        reconstructed_models = [model_class(**item) for item in processed_dicts]

        # Step 5: Validate roundtrip preserved data
        assert len(reconstructed_models) == 1
        reconstructed_model = reconstructed_models[0]

        # Step 6: Validate essential fields survived roundtrip
        self._validate_essential_fields(original_model, reconstructed_model)

        # Step 7: Validate AdCP compliance if applicable
        if hasattr(reconstructed_model, "model_dump"):
            adcp_dict = reconstructed_model.model_dump()
            self._validate_adcp_compliance(adcp_dict, model_class)

    def _validate_essential_fields(self, original: Any, reconstructed: Any) -> None:
        """Validate that essential fields survived the roundtrip conversion."""
        # Get all fields from the original model
        original_dict = original.model_dump_internal()
        reconstructed_dict = reconstructed.model_dump_internal()

        # Check that all fields are preserved
        for field_name, original_value in original_dict.items():
            assert field_name in reconstructed_dict, f"Field '{field_name}' lost during roundtrip"
            reconstructed_value = reconstructed_dict[field_name]

            # Handle different comparison types
            if isinstance(original_value, list | dict):
                assert reconstructed_value == original_value, f"Field '{field_name}' value changed during roundtrip"
            elif isinstance(original_value, Decimal):
                # Handle Decimal to float conversions
                assert float(reconstructed_value) == float(
                    original_value
                ), f"Field '{field_name}' numeric value changed during roundtrip"
            else:
                assert reconstructed_value == original_value, f"Field '{field_name}' value changed during roundtrip"

    def _validate_adcp_compliance(self, adcp_dict: dict[str, Any], model_class: type) -> None:
        """Validate that the model output is AdCP spec compliant."""
        # Common AdCP compliance checks
        if model_class == Product:
            # Product-specific AdCP validation
            assert "format_ids" in adcp_dict, "Product must have format_ids for AdCP compliance"
            assert "formats" not in adcp_dict, "Internal 'formats' field should not appear in AdCP output"
            assert isinstance(adcp_dict["format_ids"], list), "format_ids must be a list"

            # Required Product fields per AdCP spec
            required_fields = ["product_id", "name", "description", "delivery_type", "is_fixed_price"]
            for field in required_fields:
                assert field in adcp_dict, f"Required AdCP field '{field}' missing from Product output"

            # Internal fields should be excluded
            internal_fields = ["implementation_config", "expires_at", "targeting_template"]
            for field in internal_fields:
                assert field not in adcp_dict, f"Internal field '{field}' should not appear in AdCP output"


class TestProductSchemaRoundtrip:
    """Comprehensive Product schema roundtrip tests."""

    @pytest.fixture
    def validator(self):
        return SchemaRoundtripValidator()

    def test_guaranteed_product_roundtrip(self, validator):
        """Test roundtrip for guaranteed delivery product."""

        test_data = {
            "product_id": "guaranteed_roundtrip_test",
            "name": "Guaranteed Product Roundtrip Test",
            "description": "Testing guaranteed product roundtrip conversion",
            "formats": ["display_300x250", "display_728x90"],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "cpm": 15.0,
            "min_spend": 2500.0,
            "measurement": Measurement(
                type="brand_lift", attribution="deterministic_purchase", reporting="weekly_dashboard"
            ),
            "creative_policy": CreativePolicy(co_branding="optional", landing_page="any", templates_available=True),
            "is_custom": False,
        }

        validator.test_model_roundtrip(Product, test_data)

    def test_non_guaranteed_product_roundtrip(self, validator):
        """Test roundtrip for non-guaranteed product."""
        test_data = {
            "product_id": "non_guaranteed_roundtrip_test",
            "name": "Non-Guaranteed Product Roundtrip Test",
            "description": "Testing non-guaranteed product roundtrip conversion",
            "formats": ["video_15s", "video_30s"],
            "delivery_type": "non_guaranteed",
            "is_fixed_price": False,
            "cpm": None,  # Test null handling
            "min_spend": 5000.0,
            "is_custom": True,
        }

        validator.test_model_roundtrip(Product, test_data)

    def test_minimal_product_roundtrip(self, validator):
        """Test roundtrip with minimal required fields only."""
        test_data = {
            "product_id": "minimal_roundtrip_test",
            "name": "Minimal Product Roundtrip Test",
            "description": "Testing minimal product with required fields only",
            "formats": ["display_320x50"],
            "delivery_type": "non_guaranteed",
            "is_fixed_price": False,
            "is_custom": False,
        }

        validator.test_model_roundtrip(Product, test_data)

    def test_complex_product_roundtrip(self, validator):
        """Test roundtrip with all optional fields populated."""

        test_data = {
            "product_id": "complex_roundtrip_test",
            "name": "Complex Product Roundtrip Test",
            "description": "Testing complex product with all fields populated",
            "formats": ["display_300x250", "video_15s", "audio_30s"],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "cpm": 25.75,
            "min_spend": 10000.0,
            "measurement": Measurement(
                type="incremental_sales_lift", attribution="probabilistic", window="30_days", reporting="real_time_api"
            ),
            "creative_policy": CreativePolicy(
                co_branding="required", landing_page="retailer_site_only", templates_available=True
            ),
            "is_custom": True,
            "brief_relevance": "Highly relevant for video advertising campaigns",
        }

        validator.test_model_roundtrip(Product, test_data)


class TestCreativeSchemaRoundtrip:
    """Creative schema roundtrip tests."""

    @pytest.fixture
    def validator(self):
        return SchemaRoundtripValidator()

    def test_display_creative_roundtrip(self, validator):
        """Test roundtrip for display creative."""
        test_data = {
            "creative_id": "display_creative_roundtrip",
            "name": "Display Creative Roundtrip Test",
            "format": "display_300x250",
            "status": "pending",
            "url": "https://example.com/creative.jpg",
            "width": 300,
            "height": 250,
            "file_size": "150KB",
            "creative_policy": {"max_file_size": "5MB", "formats": ["jpg", "png", "gif"]},
        }

        validator.test_model_roundtrip(Creative, test_data)

    def test_video_creative_roundtrip(self, validator):
        """Test roundtrip for video creative."""
        test_data = {
            "creative_id": "video_creative_roundtrip",
            "name": "Video Creative Roundtrip Test",
            "format": "video_30s",
            "status": "approved",
            "url": "https://example.com/creative.mp4",
            "width": 1920,
            "height": 1080,
            "duration": 30,
            "file_size": "25MB",
            "creative_policy": {"max_file_size": "100MB", "duration_max": 30},
        }

        validator.test_model_roundtrip(Creative, test_data)


class TestTargetingSchemaRoundtrip:
    """Targeting schema roundtrip tests."""

    @pytest.fixture
    def validator(self):
        return SchemaRoundtripValidator()

    def test_geo_targeting_roundtrip(self, validator):
        """Test roundtrip for geographic targeting."""
        test_data = {
            "geo_country": ["US", "CA", "GB"],
            "geo_region": ["NY", "CA", "TX"],
            "geo_city": ["New York", "Los Angeles", "London"],
        }

        validator.test_model_roundtrip(Targeting, test_data)

    def test_device_targeting_roundtrip(self, validator):
        """Test roundtrip for device targeting."""
        test_data = {
            "device_type_any_of": ["desktop", "mobile", "tablet"],
            "operating_system_any_of": ["iOS", "Android", "Windows"],
            "browser_any_of": ["Chrome", "Safari", "Firefox"],
        }

        validator.test_model_roundtrip(Targeting, test_data)

    def test_complex_targeting_roundtrip(self, validator):
        """Test roundtrip for complex targeting with multiple dimensions."""
        test_data = {
            "geo_country": ["US", "CA"],
            "geo_region": ["NY", "CA"],
            "device_type_any_of": ["desktop", "mobile"],
            "operating_system_any_of": ["iOS", "Android"],
            "browser_any_of": ["Chrome", "Safari"],
            "age_range": {"min": 18, "max": 65},
            "signals": {"contextual_keywords": ["sports", "news"]},
        }

        validator.test_model_roundtrip(Targeting, test_data)


class TestSignalSchemaRoundtrip:
    """Signal schema roundtrip tests."""

    @pytest.fixture
    def validator(self):
        return SchemaRoundtripValidator()

    def test_contextual_signal_roundtrip(self, validator):
        """Test roundtrip for contextual signals."""
        test_data = {
            "signal_id": "contextual_keywords",
            "name": "Contextual Keywords",
            "description": "Keywords extracted from page content",
            "signal_type": "contextual",
            "deployment": SignalDeployment(availability="real_time", latency_ms=50, coverage_percentage=95.0),
            "pricing": SignalPricing(
                pricing_model="cpm_uplift",
                base_cpm_uplift=2.50,
                tier_pricing=[{"tier": "premium", "cpm_uplift": 5.00}, {"tier": "standard", "cpm_uplift": 2.50}],
            ),
        }

        validator.test_model_roundtrip(Signal, test_data)

    def test_audience_signal_roundtrip(self, validator):
        """Test roundtrip for audience signals."""
        test_data = {
            "signal_id": "lookalike_audience",
            "name": "Lookalike Audience",
            "description": "AI-generated lookalike audience segments",
            "signal_type": "audience",
            "deployment": SignalDeployment(availability="batch_daily", latency_ms=None, coverage_percentage=75.0),
            "pricing": SignalPricing(pricing_model="flat_fee", flat_fee_usd=1000.0),
        }

        validator.test_model_roundtrip(Signal, test_data)


class TestBudgetSchemaRoundtrip:
    """Budget schema roundtrip tests."""

    @pytest.fixture
    def validator(self):
        return SchemaRoundtripValidator()

    def test_daily_budget_roundtrip(self, validator):
        """Test roundtrip for daily budget configuration."""
        test_data = {
            "total_budget_usd": 50000.0,
            "daily_budget_usd": 2500.0,
            "pacing": "even",
            "auto_pause_on_budget_exhaustion": True,
        }

        validator.test_model_roundtrip(Budget, test_data)

    def test_total_budget_only_roundtrip(self, validator):
        """Test roundtrip for total budget only (no daily limit)."""
        test_data = {
            "total_budget_usd": 100000.0,
            "pacing": "fast",
            "auto_pause_on_budget_exhaustion": False,
        }

        validator.test_model_roundtrip(Budget, test_data)


class TestRoundtripErrorScenarios:
    """Test scenarios that would cause roundtrip failures."""

    def test_field_name_mismatch_detection(self):
        """Test detection of field name mismatches that cause validation errors."""
        # This simulates the bug where external field names were used in internal dicts
        invalid_product_dict = {
            "product_id": "field_mismatch_test",
            "name": "Field Mismatch Test",
            "description": "Testing field name mismatch detection",
            "format_ids": ["display_300x250"],  # WRONG: External field name in internal dict
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "is_custom": False,
        }

        # This should fail with validation error
        with pytest.raises(ValueError, match="formats"):
            Product(**invalid_product_dict)

    def test_missing_required_field_detection(self):
        """Test detection of missing required fields."""
        incomplete_product_dict = {
            "product_id": "missing_field_test",
            "name": "Missing Field Test",
            # Missing: description, formats, delivery_type, is_fixed_price, is_custom
        }

        # This should fail with validation error for missing required fields
        with pytest.raises(ValueError):
            Product(**incomplete_product_dict)

    def test_type_conversion_issues(self):
        """Test detection of type conversion issues during roundtrip."""
        # Test data with potential type conversion problems
        test_cases = [
            {
                "name": "string_instead_of_list",
                "data": {
                    "product_id": "type_test_1",
                    "name": "Type Test 1",
                    "description": "Testing type conversion",
                    "formats": "display_300x250",  # WRONG: String instead of list
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "is_custom": False,
                },
                "should_fail": True,
            },
            {
                "name": "invalid_enum_value",
                "data": {
                    "product_id": "type_test_2",
                    "name": "Type Test 2",
                    "description": "Testing enum validation",
                    "formats": ["display_300x250"],
                    "delivery_type": "invalid_delivery_type",  # WRONG: Invalid enum value
                    "is_fixed_price": True,
                    "is_custom": False,
                },
                "should_fail": True,
            },
            {
                "name": "negative_pricing",
                "data": {
                    "product_id": "type_test_3",
                    "name": "Type Test 3",
                    "description": "Testing numeric validation",
                    "formats": ["display_300x250"],
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "cpm": -5.0,  # WRONG: Negative CPM
                    "is_custom": False,
                },
                "should_fail": True,
            },
        ]

        for test_case in test_cases:
            if test_case["should_fail"]:
                with pytest.raises(ValueError):
                    Product(**test_case["data"])
            else:
                # Should succeed
                product = Product(**test_case["data"])
                assert product is not None

    def test_roundtrip_with_data_loss_detection(self):
        """Test detection of data loss during roundtrip conversions."""
        # Create a product with all fields
        original_data = {
            "product_id": "data_loss_test",
            "name": "Data Loss Test Product",
            "description": "Testing for data loss during roundtrip",
            "formats": ["display_300x250", "video_15s"],
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "cpm": 20.0,
            "min_spend": 3000.0,
            "measurement": {"viewability": True, "brand_safety": True},
            "creative_policy": {"max_file_size": "15MB"},
            "is_custom": False,
            "brief_relevance": "Test relevance explanation",
        }

        original_product = Product(**original_data)

        # Roundtrip through internal format
        internal_dict = original_product.model_dump_internal()
        reconstructed_product = Product(**internal_dict)

        # Verify no data was lost
        original_internal = original_product.model_dump_internal()
        reconstructed_internal = reconstructed_product.model_dump_internal()

        # Check all fields are preserved
        for field_name, original_value in original_internal.items():
            assert field_name in reconstructed_internal, f"Field '{field_name}' was lost during roundtrip"
            reconstructed_value = reconstructed_internal[field_name]
            assert (
                reconstructed_value == original_value
            ), f"Field '{field_name}' value changed during roundtrip: {original_value} → {reconstructed_value}"
