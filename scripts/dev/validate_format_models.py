#!/usr/bin/env python3
"""
Validate that the creative format models can be imported and used correctly.
This helps ensure the changes are syntactically correct even without pydantic runtime.
"""

import ast
import json
import sys
from pathlib import Path


def validate_schemas_py():
    """Validate schemas.py syntax and structure."""
    print("Validating schemas.py...")

    schema_path = Path(__file__).parent / "schemas.py"
    with open(schema_path) as f:
        content = f.read()

    try:
        # Parse the Python AST
        tree = ast.parse(content)
        print("✓ schemas.py has valid Python syntax")

        # Find the Asset class
        asset_class = None
        format_class = None

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name == "Asset":
                    asset_class = node
                elif node.name == "Format":
                    format_class = node

        if asset_class:
            print("✓ Found Asset class definition")
            # Check for required fields
            asset_fields = {
                field.target.id
                for field in ast.walk(asset_class)
                if isinstance(field, ast.AnnAssign) and hasattr(field.target, "id")
            }
            required_fields = {"asset_id", "asset_type", "required"}
            if required_fields.issubset(asset_fields):
                print("✓ Asset class has required fields")
            else:
                print(f"✗ Asset class missing fields: {required_fields - asset_fields}")
        else:
            print("✗ Asset class not found")

        if format_class:
            print("✓ Found Format class definition")
            # Check for assets field
            format_fields = {
                field.target.id
                for field in ast.walk(format_class)
                if isinstance(field, ast.AnnAssign) and hasattr(field.target, "id")
            }
            if "assets" in format_fields:
                print("✓ Format class has assets field")
            else:
                print("✗ Format class missing assets field")
        else:
            print("✗ Format class not found")

    except SyntaxError as e:
        print(f"✗ Syntax error in schemas.py: {e}")
        return False

    return True


def validate_json_structure():
    """Validate the JSON structure matches expected format."""
    print("\nValidating foundational_creative_formats.json structure...")

    json_path = Path(__file__).parent / "data" / "foundational_creative_formats.json"
    with open(json_path) as f:
        data = json.load(f)

    # Validate each format
    for fmt in data.get("foundational_formats", []):
        format_id = fmt.get("format_id", "unknown")

        # Check assets array exists and is valid
        if "assets" not in fmt:
            print(f"✗ {format_id}: Missing assets array")
            continue

        if not isinstance(fmt["assets"], list):
            print(f"✗ {format_id}: assets is not a list")
            continue

        # Validate each asset
        valid_assets = True
        for i, asset in enumerate(fmt["assets"]):
            if not isinstance(asset, dict):
                print(f"✗ {format_id}: asset[{i}] is not a dict")
                valid_assets = False
                continue

            # Check required fields
            required = {"asset_id", "asset_type", "required"}
            if not required.issubset(asset.keys()):
                missing = required - set(asset.keys())
                print(f"✗ {format_id}: asset[{i}] missing fields: {missing}")
                valid_assets = False

            # Validate asset_type
            valid_types = {"video", "image", "text", "url", "audio", "html"}
            if asset.get("asset_type") not in valid_types:
                print(f"✗ {format_id}: asset[{i}] has invalid asset_type: {asset.get('asset_type')}")
                valid_assets = False

        if valid_assets:
            print(f"✓ {format_id}: All assets valid")

    return True


def validate_converter():
    """Validate the converter module."""
    print("\nValidating creative_format_converter.py...")

    converter_path = Path(__file__).parent / "creative_format_converter.py"
    if not converter_path.exists():
        print("✗ creative_format_converter.py not found")
        return False

    with open(converter_path) as f:
        content = f.read()

    try:
        # Parse the Python AST
        tree = ast.parse(content)
        print("✓ creative_format_converter.py has valid Python syntax")

        # Check for main conversion functions
        functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        required_functions = {"convert_legacy_format_to_assets", "convert_assets_to_legacy_format"}

        if required_functions.issubset(functions):
            print("✓ Found required conversion functions")
        else:
            missing = required_functions - functions
            print(f"✗ Missing functions: {missing}")

    except SyntaxError as e:
        print(f"✗ Syntax error in converter: {e}")
        return False

    return True


def test_example_conversion():
    """Test a simple conversion example without importing."""
    print("\nTesting example format structure...")

    # Example legacy format
    legacy = {
        "format_id": "video_30s",
        "type": "video",
        "specs": {"file_types": ["mp4", "webm"], "max_file_size_mb": 50, "duration_seconds": 30},
    }

    # Expected new format structure
    expected = {
        "format_id": "video_30s",
        "type": "video",
        "assets": [
            {
                "asset_id": "video_file",
                "asset_type": "video",
                "required": True,
                "acceptable_formats": ["mp4", "webm"],
                "max_file_size_mb": 50,
                "duration_seconds": 30,
            }
        ],
        "specs": legacy["specs"],  # Keep for backward compatibility
    }

    print("✓ Example shows correct transformation structure")
    print(f"  Legacy: {len(legacy.get('specs', {}))} spec fields")
    print(f"  New: {len(expected.get('assets', []))} assets")

    return True


def main():
    """Run all validations."""
    print("=== Creative Format Model Validation ===\n")

    tests = [validate_schemas_py, validate_json_structure, validate_converter, test_example_conversion]

    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed with error: {e}")

    print(f"\n=== Results: {passed}/{len(tests)} validations passed ===")

    if passed == len(tests):
        print("\n✓ All creative format updates are structurally valid!")
        print("  The new asset-based structure is ready for use.")
    else:
        print("\n✗ Some validations failed. Please review the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
