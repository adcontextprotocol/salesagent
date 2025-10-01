#!/usr/bin/env python3
"""
Pre-commit hook to check Pydantic model alignment with AdCP JSON schemas.

This script prevents the bug where Pydantic models don't accept all fields
defined in the AdCP specification. It compares Pydantic model fields against
cached AdCP JSON schemas to ensure full compatibility.

Usage:
    python scripts/check_pydantic_adcp_alignment.py

Exit codes:
    0 - All Pydantic models align with AdCP schemas
    1 - Alignment issues found (fields missing or mismatched)
"""

import json
import sys
from pathlib import Path
from typing import Any

# Model to schema mappings
MODEL_SCHEMA_MAPPINGS = {
    "GetProductsRequest": "tests/e2e/schemas/v1/_schemas_v1_media-buy_get-products-request_json.json",
    # Add more mappings as needed:
    # "CreateMediaBuyRequest": "tests/e2e/schemas/v1/_schemas_v1_media-buy_create-media-buy-request_json.json",
    # "UpdateMediaBuyRequest": "tests/e2e/schemas/v1/_schemas_v1_media-buy_update-media-buy-request_json.json",
}


def load_json_schema(schema_path: str) -> dict[str, Any]:
    """Load and parse JSON schema file."""
    full_path = Path(__file__).parent.parent / schema_path
    if not full_path.exists():
        print(f"⚠️  Warning: Schema file not found: {schema_path}")
        return {}

    with open(full_path) as f:
        return json.load(f)


