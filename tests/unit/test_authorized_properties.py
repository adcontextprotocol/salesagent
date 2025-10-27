"""Unit tests for authorized properties functionality."""

import pytest

from src.core.schemas import (
    ListAuthorizedPropertiesRequest,
    ListAuthorizedPropertiesResponse,
    Property,
    PropertyIdentifier,
    PropertyTagMetadata,
)


class TestListAuthorizedPropertiesRequest:
    """Test ListAuthorizedPropertiesRequest schema validation."""

    def test_request_with_minimal_fields(self):
        """Test request with only required fields."""
        request = ListAuthorizedPropertiesRequest()

        # adcp_version removed from AdCP spec
        assert request.tags is None

    def test_request_with_all_fields(self):
        """Test request with all fields."""
        request = ListAuthorizedPropertiesRequest(tags=["premium_content", "news"])

        assert request.tags == ["premium_content", "news"]

    def test_request_normalizes_tags(self):
        """Test that tags are normalized to lowercase with underscores."""
        request = ListAuthorizedPropertiesRequest(tags=["Premium-Content", "News-Sports"])

        assert request.tags == ["premium_content", "news_sports"]

    def test_adcp_compliance(self):
        """Test that ListAuthorizedPropertiesRequest complies with AdCP schema."""
        # Create request with all fields
        request = ListAuthorizedPropertiesRequest(tags=["premium_content", "news"])

        # Test AdCP-compliant response
        adcp_response = request.model_dump()

        # Verify optional AdCP fields present (can be null)
        optional_fields = ["tags", "adcp_version"]
        for field in optional_fields:
            assert field in adcp_response

        # Verify field count matches expectation
        assert len(adcp_response) == 2


class TestProperty:
    """Test Property schema validation."""

    def test_property_with_minimal_fields(self):
        """Test property with only required fields."""
        property_obj = Property(
            property_type="website",
            name="Example Site",
            identifiers=[PropertyIdentifier(type="domain", value="example.com")],
            publisher_domain="example.com",
        )

        assert property_obj.property_type == "website"
        assert property_obj.name == "Example Site"
        assert len(property_obj.identifiers) == 1
        assert property_obj.identifiers[0].type == "domain"
        assert property_obj.identifiers[0].value == "example.com"
        assert property_obj.publisher_domain == "example.com"
        assert property_obj.tags is None

    def test_property_with_all_fields(self):
        """Test property with all fields."""
        property_obj = Property(
            property_type="mobile_app",
            name="Example App",
            identifiers=[
                PropertyIdentifier(type="bundle_id", value="com.example.app"),
                PropertyIdentifier(type="app_store_id", value="123456789"),
            ],
            tags=["mobile", "entertainment"],
            publisher_domain="example.com",
        )

        assert property_obj.property_type == "mobile_app"
        assert property_obj.name == "Example App"
        assert len(property_obj.identifiers) == 2
        assert property_obj.tags == ["mobile", "entertainment"]
        assert property_obj.publisher_domain == "example.com"

    def test_property_model_dump_omits_none_tags(self):
        """Test that model_dump omits tags when None (AdCP spec compliance)."""
        property_obj = Property(
            property_type="website",
            name="Example Site",
            identifiers=[PropertyIdentifier(type="domain", value="example.com")],
            publisher_domain="example.com",
            # tags not set (None)
        )

        data = property_obj.model_dump()
        # Per AdCP spec, optional fields with None values should be omitted
        assert "tags" not in data, "tags with None value should be omitted per AdCP spec"

        # Test that tags are included when explicitly set
        property_with_tags = Property(
            property_type="website",
            name="Example Site",
            identifiers=[PropertyIdentifier(type="domain", value="example.com")],
            publisher_domain="example.com",
            tags=["premium"],
        )
        data_with_tags = property_with_tags.model_dump()
        assert "tags" in data_with_tags, "tags should be present when set"
        assert data_with_tags["tags"] == ["premium"]

    def test_property_requires_at_least_one_identifier(self):
        """Test that property requires at least one identifier."""
        with pytest.raises(ValueError):
            Property(
                property_type="website",
                name="Example Site",
                identifiers=[],  # Empty list should fail
                publisher_domain="example.com",
            )

    def test_invalid_property_type(self):
        """Test that invalid property type raises validation error."""
        with pytest.raises(ValueError):
            Property(
                property_type="invalid_type",
                name="Example Site",
                identifiers=[PropertyIdentifier(type="domain", value="example.com")],
                publisher_domain="example.com",
            )

    def test_property_adcp_compliance(self):
        """Test that Property complies with AdCP property schema."""
        # Create property with all required + optional fields
        property_obj = Property(
            property_type="website",
            name="Example Site",
            identifiers=[PropertyIdentifier(type="domain", value="example.com")],
            tags=["premium_content"],
            publisher_domain="example.com",
        )

        # Test AdCP-compliant response
        adcp_response = property_obj.model_dump()

        # Verify required AdCP fields present and non-null
        required_fields = ["property_type", "name", "identifiers", "publisher_domain"]
        for field in required_fields:
            assert field in adcp_response
            assert adcp_response[field] is not None

        # Verify optional AdCP fields present (can be null)
        optional_fields = ["tags"]
        for field in optional_fields:
            assert field in adcp_response

        # Verify field count expectations
        assert len(adcp_response) == 5  # 4 required + 1 optional


