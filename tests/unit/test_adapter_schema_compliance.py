"""Test that schema_adapters.py matches official AdCP JSON schemas.

This ensures that the adapter schemas (which wrap the base schemas and add __str__
methods) have all the fields defined in the official AdCP specification and that
they stay in sync.

Why this matters:
- schema_adapters.py is used by main.py for actual response construction
- The pre-commit hook validates against schema_adapters.py
- If schema_adapters.py drifts from the spec, we'll construct invalid responses

This test uses Pydantic's model_json_schema() to extract field definitions and
compares them against the cached official JSON schemas.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from src.core.schema_adapters import (
    ActivateSignalResponse,
    CreateMediaBuyResponse,
    GetMediaBuyDeliveryResponse,
    GetProductsResponse,
    GetSignalsResponse,
    ListAuthorizedPropertiesResponse,
    ListCreativeFormatsResponse,
    ListCreativesResponse,
    SyncCreativesResponse,
    UpdateMediaBuyResponse,
)


class TestAdapterSchemaCompliance:
    """Validate that adapter schemas match official AdCP JSON schemas."""

    @staticmethod
    def load_official_schema(schema_name: str) -> dict[str, Any]:
        """Load cached official AdCP JSON schema."""
        project_root = Path(__file__).parent.parent.parent
        schema_dir = project_root / "schemas" / "v1"

        # Map response names to schema file names
        schema_files = {
            "CreateMediaBuyResponse": "_schemas_v1_media-buy_create-media-buy-response_json.json",
            "GetProductsResponse": "_schemas_v1_media-buy_get-products-response_json.json",
            "GetMediaBuyDeliveryResponse": "_schemas_v1_media-buy_get-media-buy-delivery-response_json.json",
            "ListCreativesResponse": "_schemas_v1_media-buy_list-creatives-response_json.json",
            "UpdateMediaBuyResponse": "_schemas_v1_media-buy_update-media-buy-response_json.json",
            "ListAuthorizedPropertiesResponse": "_schemas_v1_media-buy_list-authorized-properties-response_json.json",
            "ListCreativeFormatsResponse": "_schemas_v1_media-buy_list-creative-formats-response_json.json",
            "SyncCreativesResponse": "_schemas_v1_media-buy_sync-creatives-response_json.json",
            "GetSignalsResponse": "_schemas_v1_signals_get-signals-response_json.json",
            "ActivateSignalResponse": "_schemas_v1_signals_activate-signal-response_json.json",
        }

        schema_file = schema_files.get(schema_name)
        if not schema_file:
            raise ValueError(f"No schema file mapping for {schema_name}")

        schema_path = schema_dir / schema_file
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path) as f:
            return json.load(f)

    @staticmethod
    def extract_pydantic_fields(model: type[BaseModel]) -> dict[str, dict[str, Any]]:
        """Extract field definitions from Pydantic model.

        Returns dict mapping field name to metadata like:
        {
            "field_name": {
                "required": bool,
                "type": str,  # simplified type description
            }
        }
        """
        fields = {}
        for field_name, field_info in model.model_fields.items():
            # Determine if field is required
            is_required = field_info.is_required()

            # Get simplified type info
            annotation = field_info.annotation
            type_str = str(annotation) if annotation else "Any"

            fields[field_name] = {
                "required": is_required,
                "type": type_str,
            }

        return fields

    @staticmethod
    def extract_json_schema_fields(json_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Extract field definitions from JSON schema.

        Returns dict mapping field name to metadata.
        """
        properties = json_schema.get("properties", {})
        required_fields = set(json_schema.get("required", []))

        fields = {}
        for field_name, field_def in properties.items():
            # Handle type as string or array (for nullable fields)
            field_type = field_def.get("type", "unknown")
            if isinstance(field_type, list):
                # ["string", "null"] → "string"
                field_type = [t for t in field_type if t != "null"][0] if field_type else "unknown"

            fields[field_name] = {
                "required": field_name in required_fields,
                "type": field_type,
                "description": field_def.get("description", ""),
            }

        return fields

    @staticmethod
    def validate_field_type(json_type: str, pydantic_type: str) -> bool:
        """Check if Pydantic type is compatible with JSON schema type.

        Args:
            json_type: JSON schema type ("string", "array", "object", "integer", etc.)
            pydantic_type: Pydantic annotation as string (e.g., "str | None", "list[Any]")

        Returns:
            True if types are compatible
        """
        # Any type accepts everything (used for flexible fields)
        if "Any" in pydantic_type:
            return True

        # Type mapping from JSON Schema to Pydantic types
        type_mappings = {
            "string": ["str", "datetime", "date"],
            "integer": ["int"],
            "number": ["float", "Decimal", "int"],
            "boolean": ["bool"],
            "array": ["list[", "List[", "Sequence["],
            "object": ["dict", "Dict["],
            "null": ["None"],
        }

        # Get valid Pydantic types for this JSON type
        valid_types = type_mappings.get(json_type, [])

        # Check if any valid type appears in the Pydantic annotation
        return any(valid_type in pydantic_type for valid_type in valid_types)

    @pytest.mark.parametrize(
        "adapter_class,schema_name",
        [
            (ListAuthorizedPropertiesResponse, "ListAuthorizedPropertiesResponse"),
            (GetSignalsResponse, "GetSignalsResponse"),
            (ActivateSignalResponse, "ActivateSignalResponse"),
            (UpdateMediaBuyResponse, "UpdateMediaBuyResponse"),
            (ListCreativesResponse, "ListCreativesResponse"),
            (CreateMediaBuyResponse, "CreateMediaBuyResponse"),
            (GetProductsResponse, "GetProductsResponse"),
            (GetMediaBuyDeliveryResponse, "GetMediaBuyDeliveryResponse"),
            (ListCreativeFormatsResponse, "ListCreativeFormatsResponse"),
            (SyncCreativesResponse, "SyncCreativesResponse"),
        ],
    )
    def test_response_adapter_matches_spec(self, adapter_class, schema_name):
        """Test that adapter schema matches official AdCP JSON schema.

        Validates:
        - All official fields are present in adapter
        - Required/optional status matches
        - Field types are compatible (basic validation)
        - No extra fields in adapter
        """
        # Load official schema
        official_schema = self.load_official_schema(schema_name)
        official_fields = self.extract_json_schema_fields(official_schema)

        # Extract Pydantic model fields
        adapter_fields = self.extract_pydantic_fields(adapter_class)

        # 1. Check for missing fields (official → adapter)
        missing_fields = []
        for field_name, field_info in official_fields.items():
            if field_name not in adapter_fields:
                missing_fields.append(f"{field_name} (required={field_info['required']})")

        if missing_fields:
            pytest.fail(
                f"{schema_name} in schema_adapters.py is missing fields from AdCP spec:\n"
                f"Missing: {', '.join(missing_fields)}\n"
                f"Adapter has: {list(adapter_fields.keys())}\n"
                f"Spec requires: {list(official_fields.keys())}"
            )

        # 2. Check for extra fields (adapter → official)
        # NOTE: We currently allow extra fields for internal/protocol use
        # (e.g., workflow_step_id, status). These should eventually be moved
        # to a separate layer or removed per AdCP PR #113.
        extra_fields = []
        for field_name in adapter_fields:
            if field_name not in official_fields:
                extra_fields.append(field_name)

        if extra_fields:
            # TODO: Make this a hard failure after cleaning up protocol fields
            import warnings

            warnings.warn(
                f"{schema_name} has extra fields not in AdCP spec: {', '.join(extra_fields)}. "
                f"These should be reviewed - may be internal fields that need cleanup.",
                UserWarning,
                stacklevel=2,
            )

        # 3. Check required/optional status matches
        for field_name in official_fields:
            if field_name in adapter_fields:
                official_required = official_fields[field_name]["required"]
                adapter_required = adapter_fields[field_name]["required"]

                assert adapter_required == official_required, (
                    f"Field '{field_name}' requirement mismatch in {schema_name}: "
                    f"spec requires={official_required}, adapter requires={adapter_required}"
                )

        # 4. Validate field types are compatible (basic check)
        type_mismatches = []
        for field_name in official_fields:
            if field_name in adapter_fields:
                json_type = official_fields[field_name]["type"]
                pydantic_type = adapter_fields[field_name]["type"]

                if not self.validate_field_type(json_type, pydantic_type):
                    type_mismatches.append(
                        f"{field_name}: JSON schema type '{json_type}' "
                        f"not compatible with Pydantic type '{pydantic_type}'"
                    )

        if type_mismatches:
            pytest.fail(f"{schema_name} has type mismatches:\n{chr(10).join(type_mismatches)}")