def extract_schema_fields(schema: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Extract required and optional fields from JSON schema.

    Returns:
        (required_fields, all_fields)
    """
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    all_fields = set(properties.keys())

    return required, all_fields


def extract_pydantic_fields(model_name: str) -> tuple[set[str], set[str], dict[str, str]]:
    """Extract fields from Pydantic model by parsing schemas.py.

    Returns:
        (required_fields, all_fields, field_types)
    """
    schemas_file = Path(__file__).parent.parent / "src" / "core" / "schemas.py"

    with open(schemas_file) as f:
        content = f.read()

    # Find the model class definition
    class_marker = f"class {model_name}(BaseModel):"
    if class_marker not in content:
        print(f"⚠️  Warning: Model {model_name} not found in schemas.py")
        return set(), set(), {}

    # Extract class definition
    start_idx = content.index(class_marker)
    # Find next class or end of file
    remaining = content[start_idx + len(class_marker) :]
    next_class = remaining.find("\nclass ")
    if next_class == -1:
        class_content = remaining
    else:
        class_content = remaining[:next_class]

    # Parse field definitions
    required_fields = set()
    all_fields = set()
    field_types = {}

    for line in class_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith('"""'):
            continue

        # Match field definitions like: field_name: type = Field(...)
        # or: field_name: type
        if ":" in line and not line.startswith("def "):
            parts = line.split(":")
            if len(parts) >= 2:
                field_name = parts[0].strip()
                type_and_default = parts[1].strip()

                # Extract type (before = or end of line)
                if "=" in type_and_default:
                    field_type = type_and_default.split("=")[0].strip()
                    default_value = type_and_default.split("=", 1)[1].strip()

                    # Check if field is required (no default or default is ...)
                    is_required = default_value.startswith("...") or default_value == "Field(...)"

                    if is_required:
                        required_fields.add(field_name)
                else:
                    field_type = type_and_default.strip()
                    # No default value means required
                    required_fields.add(field_name)

                all_fields.add(field_name)
                field_types[field_name] = field_type

    return required_fields, all_fields, field_types


def check_field_type_compatibility(pydantic_type: str, json_schema_type: Any) -> bool:
    """Check if Pydantic type is compatible with JSON schema type.

    This is a simplified check - comprehensive type validation would be more complex.
    """
    # Handle JSON schema type definitions
    if isinstance(json_schema_type, str):
        schema_type = json_schema_type
    elif isinstance(json_schema_type, dict):
        schema_type = json_schema_type.get("type", "")
    else:
        return True  # Can't validate complex types easily

    # Basic type mappings
    type_mappings = {
        "string": ["str"],
        "number": ["float", "int", "Decimal"],
        "integer": ["int"],
        "boolean": ["bool"],
        "array": ["list", "List"],
        "object": ["dict", "Dict", "BaseModel"],
    }

    # Check if Pydantic type matches JSON schema type
    if schema_type in type_mappings:
        expected_types = type_mappings[schema_type]
        # Special handling for object types - accept custom Pydantic models
        if schema_type == "object":
            # Accept dict, Dict, BaseModel, or custom model types (capitalized names)
            if any(t in pydantic_type for t in ["dict", "Dict", "BaseModel"]):
                return True
            # Check if it's a custom Pydantic model (capitalized type name like "ProductFilters")
            words = [w for w in pydantic_type.replace("|", " ").split() if w and w != "None"]
            if any(word[0].isupper() for word in words):
                return True
        return any(expected in pydantic_type for expected in expected_types)

    return True  # Default to compatible for unknown types


def check_model_alignment(model_name: str, schema_path: str) -> list[str]:
    """Check if a Pydantic model aligns with its AdCP JSON schema.

    Returns:
        List of error messages (empty if aligned)
    """
    errors = []

    # Load JSON schema
    schema = load_json_schema(schema_path)
    if not schema:
        return [f"Could not load schema: {schema_path}"]

    # Extract fields
    schema_required, schema_all = extract_schema_fields(schema)
    pydantic_required, pydantic_all, pydantic_types = extract_pydantic_fields(model_name)

    # Check for missing fields in Pydantic model
    missing_optional = schema_all - pydantic_all
    if missing_optional:
        errors.append(
            f"  ❌ {model_name} missing optional fields from AdCP spec: {', '.join(sorted(missing_optional))}"
        )

    # Check for required field mismatches
    # Note: Pydantic can have more required fields than schema (stricter validation)
    missing_required = schema_required - pydantic_all
    if missing_required:
        errors.append(
            f"  ❌ {model_name} missing REQUIRED fields from AdCP spec: {', '.join(sorted(missing_required))}"
        )

    # Check for extra fields in Pydantic (not in schema)
    # These are allowed if they're internal/optional fields
    extra_fields = pydantic_all - schema_all
    if extra_fields:
        # Filter out known internal fields
        internal_fields = {"strategy_id"}  # Add known internal fields here
        unexpected_extra = extra_fields - internal_fields
        if unexpected_extra:
            errors.append(f"  ℹ️  {model_name} has extra fields not in AdCP spec: {', '.join(sorted(unexpected_extra))}")

    # Type compatibility check (basic)
    schema_props = schema.get("properties", {})
    for field in pydantic_all & schema_all:  # Common fields
        if field in pydantic_types and field in schema_props:
            pydantic_type = pydantic_types[field]
            schema_type = schema_props[field].get("type")

            if not check_field_type_compatibility(pydantic_type, schema_type):
                errors.append(
                    f"  ⚠️  {model_name}.{field}: type mismatch - "
                    f"Pydantic='{pydantic_type}' vs Schema='{schema_type}'"
                )

    return errors


def main() -> int:
    """Run alignment checks on all models."""
    print("=" * 60)
    print("Checking Pydantic Model Alignment with AdCP Schemas")
    print("=" * 60)

    all_errors = []

    for model_name, schema_path in MODEL_SCHEMA_MAPPINGS.items():
        print(f"\nChecking {model_name}...")
        errors = check_model_alignment(model_name, schema_path)

        if errors:
            all_errors.extend(errors)
            for error in errors:
                print(error)
        else:
            print(f"  ✓ {model_name} aligns with AdCP schema")

    print("\n" + "=" * 60)
    if all_errors:
        print(f"❌ FAILED: Found {len(all_errors)} alignment issues")
        print("\nAction Required:")
        print("  1. Update Pydantic models in src/core/schemas.py")
        print("  2. Add missing fields with appropriate defaults")
        print("  3. Run tests: pytest tests/unit/test_pydantic_adcp_alignment.py")
        print("=" * 60)
        return 1
    else:
        print("✓ SUCCESS: All models align with AdCP schemas")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
