"""Test schema adapters - simple API on top of generated schemas.

These tests demonstrate:
1. Adapters provide simple API (like manual schemas)
2. Under the hood, they use generated schemas (spec-compliant)
3. Custom validators still work
4. Backward compatibility is preserved
5. Tests don't break when spec changes (auto-regenerate schemas)
"""


from src.core.schema_adapters import GetProductsRequest


class TestGetProductsRequestAdapter:
    """Test the adapter provides simple API on top of generated schemas."""

    def test_simple_construction_with_brand_manifest(self):
        """Adapter has simple, flat API for construction."""
        req = GetProductsRequest(brand_manifest="https://example.com", brief="Video ads")

        assert req.brand_manifest == "https://example.com"
        assert req.brief == "Video ads"
        assert req.brand_manifest is not None  # Auto-converted

    def test_simple_construction_with_brand_manifest(self):
        """Adapter accepts brand_manifest dict."""
        req = GetProductsRequest(brand_manifest={"name": "Acme Corp", "url": "https://acme.com"}, brief="Display ads")

        assert req.brand_manifest == {"name": "Acme Corp", "url": "https://acme.com"}
        assert req.brief == "Display ads"

    def test_backward_compatibility_brand_manifest(self):
        """Adapter handles legacy brand_manifest field."""
        req = GetProductsRequest(brand_manifest="https://example.com")

        # Auto-converted to brand_manifest
        assert req.brand_manifest is not None
        assert req.brand_manifest == "https://example.com"

    def test_converts_to_generated_schema(self):
        """Adapter converts to generated schema for protocol validation."""
        req = GetProductsRequest(brand_manifest="https://example.com", brief="Video ads")

        # Convert to generated schema (validates against JSON Schema)
        generated = req.to_generated()

        # Generated schema is spec-compliant
        assert generated is not None
        # Can be serialized for protocol
        data = generated.model_dump()
        assert isinstance(data, dict)

    def test_roundtrip_through_generated_schema(self):
        """Adapter survives roundtrip through generated schema."""
        # Start with adapter
        original = GetProductsRequest(
            brand_manifest="https://example.com", brief="Test brief", filters={"format_ids": ["display_300x250"]}
        )

        # Convert to generated (protocol validation)
        generated = original.to_generated()

        # Convert back to adapter
        reconstructed = GetProductsRequest.from_generated(generated)

        # Verify fields preserved
        assert reconstructed.brand_manifest == "https://example.com"
        assert reconstructed.brief == "Test brief"
        # After AdCP PR #123: format_ids are FormatId objects, not strings
        assert len(reconstructed.filters["format_ids"]) == 1
        assert reconstructed.filters["format_ids"][0]["id"] == "display_300x250"
        assert reconstructed.filters["format_ids"][0]["agent_url"]

    def test_adcp_compliant_dump(self):
        """Adapter can dump as AdCP-compliant dict."""
        req = GetProductsRequest(brand_manifest="https://example.com", brief="Video ads")

        # Dump as AdCP-compliant (validates against JSON Schema)
        data = req.model_dump_adcp_compliant()

        assert isinstance(data, dict)
        # Contains valid AdCP fields
        assert "brief" in data or "brand_manifest" in data or "brand_manifest" in data


class TestAdapterBenefitsForTesting:
    """Demonstrate why adapters are better for testing."""

    def test_simple_test_data_construction(self):
        """Tests can use simple API to create test data."""
        # OLD: Complex RootModel[Union[...]] from generated
        # NEW: Simple adapter construction

        req = GetProductsRequest(brand_manifest="https://example.com", brief="Test campaign")

        # Easy assertions
        assert req.brand_manifest == "https://example.com"
        assert req.brief == "Test campaign"

    def test_no_schema_drift_bugs(self):
        """When AdCP spec changes, regenerate schemas and tests still work.

        Example:
        1. AdCP adds new field to GetProductsRequest
        2. Run: python scripts/generate_schemas.py
        3. Generated schemas updated with new field
        4. Adapter automatically gets new field
        5. Tests keep working (backward compatible)
        6. New tests can use new field

        Without adapters:
        1. AdCP adds new field
        2. Manual schema out of date
        3. Tests fail in confusing ways
        4. Manually update schema
        5. Fix all broken tests
        6. Repeat every spec change...
        """
        # This test documents the benefit, doesn't assert behavior
        req = GetProductsRequest(brand_manifest="https://example.com")
        assert req.brand_manifest == "https://example.com"

    def test_custom_validators_still_work(self):
        """Adapters can add custom validators that can't be in JSON Schema."""

        # The adapter has handle_legacy_brand_manifest validator
        # This converts brand_manifest to brand_manifest

        req = GetProductsRequest(brand_manifest="MyBrand")

        # Custom validator ran
        assert req.brand_manifest is not None  # Auto-created
        assert req.brand_manifest["name"] == "MyBrand"


