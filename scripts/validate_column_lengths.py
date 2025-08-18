#!/usr/bin/env python3
"""
Validate that database column length definitions match between models and constants.
"""
import ast
import os
import re
import sys

# Expected column lengths
COLUMN_LENGTHS = {
    "inventory_type": 30,
    "tenant_id": 50,
    "principal_id": 50,
    "status": 20,
    "name": 200,
    "platform": 50,
}


def extract_string_length(node: ast.AST) -> int | None:
    """Extract length from String(n) or Column(String(n))."""
    if isinstance(node, ast.Call):
        # Check if it's String(...)
        if isinstance(node.func, ast.Name) and node.func.id == "String" and node.args:
            if isinstance(node.args[0], ast.Constant):
                return node.args[0].value
        # Check if it's Column(String(...))
        elif isinstance(node.func, ast.Name) and node.func.id == "Column" and node.args:
            if isinstance(node.args[0], ast.Call):
                return extract_string_length(node.args[0])
    return None


def check_models_file(filepath: str) -> dict[str, dict[str, int]]:
    """Extract column definitions from models.py."""
    columns = {}

    try:
        with open(filepath) as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                columns[class_name] = {}

                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                col_name = target.id
                                length = extract_string_length(item.value)
                                if length:
                                    columns[class_name][col_name] = length

    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return columns


def check_pydantic_schemas(filepath: str) -> dict[str, int]:
    """Extract field constraints from Pydantic schemas."""
    constraints = {}

    try:
        with open(filepath) as f:
            content = f.read()

        # Look for Field(..., max_length=n) or constr(max_length=n)
        max_length_pattern = r"(\w+).*(?:Field|constr)\s*\([^)]*max_length\s*=\s*(\d+)"
        for match in re.finditer(max_length_pattern, content):
            field_name = match.group(1)
            max_length = int(match.group(2))
            constraints[field_name] = max_length

    except Exception:
        pass

    return constraints


def main():
    """Validate all column length definitions."""
    issues = []

    # Check models.py
    models_path = "models.py"
    if os.path.exists(models_path):
        model_columns = check_models_file(models_path)

        for class_name, columns in model_columns.items():
            for col_name, length in columns.items():
                if col_name in COLUMN_LENGTHS:
                    expected = COLUMN_LENGTHS[col_name]
                    if length != expected:
                        issues.append(
                            f"{models_path}: {class_name}.{col_name} has length {length}, " f"expected {expected}"
                        )

    # Check for specific problematic columns
    critical_checks = [
        ("inventory_type", 30, "GAM inventory types can be up to 30 characters"),
        ("tenant_id", 50, "Tenant IDs need sufficient length"),
    ]

    for col_name, min_length, reason in critical_checks:
        found_length = None

        # Search for this column definition
        for root, dirs, files in os.walk("."):
            if any(skip in root for skip in [".git", "__pycache__", ".venv", "alembic/versions"]):
                continue

            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath) as f:
                            content = f.read()

                        # Look for Column(String(n)) where column name matches
                        pattern = rf"{col_name}\s*=\s*Column\s*\(\s*String\s*\(\s*(\d+)\s*\)"
                        match = re.search(pattern, content)
                        if match:
                            found_length = int(match.group(1))
                            if found_length < min_length:
                                issues.append(
                                    f"{filepath}: {col_name} length {found_length} < {min_length} " f"({reason})"
                                )
                    except:
                        pass

    # Check schemas.py for validation
    schemas_path = "schemas.py"
    if os.path.exists(schemas_path):
        schema_constraints = check_pydantic_schemas(schemas_path)

        for field_name, max_length in schema_constraints.items():
            if field_name in COLUMN_LENGTHS:
                expected = COLUMN_LENGTHS[field_name]
                if max_length > expected:
                    issues.append(
                        f"{schemas_path}: {field_name} allows length {max_length}, "
                        f"but database column is only {expected}"
                    )

    if issues:
        print("Column length validation errors:")
        for issue in issues:
            print(f"  {issue}")
        print(f"\nTotal issues: {len(issues)}")
        print("\nPlease update column definitions to match expected lengths.")
        sys.exit(1)
    else:
        print("✓ All column lengths validated successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
