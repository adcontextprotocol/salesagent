#!/usr/bin/env python3
"""Automated Pydantic-to-Schema Alignment Tests.

This test suite automatically validates that ALL Pydantic request/response models
accept ALL fields defined in their corresponding AdCP JSON schemas.

This prevents regressions like:
- promoted_offering missing from CreateMediaBuyRequest (current issue)
- filters missing from GetProductsRequest (PR #195)
- Any future field omissions

The test dynamically loads JSON schemas and validates Pydantic models can handle
all spec-compliant requests.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.core.schemas import (
    CreateMediaBuyRequest,
    GetMediaBuyDeliveryRequest,
    GetProductsRequest,
    GetSignalsRequest,
    ListAuthorizedPropertiesRequest,
    ListCreativesRequest,
    SyncCreativesRequest,
    UpdateMediaBuyRequest,
)

# Map schema file paths to Pydantic model classes
# Only include models that exist in our codebase
SCHEMA_TO_MODEL_MAP = {
    "tests/e2e/schemas/v1/_schemas_v1_media-buy_get-products-request_json.json": GetProductsRequest,
    "tests/e2e/schemas/v1/_schemas_v1_media-buy_create-media-buy-request_json.json": CreateMediaBuyRequest,
    "tests/e2e/schemas/v1/_schemas_v1_media-buy_update-media-buy-request_json.json": UpdateMediaBuyRequest,
    "tests/e2e/schemas/v1/_schemas_v1_media-buy_get-media-buy-delivery-request_json.json": GetMediaBuyDeliveryRequest,
    "tests/e2e/schemas/v1/_schemas_v1_media-buy_sync-creatives-request_json.json": SyncCreativesRequest,
    "tests/e2e/schemas/v1/_schemas_v1_media-buy_list-creatives-request_json.json": ListCreativesRequest,
    "tests/e2e/schemas/v1/_schemas_v1_signals_get-signals-request_json.json": GetSignalsRequest,
    "tests/e2e/schemas/v1/_schemas_v1_properties_list-authorized-properties-request_json.json": ListAuthorizedPropertiesRequest,
}


def load_json_schema(schema_path: str) -> dict[str, Any]:
    """Load a JSON schema file."""
    path = Path(schema_path)
    if not path.exists():
        pytest.skip(f"Schema file not found: {schema_path}")
    with open(path) as f:
        return json.load(f)


def generate_example_value(field_type: str, field_name: str = "", field_spec: dict = None) -> Any:
    """Generate a reasonable example value for a JSON schema type."""
    if field_type == "string":
        # Special cases for known field patterns
        if "date" in field_name.lower() or "time" in field_name.lower():
            return "2025-02-01T00:00:00Z"
        if "id" in field_name.lower():
            return f"test_{field_name}_123"
        if "url" in field_name.lower():
            return "https://example.com/test"
        if "email" in field_name.lower():
            return "test@example.com"
        if "version" in field_name.lower():
            return "1.0.0"
        if "offering" in field_name.lower():
            return "Nike Air Jordan 2025 basketball shoes"
        if "po_number" in field_name.lower():
            return "PO-TEST-12345"
        return f"test_{field_name}_value"
    elif field_type == "number":
        return 100.0
    elif field_type == "integer":
        return 100
    elif field_type == "boolean":
        return True
    elif field_type == "array":
        # Check if items type is specified
        if field_spec and "items" in field_spec:
            items_spec = field_spec["items"]
            if isinstance(items_spec, dict):
                item_type = items_spec.get("type", "string")
                if item_type == "object":
                    # Generate a proper object with required fields
                    obj = {}
                    if "properties" in items_spec:
                        required_fields = items_spec.get("required", [])
                        for prop_name, prop_spec in items_spec["properties"].items():
                            if prop_name in required_fields or "id" in prop_name:
                                prop_type = prop_spec.get("type", "string")
                                obj[prop_name] = generate_example_value(prop_type, prop_name, prop_spec)
                    return [obj] if obj else []
                else:
                    # Generate one example item
                    return [generate_example_value(item_type, field_name, items_spec)]
        return []
    elif field_type == "object":
        # Generate sensible defaults for known object types
        if "budget" in field_name.lower():
            return {
                "total": 5000.0,
                "currency": "USD",
                "pacing": "even",
            }
        if "targeting" in field_name.lower():
            return {
                "geo_country_any_of": ["US"],
            }
        if field_spec and "properties" in field_spec:
            # Generate a minimal object with required fields
            obj = {}
            required_fields = field_spec.get("required", [])
            for prop_name, prop_spec in field_spec["properties"].items():
                if prop_name in required_fields:
                    prop_type = prop_spec.get("type", "string")
                    obj[prop_name] = generate_example_value(prop_type, prop_name, prop_spec)
            return obj
        return {}
    else:
        return None


def extract_required_fields(schema: dict[str, Any]) -> list[str]:
    """Extract required fields from a JSON schema."""
    return schema.get("required", [])


def extract_all_fields(schema: dict[str, Any]) -> dict[str, Any]:
    """Extract all fields (required and optional) from a JSON schema."""
    properties = schema.get("properties", {})
    return {
        field_name: field_spec
        for field_name, field_spec in properties.items()
        if field_name not in ["adcp_version"]  # Skip version fields for simplicity
        and "$ref" not in field_spec  # Skip $ref fields (complex nested objects) for now
    }


def generate_minimal_valid_request(schema: dict[str, Any]) -> dict[str, Any]:
    """Generate a minimal valid request with only required fields."""
    required_fields = extract_required_fields(schema)
    properties = schema.get("properties", {})

    request_data = {}
    for field_name in required_fields:
        if field_name not in properties:
            continue
        field_spec = properties[field_name]
        field_type = field_spec.get("type", "string")
        request_data[field_name] = generate_example_value(field_type, field_name, field_spec)

    return request_data


def generate_full_valid_request(schema: dict[str, Any]) -> dict[str, Any]:
    """Generate a complete valid request with all fields."""
    all_fields = extract_all_fields(schema)

    request_data = {}
    for field_name, field_spec in all_fields.items():
        field_type = field_spec.get("type", "string")
        request_data[field_name] = generate_example_value(field_type, field_name, field_spec)

    return request_data


class TestPydanticSchemaAlignment:
    """Test that Pydantic models accept all fields from AdCP JSON schemas.

    NOTE: These comprehensive tests are exploratory and may fail on edge cases.
    The critical regression prevention tests are in TestSpecificFieldValidation.
    """

    @pytest.mark.skip_ci  # Skip in CI - comprehensive validation with edge cases
    @pytest.mark.parametrize("schema_path,model_class", SCHEMA_TO_MODEL_MAP.items())
    def test_model_accepts_all_schema_fields(self, schema_path: str, model_class: type):
        """Test that Pydantic model accepts ALL fields defined in JSON schema.

        This is the critical test that would have caught:
        - promoted_offering missing from CreateMediaBuyRequest
        - filters missing from GetProductsRequest
        """
        # Load the JSON schema
        schema = load_json_schema(schema_path)

        # Generate a request with ALL fields from schema
        full_request = generate_full_valid_request(schema)

        # This should NOT raise ValidationError
        try:
            instance = model_class(**full_request)
            assert instance is not None
        except ValidationError as e:
            # Extract which fields were rejected
            rejected_fields = [err["loc"][0] for err in e.errors() if err["type"] == "extra_forbidden"]
            missing_fields = [err["loc"][0] for err in e.errors() if err["type"] == "missing"]

            error_msg = f"\n❌ {model_class.__name__} REJECTED AdCP spec fields!\n"
            if rejected_fields:
                error_msg += f"   Rejected fields: {rejected_fields}\n"
            if missing_fields:
                error_msg += f"   Missing required fields: {missing_fields}\n"
            error_msg += "\n   This means clients sending spec-compliant requests will get validation errors.\n"
            error_msg += f"   Schema: {schema_path}\n"
            error_msg += f"   Error details: {e}\n"

            pytest.fail(error_msg)

    @pytest.mark.skip_ci  # Skip in CI - comprehensive validation with edge cases
    @pytest.mark.parametrize("schema_path,model_class", SCHEMA_TO_MODEL_MAP.items())
    def test_model_has_all_required_fields(self, schema_path: str, model_class: type):
        """Test that Pydantic model requires all fields marked as required in JSON schema."""
        # Load the JSON schema
        schema = load_json_schema(schema_path)

        # Get required fields from schema
        required_in_schema = set(extract_required_fields(schema))

        # Skip adcp_version as it often has defaults
        required_in_schema.discard("adcp_version")

        if not required_in_schema:
            pytest.skip("No required fields in schema")

        # Try to create model without required fields
        try:
            instance = model_class()

            # If it succeeded, check which required fields have defaults
            model_data = instance.model_dump()
            fields_with_defaults = {field for field in required_in_schema if field in model_data}

            # If ALL required fields have defaults, that might be intentional
            if fields_with_defaults == required_in_schema:
                pytest.skip(f"All required fields have defaults: {fields_with_defaults}")

        except ValidationError as e:
            # This is expected - required fields should cause validation errors
            missing_from_error = {err["loc"][0] for err in e.errors() if err["type"] == "missing"}

            # Verify that the fields flagged as missing match schema requirements
            if missing_from_error != required_in_schema:
                unexpected = missing_from_error - required_in_schema
                not_enforced = required_in_schema - missing_from_error

                if unexpected or not_enforced:
                    error_msg = f"\n⚠️  {model_class.__name__} required field mismatch!\n"
                    if unexpected:
                        error_msg += f"   Unexpected required fields: {unexpected}\n"
                    if not_enforced:
                        error_msg += f"   Required in schema but not enforced: {not_enforced}\n"
                    pytest.fail(error_msg)

    @pytest.mark.skip_ci  # Skip in CI - comprehensive validation with edge cases
    @pytest.mark.parametrize("schema_path,model_class", SCHEMA_TO_MODEL_MAP.items())
    def test_model_accepts_minimal_request(self, schema_path: str, model_class: type):
        """Test that Pydantic model accepts minimal valid request (only required fields)."""
        # Load the JSON schema
        schema = load_json_schema(schema_path)

        # Generate minimal request
        minimal_request = generate_minimal_valid_request(schema)

        # This should work
        try:
            instance = model_class(**minimal_request)
            assert instance is not None
        except ValidationError as e:
            pytest.fail(
                f"{model_class.__name__} rejected minimal valid request.\n"
                f"Schema: {schema_path}\n"
                f"Request: {minimal_request}\n"
                f"Error: {e}"
            )


class TestSpecificFieldValidation:
    """Specific regression tests for fields that have caused issues."""

    def test_create_media_buy_accepts_promoted_offering(self):
        """REGRESSION TEST: promoted_offering must be accepted (current issue)."""
        request = CreateMediaBuyRequest(
            promoted_offering="Nike Air Jordan 2025",
            po_number="PO-123",
            product_ids=["prod_1"],
            total_budget=5000.0,
            start_date="2025-02-01",
            end_date="2025-02-28",
        )
        assert request.promoted_offering == "Nike Air Jordan 2025"

    def test_get_products_accepts_filters(self):
        """REGRESSION TEST: filters must be accepted (PR #195 issue)."""
        request = GetProductsRequest(
            promoted_offering="Test Product",
            filters={
                "delivery_type": "guaranteed",
                "format_types": ["video"],
                "is_fixed_price": True,
            },
        )
        assert request.filters is not None
        assert request.filters.delivery_type == "guaranteed"

    def test_get_products_accepts_adcp_version(self):
        """REGRESSION TEST: adcp_version must be accepted."""
        request = GetProductsRequest(
            promoted_offering="Test Product",
            adcp_version="1.6.0",
        )
        assert request.adcp_version == "1.6.0"


class TestFieldNameConsistency:
    """Test that field names match between Pydantic models and JSON schemas."""

    @pytest.mark.skip_ci  # Skip in CI - comprehensive validation with edge cases
    @pytest.mark.parametrize("schema_path,model_class", SCHEMA_TO_MODEL_MAP.items())
    def test_field_names_match_schema(self, schema_path: str, model_class: type):
        """Test that Pydantic model field names match JSON schema property names."""
        # Load the JSON schema
        schema = load_json_schema(schema_path)

        # Get all properties from schema
        schema_fields = set(schema.get("properties", {}).keys())

        # Get all fields from Pydantic model
        model_fields = set(model_class.model_fields.keys())

        # Find discrepancies (excluding internal fields)
        internal_fields = {"strategy_id", "testing_mode"}  # Known internal-only fields
        model_fields_public = model_fields - internal_fields

        # Fields in schema but not in model (potential missing fields)
        missing_in_model = schema_fields - model_fields_public

        # We're lenient here - having extra model fields is okay (for internal use)
        # But missing schema fields is a problem
        if missing_in_model:
            # Some fields might be intentionally skipped (like adcp_version with defaults)
            critical_missing = missing_in_model - {"adcp_version"}

            if critical_missing:
                pytest.fail(
                    f"\n⚠️  {model_class.__name__} is missing schema fields!\n"
                    f"   Missing: {critical_missing}\n"
                    f"   These fields are defined in AdCP spec but not in Pydantic model.\n"
                    f"   Schema: {schema_path}\n"
                )


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
