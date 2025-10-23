"""Admin utilities package."""

# Re-export from parent utils module for backward compatibility
from pathlib import Path

# Import from parent utils.py
parent_utils = Path(__file__).parent.parent / "utils.py"
spec = __import__("importlib.util").util.spec_from_file_location("utils", parent_utils)
utils_module = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(utils_module)

# Re-export all public functions from utils.py
for name in dir(utils_module):
    if not name.startswith("_"):
        globals()[name] = getattr(utils_module, name)

# Export decorator
from src.admin.utils.audit_decorator import log_admin_action

__all__ = ["log_admin_action"]
