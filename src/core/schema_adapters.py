"""Schema adapters: Simple API on top of auto-generated schemas.

This module provides thin wrappers around auto-generated schemas that:
1. Import from schemas_generated/ (always in sync with AdCP spec)
2. Provide simple, ergonomic API (like manual schemas)
3. Add custom validators/methods where needed
4. Serve as single import point for all code

Pattern:
- Generated schemas: RootModel[Union[...]] (complex but spec-perfect)
- Adapter schemas: BaseModel (simple API, delegates to generated)

Benefits:
- Always in sync with AdCP spec (auto-regenerate)
- Simple API for application code
- Custom validators/logic added here
- No schema drift bugs
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.core.schemas_generated._schemas_v1_media_buy_get_products_request_json import (
    GetProductsRequest as _GeneratedGetProductsRequest,
)

# Import generated schemas
from src.core.schemas_generated._schemas_v1_media_buy_get_products_request_json import (
    GetProductsRequest1 as _GeneratedGetProductsRequest1,
)
from src.core.schemas_generated._schemas_v1_media_buy_get_products_request_json import (
    GetProductsRequest2 as _GeneratedGetProductsRequest2,
)


class GetProductsRequest(BaseModel):
    """Adapter for GetProductsRequest - simple API on top of generated schema.

    This provides a simple, flat API while using the generated schemas underneath.
    The generated schema uses RootModel[Union[...]] for oneOf, which is spec-compliant
    but complex to use. This adapter hides that complexity.

    Usage:
        # Simple construction (just like manual schemas)
        req = GetProductsRequest(promoted_offering="https://example.com", brief="Video ads")

        # With brand_manifest
        req = GetProductsRequest(
            brand_manifest={"name": "Acme", "url": "https://acme.com"},
            brief="Display ads"
        )

    Under the hood:
        - Converts to correct generated schema variant (GetProductsRequest1 or GetProductsRequest2)
        - Validates against AdCP JSON Schema
        - Provides simple field access (no .root needed)
    """

    # Fields match both generated variants (union of all fields)
    promoted_offering: str | None = Field(
        None, description="DEPRECATED: Use brand_manifest instead. What is being promoted."
    )
    brand_manifest: dict[str, Any] | str | None = Field(
        None, description="Brand information manifest (inline object or URL string)"
    )
    brief: str = Field("", description="Natural language description of campaign requirements")
    adcp_version: str = Field("1.6.0", description="AdCP schema version")
    filters: dict[str, Any] | None = Field(None, description="Structured filters for product discovery")

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_promoted_offering(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Convert promoted_offering to brand_manifest for backward compatibility."""
        if not isinstance(values, dict):
            return values

        # If only promoted_offering provided, convert to brand_manifest
        if values.get("promoted_offering") and not values.get("brand_manifest"):
            # Create minimal brand manifest from promoted_offering
            offering = values["promoted_offering"]
            if isinstance(offering, str) and offering.startswith("http"):
                values["brand_manifest"] = {"url": offering}
            else:
                values["brand_manifest"] = {"name": offering}

        return values

    def to_generated(self) -> _GeneratedGetProductsRequest:
        """Convert to the generated schema for protocol validation.

        This creates the appropriate generated schema variant (GetProductsRequest1 or
        GetProductsRequest2) based on which fields are present.

        Returns:
            Generated schema instance that can be validated against AdCP JSON Schema
        """
        # Determine which variant to use
        if self.promoted_offering and not self.brand_manifest:
            # Use variant 1 (requires promoted_offering)
            variant = _GeneratedGetProductsRequest1(
                promoted_offering=self.promoted_offering,
                brief=self.brief or None,
                adcp_version=self.adcp_version,
                filters=self.filters,
            )
        elif self.brand_manifest:
            # Use variant 2 (requires brand_manifest)
            variant = _GeneratedGetProductsRequest2(
                promoted_offering=self.promoted_offering,
                brand_manifest=self.brand_manifest,
                brief=self.brief or None,
                adcp_version=self.adcp_version,
                filters=self.filters,
            )
        else:
            # Fallback - shouldn't happen due to validator
            raise ValueError("Either promoted_offering or brand_manifest must be provided")

        # Wrap in RootModel
        return _GeneratedGetProductsRequest(root=variant)

    @classmethod
    def from_generated(cls, generated: _GeneratedGetProductsRequest) -> "GetProductsRequest":
        """Create adapter from generated schema.

        Args:
            generated: Generated schema instance (from protocol validation)

        Returns:
            Adapter instance with simple API
        """
        # Extract data from the RootModel union
        data = generated.root.model_dump()

        return cls(**data)

    def model_dump_adcp_compliant(self, **kwargs) -> dict[str, Any]:
        """Dump as AdCP-compliant dict (validates against JSON Schema).

        This converts to generated schema first, ensuring full spec compliance.
        """
        generated = self.to_generated()
        return generated.model_dump(**kwargs)


# Example: How to add this pattern to other schemas
class GetProductsRequestAdapter:
    """Documentation of the adapter pattern for other developers.

    To add an adapter for a new schema:

    1. Import the generated schema(s):
       from src.core.schemas_generated._schemas_v1_... import GeneratedModel

    2. Create adapter class:
       class MyModel(BaseModel):
           # Simple, flat fields
           field1: str
           field2: str | None

           def to_generated(self) -> GeneratedModel:
               # Convert to generated schema
               ...

           @classmethod
           def from_generated(cls, generated: GeneratedModel) -> "MyModel":
               # Convert from generated schema
               ...

    3. Add custom validators/methods:
       @model_validator
       def my_custom_validation(self):
           # Custom logic that can't be in JSON Schema
           ...

    4. Use in code:
       # Construction is simple
       obj = MyModel(field1="value")

       # Protocol validation uses generated
       generated = obj.to_generated()
       validated_data = generated.model_dump()

    Benefits:
    - Application code uses simple API
    - Protocol validation uses spec-compliant generated schema
    - Custom logic added only where needed
    - Automatic sync with AdCP spec (regenerate schemas)
    """

    pass


# TODO: Add adapters for other key models
# - CreateMediaBuyRequest (has timezone validators)
# - CreateMediaBuyResponse (has model_dump_internal)
# - Product (has model_dump_adcp_compliant)
# - Package (has model_dump_internal)
# - Budget (simple, could use generated directly)
# - Targeting (simple, could use generated directly)