class TestListAuthorizedPropertiesResponse:
    """Test ListAuthorizedPropertiesResponse schema validation."""

    def test_response_with_minimal_fields(self):
        """Test response with only required fields."""
        response = ListAuthorizedPropertiesResponse(publisher_domains=["example.com"])

        assert response.publisher_domains == ["example.com"]
        assert response.tags == {}
        assert response.errors is None

    def test_response_with_all_fields(self):
        """Test response with all fields (per AdCP v2.4 spec)."""
        tag_metadata = PropertyTagMetadata(name="Premium Content", description="Premium content tag")
        response = ListAuthorizedPropertiesResponse(
            publisher_domains=["example.com"],
            tags={"premium_content": tag_metadata},
            errors=[{"code": "WARNING", "message": "Test warning"}],
        )

        assert len(response.publisher_domains) == 1
        assert "premium_content" in response.tags
        assert len(response.errors) == 1

    def test_response_model_dump_omits_none_values(self):
        """Test that model_dump omits None-valued optional fields per AdCP spec."""
        response = ListAuthorizedPropertiesResponse(publisher_domains=["example.com"])

        data = response.model_dump()
        # Per AdCP spec, optional fields with None values should be omitted
        assert "errors" not in data, "errors with None value should be omitted"
        assert "primary_channels" not in data, "primary_channels with None value should be omitted"
        assert "publisher_domains" in data, "Required fields should always be present"

    def test_response_adcp_compliance(self):
        """Test that ListAuthorizedPropertiesResponse complies with AdCP v2.4 schema."""
        # Create response with required fields only (no optional fields set)
        response = ListAuthorizedPropertiesResponse(
            publisher_domains=["example.com"],
            tags={"test": PropertyTagMetadata(name="Test", description="Test tag")},
            # errors not set - should be omitted per AdCP spec
        )

        # Test AdCP-compliant response
        adcp_response = response.model_dump()

        # Verify required AdCP fields present and non-null
        required_fields = ["publisher_domains"]
        for field in required_fields:
            assert field in adcp_response
            assert adcp_response[field] is not None

        # Verify optional fields with None values are omitted per AdCP spec
        assert "errors" not in adcp_response, "errors with None value should be omitted"
        assert "primary_channels" not in adcp_response, "primary_channels with None value should be omitted"
        assert "primary_countries" not in adcp_response, "primary_countries with None value should be omitted"
        assert "portfolio_description" not in adcp_response, "portfolio_description with None value should be omitted"
        assert "advertising_policies" not in adcp_response, "advertising_policies with None value should be omitted"
        assert "last_updated" not in adcp_response, "last_updated with None value should be omitted"

        # Verify field count (only publisher_domains and tags should be present)
        assert len(adcp_response) == 2, f"Expected 2 fields, got {len(adcp_response)}: {list(adcp_response.keys())}"

        # Test with optional fields explicitly set to non-None values
        response_with_optionals = ListAuthorizedPropertiesResponse(
            publisher_domains=["example.com", "example.org"],
            primary_channels=["display", "video"],
            advertising_policies="No tobacco ads",
        )
        adcp_with_optionals = response_with_optionals.model_dump()
        assert "primary_channels" in adcp_with_optionals, "Set optional fields should be present"
        assert "advertising_policies" in adcp_with_optionals, "Set optional fields should be present"
        assert "errors" not in adcp_with_optionals, "Unset optional fields should still be omitted"


class TestPropertyTagMetadata:
    """Test PropertyTagMetadata schema validation."""

    def test_tag_metadata_creation(self):
        """Test basic tag metadata creation."""
        tag = PropertyTagMetadata(name="Premium Content", description="High-quality content properties")

        assert tag.name == "Premium Content"
        assert tag.description == "High-quality content properties"

    def test_tag_metadata_requires_all_fields(self):
        """Test that tag metadata requires all fields."""
        with pytest.raises(ValueError):
            PropertyTagMetadata(name="Test")  # Missing description

        with pytest.raises(ValueError):
            PropertyTagMetadata(description="Test")  # Missing name


class TestPropertyIdentifier:
    """Test PropertyIdentifier schema validation."""

    def test_identifier_creation(self):
        """Test basic identifier creation."""
        identifier = PropertyIdentifier(type="domain", value="example.com")

        assert identifier.type == "domain"
        assert identifier.value == "example.com"

    def test_identifier_requires_all_fields(self):
        """Test that identifier requires all fields."""
        with pytest.raises(ValueError):
            PropertyIdentifier(type="domain")  # Missing value

        with pytest.raises(ValueError):
            PropertyIdentifier(value="example.com")  # Missing type
