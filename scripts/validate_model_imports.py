#!/usr/bin/env python3
"""
Validate that code imports the correct model types (Pydantic vs SQLAlchemy).
"""
import ast
import os
import sys

# Map of model names to their correct import sources
# Note: Some models exist in both places for different purposes:
# - models.py: SQLAlchemy ORM models for database operations
# - schemas.py: Pydantic models for API validation
MODEL_IMPORT_MAP = {
    # Pydantic models (API/validation)
    "schemas": {
        # API Request/Response models
        "MediaPackage",
        "TargetingOverlay",
        "CreativeAsset",
        "TaskResponse",
        "CreateMediaBuyRequest",
        "UpdateMediaBuyRequest",
        "GetProductsRequest",
        "UploadCreativeRequest",
    },
    # SQLAlchemy ORM models (database)
    "models": {
        "Tenant",
        "GAMInventory",
        "HumanTask",
        "AuditLog",
        "AdapterConfig",
        "SuperadminConfig",
        "User",
        "Task",
        "MediaBuy",  # SQLAlchemy model
        "Base",  # SQLAlchemy base
    },
}

# Models that exist in both locations and can be imported from either
# depending on the use case (database operations vs API)
DUAL_PURPOSE_MODELS = {
    "Principal",  # schemas.py for business logic (get_adapter_id), models.py for DB
    "CreativeFormat",  # schemas.py for API, models.py for DB
    "Product",  # schemas.py for API responses, models.py for DB operations
    "Creative",  # Both places for different purposes
}

# Known issues to check for - empty for now as we handle them more intelligently
KNOWN_ISSUES = []


def get_imports(tree: ast.AST) -> dict[str, set[str]]:
    """Extract all imports from an AST."""
    imports = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                name = alias.name
                if module not in imports:
                    imports[module] = set()
                imports[module].add(name)

    return imports


def check_file(filepath: str) -> list[str]:
    """Check a single file for incorrect model imports."""
    issues = []

    # Skip checking the model files themselves
    if filepath.endswith(("models.py", "schemas.py")):
        return []

    try:
        with open(filepath) as f:
            content = f.read()

        tree = ast.parse(content)
        imports = get_imports(tree)

        # Check for incorrect imports
        for module, expected_models in MODEL_IMPORT_MAP.items():
            wrong_module = "schemas" if module == "models" else "models"

            if wrong_module in imports:
                wrong_imports = imports[wrong_module] & expected_models
                for model in wrong_imports:
                    # Skip dual-purpose models - they can be imported from either
                    if model in DUAL_PURPOSE_MODELS:
                        continue
                    issues.append(f"{filepath}: '{model}' should be imported from '{module}', " f"not '{wrong_module}'")

        # Check for specific known issues
        for known_issue in KNOWN_ISSUES:
            if known_issue["wrong_import"] in content:
                # Check if it's not in a comment
                for line_no, line in enumerate(content.split("\n"), 1):
                    if known_issue["wrong_import"] in line and not line.strip().startswith("#"):
                        issues.append(
                            f"{filepath}:{line_no}: {known_issue['wrong_import']}\n"
                            f"    Should be: {known_issue['correct_import']}\n"
                            f"    Reason: {known_issue['reason']}"
                        )

        # Special check for Principal imports - only flag if get_adapter_id is used
        if "from models import Principal" in content:
            # Check if this file uses get_adapter_id
            if "get_adapter_id" in content:
                # It's using get_adapter_id, so it needs schemas.Principal
                for line_no, line in enumerate(content.split("\n"), 1):
                    if "from models import Principal" in line and not line.strip().startswith("#"):
                        # Check for noqa comment to suppress this warning
                        if "noqa: validate-model-imports" not in line:
                            issues.append(
                                f"{filepath}:{line_no}: from models import Principal\n"
                                f"    Should be: from schemas import Principal\n"
                                f"    Reason: This file uses get_adapter_id() which requires schemas.Principal"
                            )

    except Exception:
        # Skip files that can't be parsed
        pass

    return issues


def check_model_usage(filepath: str) -> list[str]:
    """Check for common model usage errors."""
    issues = []

    try:
        with open(filepath) as f:
            content = f.read()

        # Check for get_adapter_id usage on wrong Principal
        if "get_adapter_id" in content and "Principal" in content:
            tree = ast.parse(content)
            imports = get_imports(tree)

            # Only flag if using get_adapter_id with models.Principal
            # and NOT also importing from schemas (aliasing is OK)
            if "models" in imports and "Principal" in imports["models"]:
                # Check if there's aliasing (e.g., Principal as PrincipalModel)
                if "as PrincipalModel" not in content and "as PrincipalDB" not in content:
                    # Check if schemas.Principal is also imported
                    if not ("schemas" in imports and "Principal" in imports["schemas"]):
                        issues.append(
                            f"{filepath}: Using get_adapter_id() requires Principal from schemas.py, "
                            f"not models.py. Consider using aliasing if you need both."
                        )

    except Exception:
        pass

    return issues


def main():
    """Check all Python files for incorrect model imports."""
    all_issues = []

    exclude_dirs = {".git", "__pycache__", ".venv", "alembic", "scripts"}

    for root, dirs, files in os.walk("."):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        if any(excluded in root for excluded in exclude_dirs):
            continue

        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)

                # Check imports
                import_issues = check_file(filepath)
                all_issues.extend(import_issues)

                # Check usage
                usage_issues = check_model_usage(filepath)
                all_issues.extend(usage_issues)

    if all_issues:
        print("Model import validation errors:")
        for issue in all_issues:
            print(f"\n{issue}")
        print(f"\n\nTotal issues: {len(all_issues)}")
        print("\nPlease use the correct imports for Pydantic (schemas.py) vs SQLAlchemy (models.py) models.")
        sys.exit(1)
    else:
        print("✓ All model imports are correct")
        sys.exit(0)


if __name__ == "__main__":
    main()
