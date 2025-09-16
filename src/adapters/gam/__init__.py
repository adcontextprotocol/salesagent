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

__all__ = [
    "GAMAuthManager",
    "GAMClientManager",
    "GAMCreativesManager",
    "GAMOrdersManager",
    "GAMTargetingManager",
]