class TestAdapterVsManualSchema:
    """Compare adapter approach vs manual schemas."""

    def test_adapter_api_same_as_manual(self):
        """Adapter API is identical to manual schema API."""
        from src.core.schemas import GetProductsRequest as ManualGetProductsRequest

        # Both have same construction API
        adapter_req = GetProductsRequest(brand_manifest="https://example.com", brief="Test")
        manual_req = ManualGetProductsRequest(brand_manifest="https://example.com", brief="Test")

        # Both have same fields
        assert adapter_req.brand_manifest == manual_req.brand_manifest
        assert adapter_req.brief == manual_req.brief

    def test_adapter_validates_against_spec(self):
        """Adapter uses generated schema, so validates against AdCP JSON Schema."""
        req = GetProductsRequest(brand_manifest="https://example.com")

        # Convert to generated schema (validates against JSON Schema)
        generated = req.to_generated()

        # Generated schema enforces spec exactly
        # If spec changes and we regenerate, this catches drift immediately
        data = generated.model_dump()
        assert isinstance(data, dict)


class TestAdapterPattern:
    """Document the adapter pattern for other developers."""

    def test_adapter_pattern_example(self):
        """Show how to use adapter pattern for other schemas.

        Pattern:
        1. Import generated schema
        2. Create adapter with simple API
        3. Add to_generated() method
        4. Add from_generated() classmethod
        5. Add custom validators/methods

        Result:
        - Application code uses simple adapter
        - Protocol validation uses generated schema
        - Always in sync with AdCP spec
        """
        # Example usage
        req = GetProductsRequest(brand_manifest="https://example.com")

        # Application code: simple API
        assert req.brand_manifest == "https://example.com"

        # Protocol code: generated schema
        generated = req.to_generated()
        protocol_data = generated.model_dump()

        assert isinstance(protocol_data, dict)

    def test_why_not_use_generated_directly(self):
        """Explain why we need adapters instead of using generated directly.

        Generated schemas use RootModel[Union[...]] for oneOf:
        - Spec-compliant: YES
        - Easy to use: NO

        Example:
            generated = GeneratedGetProductsRequest(root=GetProductsRequest1(...))
            data = generated.root.brand_manifest  # Need .root!

        Adapter provides flat API:
            adapter = GetProductsRequest(brand_manifest="...")
            data = adapter.brand_manifest  # Simple!

        Adapter converts to generated for protocol validation:
            generated = adapter.to_generated()
            protocol_data = generated.model_dump()
        """
        req = GetProductsRequest(brand_manifest="https://example.com")

        # Simple flat access (no .root needed)
        assert req.brand_manifest == "https://example.com"

        # Converts to complex generated when needed
        generated = req.to_generated()
        assert generated.root.brand_manifest == "https://example.com"  # Complex but spec-compliant


class TestMigrationStrategy:
    """Document how to migrate codebase to use adapters."""

    def test_step1_use_adapters_in_tests_first(self):
        """Start by using adapters in tests only.

        Benefits:
        - Tests get automatic schema sync
        - No production code changes
        - Prove adapters work
        - Find issues early
        """
        # Test code uses adapter
        req = GetProductsRequest(brand_manifest="https://example.com")

        # Production code still uses manual schema
        from src.core.schemas import GetProductsRequest as ManualReq

        manual = ManualReq(brand_manifest="https://example.com")

        # Both work the same
        assert req.brand_manifest == manual.brand_manifest

    def test_step2_gradual_migration(self):
        """Gradually migrate production code file by file.

        Pattern:
        1. Pick a file to migrate
        2. Change import to use adapter
        3. Run tests
        4. If tests pass, done!
        5. If tests fail, adapter needs work

        No big bang migration needed.
        """
        # NEW: from src.core.schema_adapters import GetProductsRequest
        # OLD: from src.core.schemas import GetProductsRequest

        req = GetProductsRequest(brand_manifest="https://example.com")
        assert req.brand_manifest == "https://example.com"

    def test_step3_deprecate_manual_schemas(self):
        """Eventually, manual schemas.py becomes just re-exports.

        # src/core/schemas.py becomes:
        from src.core.schema_adapters import GetProductsRequest  # Re-export

        Benefits:
        - All imports still work
        - All code uses adapters
        - Schemas auto-sync with spec
        """
        # All imports work the same
        from src.core.schema_adapters import GetProductsRequest as AdapterReq

        req = AdapterReq(brand_manifest="https://example.com")
        assert req.brand_manifest == "https://example.com"
