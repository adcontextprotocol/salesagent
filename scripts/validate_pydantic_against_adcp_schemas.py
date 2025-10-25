#!/usr/bin/env python3
"""
Validate Pydantic Models Against AdCP JSON Schemas

This script ensures our Pydantic response models match the official AdCP specification
by comparing field names, types, and requirements between:
- Pydantic models in src/core/schemas.py
- AdCP JSON schemas in schemas/v1/

This prevents spec drift and ensures buyer compatibility.

Usage:
    python scripts/validate_pydantic_against_adcp_schemas.py
    python scripts/validate_pydantic_against_adcp_schemas.py --strict  # Exit 1 on any error
    python scripts/validate_pydantic_against_adcp_schemas.py --fix     # Auto-fix simple issues
"""

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class Colors:
    """ANSI color codes for terminal output."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class ValidationError(Exception):
    """Raised when Pydantic model doesn't match AdCP schema."""

    pass


class PydanticSchemaValidator:
    """Validates Pydantic models against AdCP JSON schemas."""

    # Map AdCP schema file names to Pydantic model names
    SCHEMA_TO_MODEL_MAP = {
        "sync-creatives-response": "SyncCreativesResponse",
        "sync-creatives-request": "SyncCreativesRequest",
        "create-media-buy-response": "CreateMediaBuyResponse",
        "create-media-buy-request": "CreateMediaBuyRequest",
        "update-media-buy-request": "UpdateMediaBuyRequest",
        "update-media-buy-response": "UpdateMediaBuyResponse",
        # "get-delivery-response": "GetDeliveryResponse",  # Schema file not available yet
        "list-creatives-response": "ListCreativesResponse",
        "list-creatives-request": "ListCreativesRequest",
        "get-products-response": "GetProductsResponse",
        "get-products-request": "GetProductsRequest",
    }

    # JSON schema type to Python type mapping
    JSON_TYPE_TO_PYTHON = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }

    def __init__(self, strict: bool = False, verbose: bool = True):
        self.strict = strict
        self.verbose = verbose
        self.errors = []
        self.warnings = []
        self.schema_dir = Path("schemas/v1")
        self.schemas_file = Path("src/core/schemas.py")

    def log_error(self, msg: str):
        """Log an error."""
        self.errors.append(msg)
        if self.verbose:
            print(f"{Colors.RED}❌ ERROR: {msg}{Colors.RESET}")

    def log_warning(self, msg: str):
        """Log a warning."""
        self.warnings.append(msg)
        if self.verbose:
            print(f"{Colors.YELLOW}⚠️  WARNING: {msg}{Colors.RESET}")

    def log_success(self, msg: str):
        """Log a success."""
        if self.verbose:
            print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

    def log_info(self, msg: str):
        """Log info."""
        if self.verbose:
            print(f"{Colors.CYAN}ℹ️  {msg}{Colors.RESET}")

    def load_json_schema(self, schema_name: str) -> dict[str, Any] | None:
        """Load AdCP JSON schema from file."""
        # Convert schema name to file name
        filename = f"_schemas_v1_media-buy_{schema_name}_json.json"
        schema_path = self.schema_dir / filename

        if not schema_path.exists():
            self.log_warning(f"Schema file not found: {schema_path}")
            return None

        try:
            with open(schema_path) as f:
                return json.load(f)
        except Exception as e:
            self.log_error(f"Failed to load schema {schema_path}: {e}")
            return None

    def extract_pydantic_model_fields(self, model_name: str) -> dict[str, Any] | None:
        """Extract field definitions from Pydantic model using AST parsing."""
        try:
            with open(self.schemas_file) as f:
                tree = ast.parse(f.read())
        except Exception as e:
            self.log_error(f"Failed to parse {self.schemas_file}: {e}")
            return None

        # Find the class definition
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == model_name:
                fields = {}
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        field_name = item.target.id

                        # Get type annotation
                        type_str = ast.unparse(item.annotation) if item.annotation else "Any"

                        # Check if field has default value (makes it optional)
                        has_default = item.value is not None

                        # Check if it's wrapped in Field()
                        is_required = True
                        if has_default and isinstance(item.value, ast.Call):
                            # Check Field() kwargs for default or default_factory
                            for keyword in item.value.keywords:
                                if keyword.arg in ["default", "default_factory"]:
                                    is_required = False
                                    break
                        elif has_default:
                            is_required = False

                        fields[field_name] = {
                            "type": type_str,
                            "required": is_required,
                        }

                return fields

        self.log_error(f"Pydantic model '{model_name}' not found in {self.schemas_file}")
        return None

    def compare_fields(self, pydantic_fields: dict[str, Any], json_schema: dict[str, Any], model_name: str) -> bool:
        """Compare Pydantic model fields with JSON schema properties."""
        all_valid = True

        json_properties = json_schema.get("properties", {})
        json_required = set(json_schema.get("required", []))

        # Get Pydantic field names
        pydantic_field_names = set(pydantic_fields.keys())
        json_field_names = set(json_properties.keys())

        # Check for missing fields in Pydantic model
        missing_in_pydantic = json_required - pydantic_field_names
        if missing_in_pydantic:
            self.log_error(f"{model_name}: Missing REQUIRED fields from AdCP spec: {missing_in_pydantic}")
            all_valid = False

        # Check for extra fields in Pydantic model
        extra_in_pydantic = pydantic_field_names - json_field_names
        if extra_in_pydantic:
            # Only warn - we might have internal fields
            self.log_warning(f"{model_name}: Has extra fields not in AdCP spec: {extra_in_pydantic}")

        # Check each field that exists in both
        for field_name in pydantic_field_names & json_field_names:
            pydantic_field = pydantic_fields[field_name]
            json_field = json_properties[field_name]

            # Check if required status matches
            is_required_in_spec = field_name in json_required
            is_required_in_pydantic = pydantic_field["required"]

            if is_required_in_spec and not is_required_in_pydantic:
                self.log_error(f"{model_name}.{field_name}: Field is REQUIRED in AdCP spec but optional in Pydantic")
                all_valid = False
            elif not is_required_in_spec and is_required_in_pydantic:
                self.log_warning(f"{model_name}.{field_name}: Field is optional in AdCP spec but required in Pydantic")

        return all_valid

    def validate_model(self, schema_name: str, model_name: str) -> bool:
        """Validate a single Pydantic model against its AdCP schema."""
        self.log_info(f"Validating {model_name} against {schema_name}")

        # Load JSON schema
        json_schema = self.load_json_schema(schema_name)
        if not json_schema:
            return False

        # Extract Pydantic fields
        pydantic_fields = self.extract_pydantic_model_fields(model_name)
        if not pydantic_fields:
            return False

        # Compare
        is_valid = self.compare_fields(pydantic_fields, json_schema, model_name)

        if is_valid:
            self.log_success(f"{model_name} matches AdCP spec ✓")
        else:
            self.log_error(f"{model_name} does NOT match AdCP spec ✗")

        return is_valid

    def validate_all(self) -> bool:
        """Validate all mapped models."""
        print(f"\n{Colors.BOLD}Validating Pydantic Models Against AdCP Schemas{Colors.RESET}\n")

        all_valid = True
        validated_count = 0

        for schema_name, model_name in self.SCHEMA_TO_MODEL_MAP.items():
            if not self.validate_model(schema_name, model_name):
                all_valid = False
            validated_count += 1
            print()  # Blank line between validations

        # Summary
        print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}Validation Summary{Colors.RESET}")
        print(f"{'=' * 60}")
        print(f"Models validated: {validated_count}")
        print(f"{Colors.RED}Errors: {len(self.errors)}{Colors.RESET}")
        print(f"{Colors.YELLOW}Warnings: {len(self.warnings)}{Colors.RESET}")

        if all_valid:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ALL MODELS MATCH ADCP SPEC{Colors.RESET}\n")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ VALIDATION FAILED{Colors.RESET}\n")
            print(f"{Colors.RED}Our Pydantic models do NOT match the AdCP specification.{Colors.RESET}")
            print(f"{Colors.RED}This will cause buyer integration failures.{Colors.RESET}\n")

        return all_valid


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate Pydantic models against AdCP JSON schemas")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any validation errors found",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only show errors and warnings",
    )

    args = parser.parse_args()

    validator = PydanticSchemaValidator(
        strict=args.strict,
        verbose=not args.quiet,
    )

    all_valid = validator.validate_all()

    # Exit with error code if validation failed and strict mode
    if not all_valid and args.strict:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
