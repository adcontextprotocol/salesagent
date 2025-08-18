#!/usr/bin/env python3
"""
Check for references to removed database columns in Python code.
"""
import ast
import os
import sys

# Columns that have been removed from the database
REMOVED_COLUMNS = {
    "tenants": ["config"],
    # Add other removed columns here as migrations happen
}

# Files to exclude from checking
EXCLUDE_PATTERNS = [
    "alembic/versions/",
    "__pycache__",
    ".git",
    "test_migration",
    "postmortem",
    "scripts/check_schema_references.py",
    ".venv",
    "docs/",
]


def find_attribute_access(node: ast.AST, target_attrs: set[str]) -> list[tuple[str, int, str]]:
    """Find attribute access matching target attributes."""
    findings = []

    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in target_attrs:
            # Try to get the object name
            obj_name = None
            if isinstance(child.value, ast.Name):
                obj_name = child.value.id
            elif isinstance(child.value, ast.Attribute):
                obj_name = child.value.attr

            if obj_name and any(table in obj_name.lower() for table in REMOVED_COLUMNS.keys()):
                findings.append((child.attr, child.lineno, obj_name))

    return findings


def find_dict_access(node: ast.AST, target_keys: set[str]) -> list[tuple[str, int, str]]:
    """Find dictionary access with target keys."""
    findings = []

    for child in ast.walk(node):
        if isinstance(child, ast.Subscript):
            if isinstance(child.slice, ast.Constant) and child.slice.value in target_keys:
                # Try to get the dict name
                dict_name = None
                if isinstance(child.value, ast.Name):
                    dict_name = child.value.id
                elif isinstance(child.value, ast.Attribute):
                    dict_name = child.value.attr

                if dict_name and any(table in dict_name.lower() for table in REMOVED_COLUMNS.keys()):
                    findings.append((child.slice.value, child.lineno, dict_name))

    return findings


def check_file(filepath: str) -> list[str]:
    """Check a single Python file for removed column references."""
    issues = []

    try:
        with open(filepath) as f:
            content = f.read()

        # Quick string check first
        has_potential_issues = False
        for table, columns in REMOVED_COLUMNS.items():
            for column in columns:
                if column in content:
                    has_potential_issues = True
                    break

        if not has_potential_issues:
            return []

        # Parse AST for detailed analysis
        tree = ast.parse(content)

        # Check all removed columns
        all_removed_attrs = set()
        for columns in REMOVED_COLUMNS.values():
            all_removed_attrs.update(columns)

        # Find attribute access
        attr_findings = find_attribute_access(tree, all_removed_attrs)
        for attr, line, obj in attr_findings:
            issues.append(f"{filepath}:{line}: Accessing removed column '{attr}' on '{obj}'")

        # Find dictionary access
        dict_findings = find_dict_access(tree, all_removed_attrs)
        for key, line, obj in dict_findings:
            issues.append(f"{filepath}:{line}: Accessing removed column '{key}' on '{obj}'")

    except Exception:
        # Silently skip files that can't be parsed
        pass

    return issues


def main():
    """Check all Python files for removed column references."""
    issues = []

    for root, dirs, files in os.walk("."):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not any(pattern in os.path.join(root, d) for pattern in EXCLUDE_PATTERNS)]

        # Skip if current path matches exclude pattern
        if any(pattern in root for pattern in EXCLUDE_PATTERNS):
            continue

        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                file_issues = check_file(filepath)
                issues.extend(file_issues)

    if issues:
        print("Found references to removed database columns:")
        for issue in issues:
            print(f"  {issue}")
        print(f"\nTotal issues: {len(issues)}")
        print("\nPlease update the code to use the new schema.")
        sys.exit(1)
    else:
        print("✓ No references to removed columns found")
        sys.exit(0)


if __name__ == "__main__":
    main()
