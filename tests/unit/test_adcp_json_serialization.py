"""Test that AdCP responses correctly exclude None values in JSON serialization.

This is critical for client compatibility - the AdCP client (adcp/client npm package)
validates responses against JSON schemas that don't allow null for optional fields.

Issue: PR #xxx - list_authorized_properties returned null for optional fields
Fix: AdCPBaseModel.model_dump_json() now defaults to exclude_none=True
"""

import json

from src.core.schema_adapters import (
    GetProductsResponse,
    ListAuthorizedPropertiesResponse,
    ListCreativeFormatsResponse,
)


def test_list_authorized_properties_excludes_none_in_json():
    """Test that model_dump_json() excludes None values by default.

    This prevents schema validation errors in the AdCP client which expects
    optional fields to be omitted (not set to null).
    """
    # Create response with only required field (all optional fields will be None)
    response = ListAuthorizedPropertiesResponse(publisher_domains=["example.com"])

    # Serialize to JSON
    json_str = response.model_dump_json()
    parsed = json.loads(json_str)

    # Verify None fields are not present in JSON
    assert "publisher_domains" in parsed
    assert "primary_channels" not in parsed  # Should be excluded (None)
    assert "primary_countries" not in parsed  # Should be excluded (None)
    assert "portfolio_description" not in parsed  # Should be excluded (None)
    assert "advertising_policies" not in parsed  # Should be excluded (None)
    assert "last_updated" not in parsed  # Should be excluded (None)
    assert "errors" not in parsed  # Should be excluded (None)


def test_adcp_response_includes_explicit_values():
    """Test that explicitly set values are included in JSON."""
    response = ListAuthorizedPropertiesResponse(
        publisher_domains=["example.com"],
        primary_channels=["display", "video"],
        advertising_policies="No tobacco or alcohol",
    )

    json_str = response.model_dump_json()
    parsed = json.loads(json_str)

    # Verify explicitly set fields are included
    assert parsed["publisher_domains"] == ["example.com"]
    assert parsed["primary_channels"] == ["display", "video"]
    assert parsed["advertising_policies"] == "No tobacco or alcohol"

    # Verify unset fields are still excluded
    assert "primary_countries" not in parsed
    assert "portfolio_description" not in parsed


def test_model_dump_also_excludes_none():
    """Test that model_dump() (dict) also excludes None by default."""
    response = ListAuthorizedPropertiesResponse(publisher_domains=["example.com"])

    dump = response.model_dump()

    # Verify None fields are not present
    assert "publisher_domains" in dump
    assert "primary_channels" not in dump
    assert "primary_countries" not in dump
    assert "portfolio_description" not in dump


def test_other_responses_also_exclude_none():
    """Verify all AdCP response types exclude None values."""
    # GetProductsResponse
    products_resp = GetProductsResponse(products=[])
    products_json = json.loads(products_resp.model_dump_json())
    assert "products" in products_json
    # Should not have None-valued optional fields

    # ListCreativeFormatsResponse
    formats_resp = ListCreativeFormatsResponse(formats=[])
    formats_json = json.loads(formats_resp.model_dump_json())
    assert "formats" in formats_json
    # Should not have None-valued optional fields
