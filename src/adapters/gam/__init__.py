"""
Google Ad Manager (GAM) Adapter Modules

This package contains the modular components of the Google Ad Manager adapter:

- auth: Authentication and OAuth credential management
- client: API client initialization and management
- managers: Core business logic managers (orders, line items, creatives, targeting)
- utils: Shared utilities and helpers
"""

from .auth import GAMAuthManager
from .client import GAMClientManager
from .managers import (
    GAMCreativesManager,
    GAMOrdersManager,
    GAMTargetingManager,
)


def build_gam_config_from_adapter(adapter_config) -> dict:
    """Build GAM config dict from AdapterConfig model.

    Handles both OAuth and service account authentication methods.

    Args:
        adapter_config: AdapterConfig model instance

    Returns:
        Configuration dict suitable for GAMAuthManager/GAMClientManager
    """
    config = {
        "enabled": True,
        "network_code": adapter_config.gam_network_code,
        "trafficker_id": adapter_config.gam_trafficker_id,
        "manual_approval_required": adapter_config.gam_manual_approval_required,
    }

    # Add authentication credentials based on method
    if adapter_config.gam_auth_method == "service_account" and adapter_config.gam_service_account_json:
        config["service_account_json"] = adapter_config.gam_service_account_json
    elif adapter_config.gam_refresh_token:
        # OAuth (default)
        config["refresh_token"] = adapter_config.gam_refresh_token

    return config


__all__ = [
    "GAMAuthManager",
    "GAMClientManager",
    "GAMCreativesManager",
    "GAMOrdersManager",
    "GAMTargetingManager",
    "build_gam_config_from_adapter",
]
