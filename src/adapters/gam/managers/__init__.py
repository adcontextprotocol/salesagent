"""
GAM Manager Components

This package contains the manager classes that handle specific business logic areas:

- orders: Order creation, management, and status handling
- line_items: Line item creation, modification, and targeting
- creatives: Creative management, validation, and upload
- targeting: Targeting translation and validation
- inventory: Inventory discovery, ad unit management, and placement operations
- sync: Synchronization coordination between GAM and database
- workflow: Human-in-the-Loop workflow management and notifications
- reporting: Delivery reporting and webhook notifications
"""

from .creatives import GAMCreativesManager
from .inventory import GAMInventoryManager
from .orders import GAMOrdersManager
from .reporting import GAMReportingManager
from .sync import GAMSyncManager
from .targeting import GAMTargetingManager
from .workflow import GAMWorkflowManager

__all__ = [
    "GAMOrdersManager",
    "GAMCreativesManager",
    "GAMTargetingManager",
    "GAMInventoryManager",
    "GAMSyncManager",
    "GAMWorkflowManager",
    "GAMReportingManager",
]
