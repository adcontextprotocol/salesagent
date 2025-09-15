"""
GAM Manager Components

This package contains the manager classes that handle specific business logic areas:

- orders: Order creation, management, and status handling
- line_items: Line item creation, modification, and targeting
- creatives: Creative management, validation, and upload
- targeting: Targeting translation and validation
"""

from .creatives import GAMCreativesManager
from .orders import GAMOrdersManager
from .targeting import GAMTargetingManager

__all__ = [
    "GAMOrdersManager",
    "GAMCreativesManager",
    "GAMTargetingManager",
]
