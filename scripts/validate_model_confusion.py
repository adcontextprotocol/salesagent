#!/usr/bin/env python3
"""
Validation script to catch SQLAlchemy/Pydantic model confusion patterns.

This script scans for common patterns that indicate confusion between:
- SQLAlchemy ORM models (from models.py)
- Pydantic models (from schemas.py)

Common issues detected:
1. Using Pydantic methods on SQLAlchemy models
2. Treating relationships as JSON strings
3. Mixed imports without proper naming conventions
"""

import ast
import sys
from pathlib import Path


class ModelConfusionDetector(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.issues: list[dict] = []
        self.imports_from_models: set[str] = set()
        self.imports_from_schemas: set[str] = set()
        self.current_line = 0

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track imports from models and schemas modules."""
        if node.module == "models":
            for alias in node.names:
                self.imports_from_models.add(alias.name)
        elif node.module == "schemas":
            for alias in node.names:
                self.imports_from_schemas.add(alias.name)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        """Check for Pydantic methods being called on SQLAlchemy models."""
        pydantic_methods = {
            "model_validate_json",
            "model_validate",
            "model_dump",
            "model_dump_json",
            "model_fields",
            "model_config",
        }

        if node.attr in pydantic_methods:
            # Check if this is being called on a model imported from models.py
            if isinstance(node.value, ast.Name):
                if node.value.id in self.imports_from_models:
                    self.issues.append(
                        {
                            "type": "pydantic_method_on_sqlalchemy",
                            "line": node.lineno,
                            "message": f"Calling Pydantic method '{node.attr}' on SQLAlchemy model '{node.value.id}'",
                        }
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Check for json.loads on relationship fields."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "json"
            and node.func.attr == "loads"
        ):

            # Check if argument looks like tenant.adapter_config
            if len(node.args) > 0 and isinstance(node.args[0], ast.Attribute):
                arg = node.args[0]
                if isinstance(arg.value, ast.Name) and arg.attr in ["adapter_config", "config"]:
                    self.issues.append(
                        {
                            "type": "json_loads_on_relationship",
                            "line": node.lineno,
                            "message": f"Using json.loads on '{arg.value.id}.{arg.attr}' - may be a relationship, not JSON string",
                        }
                    )
        self.generic_visit(node)


def scan_file(filepath: Path) -> list[dict]:
    """Scan a single Python file for model confusion issues."""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)
        detector = ModelConfusionDetector(str(filepath))
        detector.visit(tree)
        return detector.issues
    except Exception as e:
        return [{"type": "parse_error", "line": 0, "message": f"Failed to parse {filepath}: {e}"}]


def scan_codebase(root_dir: Path) -> dict[str, list[dict]]:
    """Scan entire codebase for model confusion issues."""
    issues_by_file = {}

    # Scan all Python files
    for py_file in root_dir.rglob("*.py"):
        # Skip migrations, __pycache__, and .venv
        if any(skip in str(py_file) for skip in ["alembic", "__pycache__", ".venv", "venv"]):
            continue

        issues = scan_file(py_file)
        if issues:
            issues_by_file[str(py_file)] = issues

    return issues_by_file


def main():
    """Run validation and report issues."""
    root_dir = Path(__file__).parent.parent
    print(f"Scanning codebase at: {root_dir}")

    issues_by_file = scan_codebase(root_dir)

    if not issues_by_file:
        print("✅ No model confusion issues found!")
        return 0

    print(f"❌ Found issues in {len(issues_by_file)} files:")
    print()

    total_issues = 0
    for filename, issues in issues_by_file.items():
        print(f"📄 {filename}:")
        for issue in issues:
            total_issues += 1
            print(f"  Line {issue['line']}: {issue['message']}")
        print()

    print(f"Total issues: {total_issues}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
