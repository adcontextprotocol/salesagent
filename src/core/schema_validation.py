"""
JSON Schema validation utilities for AdCP API responses.

This module provides utilities for including JSON Schema validation information
in both MCP and A2A API responses to ensure protocol compliance and enable
client-side validation.
"""

from typing import Any
from urllib.parse import urljoin

from pydantic import BaseModel


class SchemaMetadata(BaseModel):
    """Metadata about the JSON Schema for API response validation."""

    schema_url: str = None
    schema_version: str = "draft-2020-12"
    adcp_version: str = "2.4"
    response_type: str = None
    validation_enabled: bool = True


class ResponseWithSchema(BaseModel):
    """Base response model that can include schema validation metadata."""

    # Core response data (this will be populated by subclasses)
    # Schema metadata (optional)
    _schema: SchemaMetadata = None

    class Config:
        # Don't include schema metadata in model dump by default
        # It will be added separately to avoid polluting the core response
        exclude = {"_schema"}


def get_model_schema(model_class: type[BaseModel]) -> dict[str, Any]:
    """Generate JSON Schema for a Pydantic model.

    Args:
        model_class: Pydantic model class to generate schema for

    Returns:
        JSON Schema dictionary
    """
    return model_class.model_json_schema()


def get_schema_reference(model_class: type[BaseModel], base_url: str = None) -> str:
    """Generate schema reference URL for a model.

    Args:
        model_class: Pydantic model class
        base_url: Base URL for schema endpoint (defaults to current domain)

    Returns:
        Schema reference URL
    """
    if base_url is None:
        base_url = "https://sales-agent.scope3.com"

    schema_name = model_class.__name__.lower().replace("response", "")
    return urljoin(base_url, f"/schemas/adcp/v2.4/{schema_name}.json")


def create_schema_metadata(model_class: type[BaseModel], base_url: str = None) -> SchemaMetadata:
    """Create schema metadata for a response model.

    Args:
        model_class: Pydantic model class
        base_url: Base URL for schema endpoint

    Returns:
        SchemaMetadata object
    """
    return SchemaMetadata(
        schema_url=get_schema_reference(model_class, base_url),
        response_type=model_class.__name__,
        schema_version="draft-2020-12",
        adcp_version="2.4",
        validation_enabled=True,
    )


def enhance_response_with_schema(
    response_data: dict[str, Any], model_class: type[BaseModel], include_full_schema: bool = False, base_url: str = None
) -> dict[str, Any]:
    """Enhance API response with JSON Schema validation metadata.

    Args:
        response_data: Original response data dictionary
        model_class: Pydantic model class for the response
        include_full_schema: Whether to include the full schema (for development)
        base_url: Base URL for schema references

    Returns:
        Enhanced response with schema metadata
    """
    # Create the enhanced response
    enhanced_response = response_data.copy()

    # Add schema metadata
    schema_metadata = create_schema_metadata(model_class, base_url)
    enhanced_response["$schema"] = schema_metadata.model_dump()

    # Optionally include the full schema for development/debugging
    if include_full_schema:
        enhanced_response["$schema"]["full_schema"] = get_model_schema(model_class)

    return enhanced_response


def enhance_mcp_response_with_schema(
    response_data: dict[str, Any], model_class: type[BaseModel], include_full_schema: bool = False
) -> dict[str, Any]:
    """Enhance MCP tool response with schema validation metadata.

    Args:
        response_data: MCP tool response data
        model_class: Pydantic model class for the response
        include_full_schema: Whether to include full schema

    Returns:
        Enhanced MCP response with schema metadata
    """
    return enhance_response_with_schema(
        response_data=response_data,
        model_class=model_class,
        include_full_schema=include_full_schema,
        base_url="https://sales-agent.scope3.com",
    )


def enhance_a2a_response_with_schema(
    response_data: dict[str, Any], model_class: type[BaseModel], include_full_schema: bool = False
) -> dict[str, Any]:
    """Enhance A2A skill response with schema validation metadata.

    Args:
        response_data: A2A skill response data
        model_class: Pydantic model class for the response
        include_full_schema: Whether to include full schema

    Returns:
        Enhanced A2A response with schema metadata
    """
    # For A2A, we might want to add schema info to the artifact data
    enhanced_response = response_data.copy()

    # Add schema metadata at the top level
    schema_metadata = create_schema_metadata(model_class, "https://sales-agent.scope3.com")
    enhanced_response["$schema"] = schema_metadata.model_dump()

    if include_full_schema:
        enhanced_response["$schema"]["full_schema"] = get_model_schema(model_class)

    return enhanced_response


def validate_response_against_schema(response_data: dict[str, Any], model_class: type[BaseModel]) -> tuple[bool, str]:
    """Validate response data against its Pydantic model schema.

    Args:
        response_data: Response data to validate
        model_class: Pydantic model class to validate against

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Try to create a model instance from the response data
        model_class.model_validate(response_data)
        return True, ""
    except Exception as e:
        return False, str(e)


def create_schema_registry() -> dict[str, dict[str, Any]]:
    """Create a registry of all available schemas for serving via API.

    Returns:
        Dictionary mapping schema names to JSON Schema objects
    """
    from src.core.schemas import (
        CreateMediaBuyResponse,
        GetMediaBuyDeliveryResponse,
        GetProductsResponse,
        GetSignalsResponse,
        ListAuthorizedPropertiesResponse,
        ListCreativeFormatsResponse,
        ListCreativesResponse,
        SyncCreativesResponse,
        UpdateMediaBuyResponse,
        UpdatePerformanceIndexResponse,
    )

    # Core response models to include in schema registry
    response_models = [
        GetProductsResponse,
        ListCreativeFormatsResponse,
        ListAuthorizedPropertiesResponse,
        CreateMediaBuyResponse,
        GetSignalsResponse,
        SyncCreativesResponse,
        ListCreativesResponse,
        UpdateMediaBuyResponse,
        GetMediaBuyDeliveryResponse,
        UpdatePerformanceIndexResponse,
    ]

    schema_registry = {}
    for model_class in response_models:
        schema_name = model_class.__name__.lower().replace("response", "")
        schema_registry[schema_name] = get_model_schema(model_class)

    return schema_registry


# Environment variable to control schema inclusion
INCLUDE_SCHEMAS_IN_RESPONSES = True  # Could be set via environment variable
INCLUDE_FULL_SCHEMAS = False  # For development debugging only
