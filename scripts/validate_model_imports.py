#!/usr/bin/env python3
"""
Validate that code imports the correct model types (Pydantic vs SQLAlchemy).
"""
import ast
import os
import sys
from typing import Set, Dict, List


# Map of model names to their correct import sources
MODEL_IMPORT_MAP = {
    # Pydantic models (API/validation)
    'schemas': {
        'Principal',  # Has get_adapter_id() method
        'MediaBuy',
        'MediaPackage',
        'TargetingOverlay',
        'CreativeFormat',
        'CreativeAsset',
        'TaskResponse',
        'CreateMediaBuyRequest',
        'UpdateMediaBuyRequest',
        'GetProductsRequest',
        'UploadCreativeRequest',
    },
    # SQLAlchemy ORM models (database)
    'models': {
        'Tenant',
        'GAMInventory',
        'Product',
        'Creative',
        'HumanTask',
        'AuditLog',
        'Base',  # SQLAlchemy base
    }
}

# Known issues to check for
KNOWN_ISSUES = [
    {
        'model': 'Principal',
        'wrong_import': 'from models import Principal',
        'correct_import': 'from schemas import Principal',
        'reason': 'Principal with get_adapter_id() method is in schemas.py'
    }
]


def get_imports(tree: ast.AST) -> Dict[str, Set[str]]:
    """Extract all imports from an AST."""
    imports = {}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for alias in node.names:
                name = alias.name
                if module not in imports:
                    imports[module] = set()
                imports[module].add(name)
                
    return imports


def check_file(filepath: str) -> List[str]:
    """Check a single file for incorrect model imports."""
    issues = []
    
    # Skip checking the model files themselves
    if filepath.endswith(('models.py', 'schemas.py')):
        return []
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
        tree = ast.parse(content)
        imports = get_imports(tree)
        
        # Check for incorrect imports
        for module, expected_models in MODEL_IMPORT_MAP.items():
            wrong_module = 'schemas' if module == 'models' else 'models'
            
            if wrong_module in imports:
                wrong_imports = imports[wrong_module] & expected_models
                for model in wrong_imports:
                    issues.append(
                        f"{filepath}: '{model}' should be imported from '{module}', "
                        f"not '{wrong_module}'"
                    )
        
        # Check for specific known issues
        for known_issue in KNOWN_ISSUES:
            if known_issue['wrong_import'] in content:
                # Check if it's not in a comment
                for line_no, line in enumerate(content.split('\n'), 1):
                    if known_issue['wrong_import'] in line and not line.strip().startswith('#'):
                        issues.append(
                            f"{filepath}:{line_no}: {known_issue['wrong_import']}\n"
                            f"    Should be: {known_issue['correct_import']}\n"
                            f"    Reason: {known_issue['reason']}"
                        )
                        
    except Exception as e:
        # Skip files that can't be parsed
        pass
        
    return issues


def check_model_usage(filepath: str) -> List[str]:
    """Check for common model usage errors."""
    issues = []
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
        # Check for get_adapter_id usage on wrong Principal
        if 'get_adapter_id' in content and 'Principal' in content:
            tree = ast.parse(content)
            imports = get_imports(tree)
            
            # If Principal is imported from models, it's wrong
            if 'models' in imports and 'Principal' in imports['models']:
                issues.append(
                    f"{filepath}: Using get_adapter_id() requires Principal from schemas.py, "
                    f"not models.py"
                )
                
    except Exception:
        pass
        
    return issues


def main():
    """Check all Python files for incorrect model imports."""
    all_issues = []
    
    exclude_dirs = {'.git', '__pycache__', '.venv', 'alembic', 'scripts'}
    
    for root, dirs, files in os.walk('.'):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        if any(excluded in root for excluded in exclude_dirs):
            continue
            
        for file in files:
            if file.endswith('.py'):
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


if __name__ == '__main__':
    main()