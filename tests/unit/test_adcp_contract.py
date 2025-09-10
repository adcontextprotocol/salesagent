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

from src.core.database.models import (
    Principal as PrincipalModel,
)  # Need both for contract test
from src.core.database.models import Product as ProductModel
from src.core.schemas import (
    Budget,
    CreateMediaBuyRequest,
    Creative,
    CreativeAssignment,
    CreativePolicy,
    CreativeStatus,
    Format,
    GetProductsRequest,
    GetProductsResponse,
    Measurement,
    Package,
    Signal,
    SignalDeployment,
    SignalPricing,
    Targeting,
)
from src.core.schemas import (
    Principal as PrincipalSchema,
)
from src.core.schemas import (
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
            formats=["display_300x250"],  # Now stores format IDs as strings
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

        # Convert to dict (simulating database retrieval and conversion)
        # The validator now ensures formats are stored as strings
        model_dict = {
            "product_id": model.product_id,
            "name": model.name,
            "description": model.description,
            "formats": model.formats,  # Now guaranteed to be strings by validator
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

        # Verify format IDs match AdCP (now strings)
        assert schema.formats[0] == "display_300x250"

    def test_product_non_guaranteed(self):
        """Test non-guaranteed product (AdCP spec compliant - no price_guidance)."""
        model = ProductModel(
            tenant_id="test_tenant",
            product_id="test_ng_product",
            name="Non-Guaranteed Product",
            description="AdCP non-guaranteed product",
            formats=["video_15s"],  # Now stores format IDs as strings
            targeting_template={},
            delivery_type="non_guaranteed",
            is_fixed_price=False,
            cpm=None,
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
            "is_custom": model.is_custom,
            "expires_at": model.expires_at,
        }

        schema = ProductSchema(**model_dict)

        # AdCP spec: non_guaranteed products use auction-based pricing (no price_guidance)
        assert schema.delivery_type == "non_guaranteed"
        assert schema.is_fixed_price is False
        assert schema.cpm is None  # No fixed CPM for non-guaranteed

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

        # Should work without promoted_offering (now optional)
        request_minimal = GetProductsRequest(brief="Just a brief")
        assert request_minimal.promoted_offering is None

    def test_adcp_create_media_buy_request(self):
        """Test AdCP create_media_buy request structure."""
        start_date = datetime.now() + timedelta(days=1)
        end_date = datetime.now() + timedelta(days=30)

        request = CreateMediaBuyRequest(
            product_ids=["product_1", "product_2"],
            total_budget=5000.0,
            start_date=start_date.date(),
            end_date=end_date.date(),
            po_number="PO-12345",  # Required per AdCP spec
            targeting_overlay={
                "geo_country_any_of": ["US", "CA"],
                "device_type_any_of": ["desktop", "mobile"],
                "signals": ["sports_enthusiasts", "auto_intenders"],
            },
        )

        # Verify AdCP requirements
        assert len(request.get_product_ids()) > 0
        assert request.get_total_budget() > 0
        # Also verify backward compatibility
        assert request.get_total_budget() == 5000.0
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
            "is_standard": True,
            "iab_specification": "IAB Native Ad Specification",
            "requirements": {"width": 300, "height": 250},
            # assets_required follows new AdCP spec structure
            "assets_required": [{"asset_type": "image", "quantity": 1, "requirements": {"width": 300, "height": 250}}],
        }

        format_obj = Format(**format_data)

        # AdCP format requirements (new spec structure)
        assert format_obj.format_id is not None
        assert format_obj.type in ["display", "video", "audio", "native", "dooh"]
        assert format_obj.is_standard is True
        assert format_obj.requirements is not None

    def test_field_mapping_consistency(self):
        """Test that field names are consistent between models and schemas."""
        # These fields should map correctly
        model_to_schema_mapping = {
            # Model field -> Schema field (AdCP spec compliant - no price_guidance)
            "product_id": "product_id",
            "name": "name",
            "description": "description",
            "delivery_type": "delivery_type",  # Must be "guaranteed" or "non_guaranteed"
            "is_fixed_price": "is_fixed_price",
            "cpm": "cpm",
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
            total_budget=1000.0,
            start_date=datetime.now().date(),
            end_date=(datetime.now() + timedelta(days=7)).date(),
            po_number="PO-SIGNAL-TEST",  # Required per AdCP spec
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

    def test_creative_adcp_compliance(self):
        """Test that Creative model complies with AdCP creative-asset schema."""
        # Test creating a Creative with required AdCP fields
        creative = Creative(
            creative_id="test_creative_123",
            name="Test AdCP Creative",
            format_id="display_300x250",
            content_uri="https://example.com/creative.jpg",
            click_through_url="https://example.com/landing",
            principal_id="test_principal",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            width=300,
            height=250,
            duration=None,  # Not applicable for display
            status="approved",
            platform_id="platform_abc123",
            review_feedback="Approved for all placements",
        )

        # Test AdCP-compliant model_dump (external response)
        adcp_response = creative.model_dump()

        # Verify required AdCP fields are present
        adcp_required_fields = ["creative_id", "name", "format"]
        for field in adcp_required_fields:
            assert field in adcp_response, f"Required AdCP field '{field}' missing from response"
            assert adcp_response[field] is not None, f"Required AdCP field '{field}' is None"

        # Verify AdCP optional fields are present
        adcp_optional_fields = [
            "url",
            "media_url",
            "click_url",
            "duration",
            "width",
            "height",
            "status",
            "platform_id",
            "review_feedback",
            "compliance",
            "package_assignments",
            "assets",
        ]
        for field in adcp_optional_fields:
            assert field in adcp_response, f"AdCP optional field '{field}' missing from response"

        # Verify internal fields are excluded from AdCP response
        internal_fields = [
            "principal_id",
            "group_id",
            "created_at",
            "updated_at",
            "has_macros",
            "macro_validation",
            "asset_mapping",
            "metadata",
        ]
        for field in internal_fields:
            assert field not in adcp_response, f"Internal field '{field}' exposed in AdCP response"

        # Verify AdCP-specific requirements
        assert adcp_response["media_url"] == adcp_response["url"], "media_url should default to url"
        assert adcp_response["compliance"]["status"] == "pending", "Default compliance status should be 'pending'"
        assert isinstance(adcp_response["compliance"]["issues"], list), "Compliance issues should be a list"
        assert adcp_response["format"] == "display_300x250", "Format should use AdCP field name"

        # Test internal model_dump includes all fields
        internal_response = creative.model_dump_internal()
        for field in internal_fields:
            assert field in internal_response, f"Internal field '{field}' missing from internal response"

        # Verify field count expectations (flexible to allow AdCP spec evolution)
        assert len(adcp_response) >= 12, f"AdCP response should have at least 12 core fields, got {len(adcp_response)}"
        assert len(internal_response) >= len(
            adcp_response
        ), "Internal response should have at least as many fields as external response"

        # Verify internal response has more fields than external (due to internal fields)
        internal_only_fields = set(internal_response.keys()) - set(adcp_response.keys())
        assert (
            len(internal_only_fields) >= 4
        ), f"Expected at least 4 internal-only fields, got {len(internal_only_fields)}"

    def test_signal_adcp_compliance(self):
        """Test that Signal model complies with AdCP get-signals-response schema."""
        # Create signal with all required AdCP fields
        deployment = SignalDeployment(
            platform="google_ad_manager",
            account="123456789",
            is_live=True,
            scope="account-specific",
            decisioning_platform_segment_id="gam_segment_123",
            estimated_activation_duration_minutes=0,
        )

        pricing = SignalPricing(cpm=2.50, currency="USD")

        signal = Signal(
            signal_agent_segment_id="signal_auto_intenders_q1_2025",
            name="Auto Intenders Q1 2025",
            description="Consumers showing purchase intent for automotive products in Q1 2025",
            signal_type="marketplace",
            data_provider="Acme Data Solutions",
            coverage_percentage=85.5,
            deployments=[deployment],
            pricing=pricing,
            tenant_id="test_tenant",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"category": "automotive", "confidence": 0.92},
        )

        # Test AdCP-compliant model_dump (external response)
        adcp_response = signal.model_dump()

        # Verify required AdCP fields are present
        adcp_required_fields = [
            "signal_agent_segment_id",
            "name",
            "description",
            "signal_type",
            "data_provider",
            "coverage_percentage",
            "deployments",
            "pricing",
        ]
        for field in adcp_required_fields:
            assert field in adcp_response, f"Required AdCP field '{field}' missing from response"
            assert adcp_response[field] is not None, f"Required AdCP field '{field}' is None"

        # Verify internal fields are excluded from AdCP response
        internal_fields = ["tenant_id", "created_at", "updated_at", "metadata"]
        for field in internal_fields:
            assert field not in adcp_response, f"Internal field '{field}' exposed in AdCP response"

        # Verify AdCP-specific requirements
        assert adcp_response["signal_type"] in ["marketplace", "custom", "owned"], "signal_type must be valid enum"
        assert 0 <= adcp_response["coverage_percentage"] <= 100, "coverage_percentage must be 0-100"

        # Verify deployments array structure
        assert isinstance(adcp_response["deployments"], list), "deployments must be array"
        assert len(adcp_response["deployments"]) > 0, "deployments array must not be empty"
        deployment_obj = adcp_response["deployments"][0]
        required_deployment_fields = ["platform", "is_live", "scope"]
        for field in required_deployment_fields:
            assert field in deployment_obj, f"Required deployment field '{field}' missing"
        assert deployment_obj["scope"] in ["platform-wide", "account-specific"], "scope must be valid enum"

        # Verify pricing structure
        assert isinstance(adcp_response["pricing"], dict), "pricing must be object"
        assert "cpm" in adcp_response["pricing"], "pricing must have cpm field"
        assert "currency" in adcp_response["pricing"], "pricing must have currency field"
        assert adcp_response["pricing"]["cpm"] >= 0, "cpm must be non-negative"
        assert len(adcp_response["pricing"]["currency"]) == 3, "currency must be 3-letter code"

        # Test backward compatibility properties
        assert signal.signal_id == signal.signal_agent_segment_id, "signal_id property should work"
        assert signal.type == signal.signal_type, "type property should work"

        # Test internal model_dump includes all fields
        internal_response = signal.model_dump_internal()
        for field in internal_fields:
            assert field in internal_response, f"Internal field '{field}' missing from internal response"

        # Verify field count expectations (flexible to allow AdCP spec evolution)
        assert len(adcp_response) >= 8, f"AdCP response should have at least 8 core fields, got {len(adcp_response)}"
        assert len(internal_response) >= len(
            adcp_response
        ), "Internal response should have at least as many fields as external response"

        # Verify internal response has more fields than external (due to internal fields)
        internal_only_fields = set(internal_response.keys()) - set(adcp_response.keys())
        assert (
            len(internal_only_fields) >= 3
        ), f"Expected at least 3 internal-only fields, got {len(internal_only_fields)}"

    def test_package_adcp_compliance(self):
        """Test that Package model complies with AdCP package schema."""
        # Create package with all required AdCP fields and optional fields
        package = Package(
            package_id="pkg_test_123",
            status="active",
            buyer_ref="buyer_ref_abc",
            product_id="product_xyz",
            products=["product_xyz", "product_def"],
            impressions=50000,
            creative_assignments=[
                {"creative_id": "creative_1", "weight": 70},
                {"creative_id": "creative_2", "weight": 30},
            ],
            tenant_id="test_tenant",
            media_buy_id="mb_12345",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"campaign_type": "awareness", "priority": "high"},
        )

        # Test AdCP-compliant model_dump (external response)
        adcp_response = package.model_dump()

        # Verify required AdCP fields are present
        adcp_required_fields = ["package_id", "status"]
        for field in adcp_required_fields:
            assert field in adcp_response, f"Required AdCP field '{field}' missing from response"
            assert adcp_response[field] is not None, f"Required AdCP field '{field}' is None"

        # Verify AdCP optional fields are present (can be null)
        adcp_optional_fields = [
            "buyer_ref",
            "product_id",
            "products",
            "budget",
            "impressions",
            "targeting_overlay",
            "creative_assignments",
        ]
        for field in adcp_optional_fields:
            assert field in adcp_response, f"AdCP optional field '{field}' missing from response"

        # Verify internal fields are excluded from AdCP response
        internal_fields = ["tenant_id", "media_buy_id", "created_at", "updated_at", "metadata"]
        for field in internal_fields:
            assert field not in adcp_response, f"Internal field '{field}' exposed in AdCP response"

        # Verify AdCP-specific requirements
        assert adcp_response["status"] in ["draft", "active", "paused", "completed"], "status must be valid enum"
        if adcp_response.get("impressions") is not None:
            assert adcp_response["impressions"] >= 0, "impressions must be non-negative"

        # Verify creative_assignments structure if present
        if adcp_response.get("creative_assignments"):
            assert isinstance(adcp_response["creative_assignments"], list), "creative_assignments must be array"
            for assignment in adcp_response["creative_assignments"]:
                assert isinstance(assignment, dict), "each creative assignment must be object"

        # Test internal model_dump includes all fields
        internal_response = package.model_dump_internal()
        for field in internal_fields:
            assert field in internal_response, f"Internal field '{field}' missing from internal response"

        # Verify field count expectations (flexible to allow AdCP spec evolution)
        assert len(adcp_response) >= 7, f"AdCP response should have at least 7 core fields, got {len(adcp_response)}"
        assert len(internal_response) >= len(
            adcp_response
        ), "Internal response should have at least as many fields as external response"

        # Verify internal response has more fields than external (due to internal fields)
        internal_only_fields = set(internal_response.keys()) - set(adcp_response.keys())
        assert (
            len(internal_only_fields) >= 3
        ), f"Expected at least 3 internal-only fields, got {len(internal_only_fields)}"

    def test_targeting_adcp_compliance(self):
        """Test that Targeting model complies with AdCP targeting schema."""
        # Create targeting with both public and managed/internal fields
        targeting = Targeting(
            geo_country_any_of=["US", "CA"],
            geo_region_any_of=["CA", "NY"],
            geo_metro_any_of=["803", "501"],
            geo_zip_any_of=["10001", "90210"],
            audiences_any_of=["segment_1", "segment_2"],
            signals=["auto_intenders_q1_2025", "sports_enthusiasts"],
            device_type_any_of=["desktop", "mobile", "tablet"],
            os_any_of=["windows", "macos", "ios", "android"],
            browser_any_of=["chrome", "firefox", "safari"],
            key_value_pairs={"aee_segment": "high_value", "aee_score": "0.85"},  # Managed-only
            tenant_id="test_tenant",  # Internal
            created_at=datetime.now(),  # Internal
            updated_at=datetime.now(),  # Internal
            metadata={"campaign_type": "awareness"},  # Internal
        )

        # Test AdCP-compliant model_dump (external response)
        adcp_response = targeting.model_dump()

        # Verify AdCP fields are present (all targeting fields are optional in AdCP)
        adcp_optional_fields = [
            "geo_country_any_of",
            "geo_region_any_of",
            "geo_metro_any_of",
            "geo_zip_any_of",
            "audiences_any_of",
            "signals",
            "device_type_any_of",
            "os_any_of",
            "browser_any_of",
        ]
        for field in adcp_optional_fields:
            # Field should be in response even if null (AdCP spec pattern)
            if getattr(targeting, field) is not None:
                assert field in adcp_response, f"AdCP optional field '{field}' missing from response"

        # Verify managed and internal fields are excluded from AdCP response
        managed_internal_fields = [
            "key_value_pairs",  # Managed-only field
            "tenant_id",
            "created_at",
            "updated_at",
            "metadata",  # Internal fields
        ]
        for field in managed_internal_fields:
            assert field not in adcp_response, f"Managed/internal field '{field}' exposed in AdCP response"

        # Verify AdCP-specific requirements
        if adcp_response.get("geo_country_any_of"):
            for country in adcp_response["geo_country_any_of"]:
                assert len(country) == 2, "Country codes must be 2-letter ISO codes"

        if adcp_response.get("device_type_any_of"):
            valid_devices = ["desktop", "mobile", "tablet", "connected_tv", "smart_speaker"]
            for device in adcp_response["device_type_any_of"]:
                assert device in valid_devices, f"Invalid device type: {device}"

        if adcp_response.get("os_any_of"):
            valid_os = ["windows", "macos", "ios", "android", "linux", "roku", "tvos", "other"]
            for os in adcp_response["os_any_of"]:
                assert os in valid_os, f"Invalid OS: {os}"

        if adcp_response.get("browser_any_of"):
            valid_browsers = ["chrome", "firefox", "safari", "edge", "other"]
            for browser in adcp_response["browser_any_of"]:
                assert browser in valid_browsers, f"Invalid browser: {browser}"

        # Test internal model_dump includes all fields
        internal_response = targeting.model_dump_internal()
        for field in managed_internal_fields:
            assert field in internal_response, f"Managed/internal field '{field}' missing from internal response"

        # Test managed fields are accessible internally
        assert (
            internal_response["key_value_pairs"]["aee_segment"] == "high_value"
        ), "Managed field should be in internal response"

        # Verify field count expectations (flexible - targeting has many optional fields)
        assert len(adcp_response) >= 9, f"AdCP response should have at least 9 fields, got {len(adcp_response)}"
        assert len(internal_response) >= len(
            adcp_response
        ), "Internal response should have at least as many fields as external response"

        # Verify internal response has more fields than external (due to managed/internal fields)
        internal_only_fields = set(internal_response.keys()) - set(adcp_response.keys())
        assert (
            len(internal_only_fields) >= 4
        ), f"Expected at least 4 internal/managed-only fields, got {len(internal_only_fields)}"

    def test_budget_adcp_compliance(self):
        """Test that Budget model complies with AdCP budget schema."""
        budget = Budget(total=5000.0, currency="USD", daily_cap=250.0, pacing="even")

        # Test model_dump (Budget doesn't have internal fields, so standard dump should be fine)
        adcp_response = budget.model_dump()

        # Verify required AdCP fields are present
        adcp_required_fields = ["total", "currency"]
        for field in adcp_required_fields:
            assert field in adcp_response, f"Required AdCP field '{field}' missing from response"
            assert adcp_response[field] is not None, f"Required AdCP field '{field}' is None"

        # Verify AdCP optional fields are present
        adcp_optional_fields = ["daily_cap", "pacing"]
        for field in adcp_optional_fields:
            assert field in adcp_response, f"AdCP optional field '{field}' missing from response"

        # Verify AdCP-specific requirements
        assert adcp_response["total"] > 0, "Budget total must be positive"
        assert len(adcp_response["currency"]) == 3, "Currency must be 3-letter ISO code"
        assert adcp_response["pacing"] in ["even", "asap", "daily_budget"], "Invalid pacing value"

        # Verify field count (Budget is simple, count should be stable)
        assert len(adcp_response) == 4, f"Budget response should have exactly 4 fields, got {len(adcp_response)}"

    def test_measurement_adcp_compliance(self):
        """Test that Measurement model complies with AdCP measurement schema."""
        measurement = Measurement(
            type="incremental_sales_lift", attribution="deterministic_purchase", window="30_days", reporting="daily"
        )

        # Test model_dump (Measurement doesn't have internal fields)
        adcp_response = measurement.model_dump()

        # Verify required AdCP fields are present
        adcp_required_fields = ["type", "attribution", "reporting"]
        for field in adcp_required_fields:
            assert field in adcp_response, f"Required AdCP field '{field}' missing from response"
            assert adcp_response[field] is not None, f"Required AdCP field '{field}' is None"

        # Verify AdCP optional fields are present
        adcp_optional_fields = ["window"]
        for field in adcp_optional_fields:
            assert field in adcp_response, f"AdCP optional field '{field}' missing from response"

        # Verify field count (Measurement is simple, count should be stable)
        assert len(adcp_response) == 4, f"Measurement response should have exactly 4 fields, got {len(adcp_response)}"

    def test_creative_policy_adcp_compliance(self):
        """Test that CreativePolicy model complies with AdCP creative-policy schema."""
        policy = CreativePolicy(co_branding="required", landing_page="retailer_site_only", templates_available=True)

        # Test model_dump (CreativePolicy doesn't have internal fields)
        adcp_response = policy.model_dump()

        # Verify required AdCP fields are present
        adcp_required_fields = ["co_branding", "landing_page", "templates_available"]
        for field in adcp_required_fields:
            assert field in adcp_response, f"Required AdCP field '{field}' missing from response"
            assert adcp_response[field] is not None, f"Required AdCP field '{field}' is None"

        # Verify AdCP-specific requirements
        assert adcp_response["co_branding"] in ["required", "optional", "none"], "Invalid co_branding value"
        assert adcp_response["landing_page"] in [
            "any",
            "retailer_site_only",
            "must_include_retailer",
        ], "Invalid landing_page value"
        assert isinstance(adcp_response["templates_available"], bool), "templates_available must be boolean"

        # Verify field count (CreativePolicy is simple, count should be stable)
        assert (
            len(adcp_response) == 3
        ), f"CreativePolicy response should have exactly 3 fields, got {len(adcp_response)}"

    def test_creative_status_adcp_compliance(self):
        """Test that CreativeStatus model complies with AdCP creative-status schema."""
        status = CreativeStatus(
            creative_id="creative_123",
            status="approved",
            detail="Creative approved for all placements",
            estimated_approval_time=datetime.now() + timedelta(hours=1),
        )

        # Test model_dump (CreativeStatus doesn't have internal fields currently)
        adcp_response = status.model_dump()

        # Verify required AdCP fields are present
        adcp_required_fields = ["creative_id", "status", "detail"]
        for field in adcp_required_fields:
            assert field in adcp_response, f"Required AdCP field '{field}' missing from response"
            assert adcp_response[field] is not None, f"Required AdCP field '{field}' is None"

        # Verify AdCP optional fields are present
        adcp_optional_fields = ["estimated_approval_time", "suggested_adaptations"]
        for field in adcp_optional_fields:
            assert field in adcp_response, f"AdCP optional field '{field}' missing from response"

        # Verify AdCP-specific requirements
        valid_statuses = ["pending_review", "approved", "rejected", "adaptation_required"]
        assert adcp_response["status"] in valid_statuses, f"Invalid status value: {adcp_response['status']}"

        # Verify field count (flexible - optional fields vary)
        assert (
            len(adcp_response) >= 3
        ), f"CreativeStatus response should have at least 3 core fields, got {len(adcp_response)}"

    def test_creative_assignment_adcp_compliance(self):
        """Test that CreativeAssignment model complies with AdCP creative-assignment schema."""
        assignment = CreativeAssignment(
            assignment_id="assign_123",
            media_buy_id="mb_456",
            package_id="pkg_789",
            creative_id="creative_abc",
            weight=75,
            percentage_goal=60.0,
            rotation_type="weighted",
            override_click_url="https://example.com/override",
            override_start_date=datetime.now(),
            override_end_date=datetime.now() + timedelta(days=7),
        )

        # Test model_dump (CreativeAssignment may have internal fields)
        adcp_response = assignment.model_dump()

        # Verify required AdCP fields are present
        adcp_required_fields = ["assignment_id", "media_buy_id", "package_id", "creative_id"]
        for field in adcp_required_fields:
            assert field in adcp_response, f"Required AdCP field '{field}' missing from response"
            assert adcp_response[field] is not None, f"Required AdCP field '{field}' is None"

        # Verify AdCP optional fields are present
        adcp_optional_fields = [
            "weight",
            "percentage_goal",
            "rotation_type",
            "override_click_url",
            "override_start_date",
            "override_end_date",
            "targeting_overlay",
        ]
        for field in adcp_optional_fields:
            if hasattr(assignment, field) and getattr(assignment, field) is not None:
                assert field in adcp_response, f"AdCP optional field '{field}' missing from response"

        # Verify AdCP-specific requirements
        if adcp_response.get("rotation_type"):
            valid_rotations = ["weighted", "sequential", "even"]
            assert (
                adcp_response["rotation_type"] in valid_rotations
            ), f"Invalid rotation_type: {adcp_response['rotation_type']}"

        if adcp_response.get("weight") is not None:
            assert adcp_response["weight"] >= 0, "Weight must be non-negative"

        if adcp_response.get("percentage_goal") is not None:
            assert 0 <= adcp_response["percentage_goal"] <= 100, "Percentage goal must be 0-100"

        # Verify field count (flexible - optional fields vary)
        assert (
            len(adcp_response) >= 4
        ), f"CreativeAssignment response should have at least 4 core fields, got {len(adcp_response)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
