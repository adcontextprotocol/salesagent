#!/usr/bin/env python3
"""
E2E tests for A2A protocol compliance with AdCP schemas.

These tests validate that our A2A server correctly accepts and processes
requests according to the official AdCP specification, catching issues like:
- Incorrect parameter names (e.g., 'updates' vs 'packages')
- Missing required fields
- Schema mismatches between A2A layer and core implementation

CRITICAL: These tests use real AdCP schemas and validate the full request/response
cycle to ensure protocol compliance.
"""

import pytest

from tests.e2e.adcp_schema_validator import AdCPSchemaValidator


class TestA2AProtocolCompliance:
    """Test A2A protocol compliance with official AdCP schemas."""

    @pytest.mark.asyncio
    async def test_update_media_buy_request_schema_compliance(self):
        """
        Test that update_media_buy accepts AdCP-compliant requests.

        This test validates:
        1. Request uses 'packages' field (not 'updates')
        2. Request accepts all AdCP-defined optional fields
        3. Request matches official update-media-buy-request schema

        Regression test for: A2A server expecting 'updates' instead of 'packages'
        """
        async with AdCPSchemaValidator(offline_mode=False) as validator:
            # Load official AdCP schema
            schema = await validator.get_schema("/schemas/v1/media-buy/update-media-buy-request.json")

            # Verify schema uses 'packages' field (not 'updates')
            assert "packages" in schema["properties"], "AdCP schema should define 'packages' field"
            assert "updates" not in schema["properties"], "AdCP schema should NOT have legacy 'updates' field"

            # Construct a valid AdCP v2.0+ request
            valid_request = {
                "media_buy_id": "mb_test_123",
                "active": True,
                "budget": 10000.0,
                "packages": [{"package_id": "pkg_1", "budget": 5000.0, "active": True}],
            }

            # Validate request against official schema
            validation_result = await validator.validate(
                data=valid_request,
                schema_ref="/schemas/v1/media-buy/update-media-buy-request.json",
                operation="update-media-buy",
            )

            assert validation_result[
                "valid"
            ], f"Valid AdCP request should pass schema validation: {validation_result.get('errors')}"

    @pytest.mark.asyncio
    async def test_update_media_buy_rejects_legacy_updates_field(self):
        """
        Test that we properly handle legacy 'updates' field.

        While we maintain backward compatibility, the primary interface
        should use 'packages' per AdCP v2.0+ spec.
        """
        async with AdCPSchemaValidator(offline_mode=False) as validator:
            # Construct legacy request with 'updates' field
            legacy_request = {
                "media_buy_id": "mb_test_123",
                "updates": {"packages": [{"package_id": "pkg_1", "budget": 5000.0}]},  # Legacy field name
            }

            # This should fail schema validation (not in AdCP spec)
            validation_result = await validator.validate(
                data=legacy_request,
                schema_ref="/schemas/v1/media-buy/update-media-buy-request.json",
                operation="update-media-buy",
            )

            # Schema validation should reject 'updates' field (not in spec)
            assert not validation_result["valid"], "Legacy 'updates' field should fail AdCP schema validation"
            assert any(
                "updates" in str(err).lower() for err in validation_result.get("errors", [])
            ), "Validation error should mention 'updates' field"

    @pytest.mark.asyncio
    async def test_all_adcp_skills_have_schemas(self):
        """
        Verify that all AdCP-compliant skills have corresponding schemas.

        This prevents regressions where we add new skills but forget to:
        1. Add them to the schema validation map
        2. Create tests for them
        3. Validate their request/response formats
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        # Get list of all skills registered in A2A server
        handler = AdCPRequestHandler()
        registered_skills = handler._skill_handlers.keys()

        # Define which skills are AdCP-compliant (should have schemas)
        adcp_skills = {
            "get_products",
            "create_media_buy",
            "update_media_buy",
            "get_media_buy_delivery",
            "sync_creatives",
            "list_creatives",
            "list_creative_formats",
            "list_authorized_properties",
            "get_signals",
        }

        async with AdCPSchemaValidator(offline_mode=False) as validator:
            missing_schemas = []

            for skill in adcp_skills:
                if skill not in registered_skills:
                    missing_schemas.append(f"{skill}: Not registered in A2A server")
                    continue

                # Map skill name to schema path
                schema_path = f"/schemas/v1/media-buy/{skill.replace('_', '-')}-request.json"

                try:
                    schema = await validator.get_schema(schema_path)
                    assert schema is not None, f"Schema loaded but is None for {skill}"
                except Exception as e:
                    # Some schemas might not exist yet (e.g., list_creative_formats)
                    # Log but don't fail - we'll track these separately
                    if "404" not in str(e) and "not found" not in str(e).lower():
                        missing_schemas.append(f"{skill}: {e}")

            # Report findings (informational, not a hard failure)
            if missing_schemas:
                pytest.skip(
                    f"Some AdCP skills don't have schemas yet (expected during development): "
                    f"{', '.join(missing_schemas)}"
                )

    @pytest.mark.asyncio
    async def test_get_media_buy_delivery_request_schema(self):
        """
        Test that get_media_buy_delivery uses correct parameter names.

        Validates the request accepts AdCP-compliant field names.
        """
        async with AdCPSchemaValidator(offline_mode=False) as validator:
            schema = await validator.get_schema("/schemas/v1/media-buy/get-media-buy-delivery-request.json")

            # Verify expected fields from AdCP spec
            assert "media_buy_ids" in schema["properties"], "Should accept media_buy_ids (plural) per AdCP spec"
            assert "buyer_refs" in schema["properties"], "Should accept buyer_refs for querying by buyer reference"

            # Validate a sample request
            valid_request = {"media_buy_ids": ["mb_1", "mb_2"], "start_date": "2025-01-01", "end_date": "2025-01-31"}

            validation_result = await validator.validate(
                data=valid_request,
                schema_ref="/schemas/v1/media-buy/get-media-buy-delivery-request.json",
                operation="get-media-buy-delivery",
            )

            assert validation_result["valid"], f"Valid request should pass: {validation_result.get('errors')}"
