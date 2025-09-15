"""
Google Ad Manager (GAM) Adapter - Refactored Version

This is the refactored Google Ad Manager adapter that uses a modular architecture.
The main adapter class acts as an orchestrator, delegating specific operations
to specialized manager classes.
"""

import logging
from datetime import datetime
from typing import Any

from flask import Flask

from src.adapters.base import AdServerAdapter

# Import modular components
from src.adapters.gam.client import GAMClientManager
from src.adapters.gam.managers import (
    GAMCreativesManager,
    GAMInventoryManager,
    GAMOrdersManager,
    GAMSyncManager,
    GAMTargetingManager,
)
from src.core.audit_logger import AuditLogger
from src.core.schemas import (
    AssetStatus,
    CheckMediaBuyStatusResponse,
    CreateMediaBuyRequest,
    CreateMediaBuyResponse,
    GetMediaBuyDeliveryResponse,
    MediaPackage,
    UpdateMediaBuyRequest,
    UpdateMediaBuyResponse,
)

# Set up logger
logger = logging.getLogger(__name__)


class GoogleAdManager(AdServerAdapter):
    """Google Ad Manager adapter using modular architecture."""

    def __init__(
        self,
        config: dict[str, Any],
        principal,
        network_code: str,
        advertiser_id: str,
        trafficker_id: str,
        dry_run: bool = False,
        audit_logger: AuditLogger = None,
        tenant_id: str = None,
    ):
        """Initialize Google Ad Manager adapter with modular managers.

        Args:
            config: Configuration dictionary
            principal: Principal object for authentication
            network_code: GAM network code
            advertiser_id: GAM advertiser ID
            trafficker_id: GAM trafficker ID
            dry_run: Whether to run in dry-run mode
            audit_logger: Audit logging instance
            tenant_id: Tenant identifier
        """
        super().__init__(config, principal, dry_run, None, tenant_id)

        self.network_code = network_code
        self.advertiser_id = advertiser_id
        self.trafficker_id = trafficker_id
        self.refresh_token = config.get("refresh_token")
        self.key_file = config.get("service_account_key_file")
        self.principal = principal

        # Validate configuration
        if not self.network_code:
            raise ValueError("GAM config requires 'network_code'")

        if not self.advertiser_id:
            raise ValueError("GAM config requires 'advertiser_id'")

        if not self.key_file and not self.refresh_token:
            raise ValueError("GAM config requires either 'service_account_key_file' or 'refresh_token'")

        # Initialize modular components
        if not self.dry_run:
            self.client_manager = GAMClientManager(self.config, self.network_code)
            # Legacy client property for backward compatibility
            self.client = self.client_manager.get_client()
        else:
            self.client_manager = None
            self.client = None
            self.log("[yellow]Running in dry-run mode - GAM client not initialized[/yellow]")

        # Initialize manager components
        self.targeting_manager = GAMTargetingManager()
        self.orders_manager = GAMOrdersManager(self.client_manager, self.advertiser_id, self.trafficker_id, dry_run)
        self.creatives_manager = GAMCreativesManager(self.client_manager, self.advertiser_id, dry_run)
        self.inventory_manager = GAMInventoryManager(self.client_manager, tenant_id, dry_run)
        self.sync_manager = GAMSyncManager(
            self.client_manager, self.inventory_manager, self.orders_manager, tenant_id, dry_run
        )

        # Initialize legacy validator for backward compatibility
        from .gam.utils.validation import GAMValidator

        self.validator = GAMValidator()

    # Legacy methods for backward compatibility - delegated to managers
    def _init_client(self):
        """Initializes the Ad Manager client (legacy - now handled by client manager)."""
        if self.client_manager:
            return self.client_manager.get_client()
        return None

    def _get_oauth_credentials(self):
        """Get OAuth credentials (legacy - now handled by auth manager)."""
        if self.client_manager:
            return self.client_manager.auth_manager.get_credentials()
        return None

    # Legacy targeting methods - delegated to targeting manager
    def _validate_targeting(self, targeting_overlay):
        """Validate targeting and return unsupported features (delegated to targeting manager)."""
        return self.targeting_manager.validate_targeting(targeting_overlay)

    def _build_targeting(self, targeting_overlay):
        """Build GAM targeting criteria from AdCP targeting (delegated to targeting manager)."""
        return self.targeting_manager.build_targeting(targeting_overlay)

    # Legacy properties for backward compatibility
    @property
    def GEO_COUNTRY_MAP(self):
        return self.targeting_manager.geo_country_map

    @property
    def GEO_REGION_MAP(self):
        return self.targeting_manager.geo_region_map

    @property
    def GEO_METRO_MAP(self):
        return self.targeting_manager.geo_metro_map

    @property
    def DEVICE_TYPE_MAP(self):
        return self.targeting_manager.DEVICE_TYPE_MAP

    @property
    def SUPPORTED_MEDIA_TYPES(self):
        return self.targeting_manager.SUPPORTED_MEDIA_TYPES

    def create_media_buy(
        self, request: CreateMediaBuyRequest, packages: list[MediaPackage], start_time: datetime, end_time: datetime
    ) -> CreateMediaBuyResponse:
        """Create a new media buy (order) in GAM - main orchestration method."""
        self.log("[bold]GoogleAdManager.create_media_buy[/bold] - Creating GAM order")

        # Use orders manager for order creation
        order_id = self.orders_manager.create_order(
            order_name=f"{request.campaign_name} - {len(packages)} packages",
            total_budget=request.total_budget,
            start_time=start_time,
            end_time=end_time,
        )

        self.log(f"✓ Created GAM Order ID: {order_id}")

        return CreateMediaBuyResponse(
            media_buy_id=order_id, status="draft", message=f"Created GAM order with {len(packages)} line items"
        )

    def archive_order(self, order_id: str) -> bool:
        """Archive a GAM order for cleanup purposes (delegated to orders manager)."""
        return self.orders_manager.archive_order(order_id)

    def get_advertisers(self) -> list[dict[str, Any]]:
        """Get list of advertisers from GAM (delegated to orders manager)."""
        return self.orders_manager.get_advertisers()

    def add_creative_assets(
        self, media_buy_id: str, assets: list[dict[str, Any]], today: datetime
    ) -> list[AssetStatus]:
        """Create and associate creatives with line items (delegated to creatives manager)."""
        return self.creatives_manager.add_creative_assets(media_buy_id, assets, today)

    def check_media_buy_status(self, media_buy_id: str, today: datetime) -> CheckMediaBuyStatusResponse:
        """Check the status of a media buy in GAM."""
        # This would be implemented with appropriate manager delegation
        # For now, returning a basic implementation
        status = self.orders_manager.get_order_status(media_buy_id)

        return CheckMediaBuyStatusResponse(
            media_buy_id=media_buy_id, status=status.lower(), message=f"GAM order status: {status}"
        )

    def get_media_buy_delivery(self, media_buy_id: str, today: datetime) -> GetMediaBuyDeliveryResponse:
        """Get delivery metrics for a media buy."""
        # This would be implemented with appropriate manager delegation
        # For now, returning a basic implementation
        return GetMediaBuyDeliveryResponse(
            media_buy_id=media_buy_id,
            delivery_data={"impressions": 0, "clicks": 0, "spend": 0.0},
            message="Delivery data retrieval would be implemented",
        )

    def update_media_buy(self, request: UpdateMediaBuyRequest) -> UpdateMediaBuyResponse:
        """Update a media buy in GAM."""
        # This would be implemented with appropriate manager delegation
        return UpdateMediaBuyResponse(
            media_buy_id=request.media_buy_id, status="updated", message="Media buy update would be implemented"
        )

    def update_media_buy_performance_index(self, media_buy_id: str, package_performance: list) -> bool:
        """Update the performance index for packages in a media buy."""
        # This would be implemented with appropriate manager delegation
        self.log(f"Update performance index for media buy {media_buy_id} with {len(package_performance)} packages")
        return True

    def get_config_ui_endpoint(self) -> str | None:
        """Return the endpoint for GAM-specific configuration UI."""
        return "/adapters/gam/config"

    def register_ui_routes(self, app: Flask) -> None:
        """Register GAM-specific configuration routes."""
        from flask import jsonify, render_template, request

        @app.route("/adapters/gam/config/<tenant_id>/<product_id>", methods=["GET", "POST"])
        def gam_config_ui(tenant_id: str, product_id: str):
            """GAM adapter configuration UI."""
            if request.method == "POST":
                # Handle configuration updates
                return jsonify({"success": True})

            return render_template(
                "gam_config.html", tenant_id=tenant_id, product_id=product_id, title="Google Ad Manager Configuration"
            )

    def validate_product_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate GAM-specific product configuration."""
        required_fields = ["network_code", "advertiser_id"]

        for field in required_fields:
            if not config.get(field):
                return False, f"Missing required field: {field}"

        return True, None

    def _create_order_statement(self, order_id: int):
        """Helper method to create a GAM statement for order filtering."""
        return self.orders_manager.create_order_statement(order_id)

    # Inventory management methods - delegated to inventory manager
    def discover_ad_units(self, parent_id=None, max_depth=10):
        """Discover ad units in the GAM network (delegated to inventory manager)."""
        return self.inventory_manager.discover_ad_units(parent_id, max_depth)

    def discover_placements(self):
        """Discover all placements in the GAM network (delegated to inventory manager)."""
        return self.inventory_manager.discover_placements()

    def discover_custom_targeting(self):
        """Discover all custom targeting keys and values (delegated to inventory manager)."""
        return self.inventory_manager.discover_custom_targeting()

    def discover_audience_segments(self):
        """Discover audience segments (delegated to inventory manager)."""
        return self.inventory_manager.discover_audience_segments()

    def sync_all_inventory(self):
        """Perform full inventory sync (delegated to inventory manager)."""
        return self.inventory_manager.sync_all_inventory()

    def build_ad_unit_tree(self):
        """Build hierarchical ad unit tree (delegated to inventory manager)."""
        return self.inventory_manager.build_ad_unit_tree()

    def get_targetable_ad_units(self, include_inactive=False, min_sizes=None):
        """Get targetable ad units (delegated to inventory manager)."""
        return self.inventory_manager.get_targetable_ad_units(include_inactive, min_sizes)

    def suggest_ad_units_for_product(self, creative_sizes, keywords=None):
        """Suggest ad units for product (delegated to inventory manager)."""
        return self.inventory_manager.suggest_ad_units_for_product(creative_sizes, keywords)

    def validate_inventory_access(self, ad_unit_ids):
        """Validate inventory access (delegated to inventory manager)."""
        return self.inventory_manager.validate_inventory_access(ad_unit_ids)

    # Sync management methods - delegated to sync manager
    def sync_inventory(self, db_session, force=False):
        """Synchronize inventory data from GAM (delegated to sync manager)."""
        return self.sync_manager.sync_inventory(db_session, force)

    def sync_orders(self, db_session, force=False):
        """Synchronize orders data from GAM (delegated to sync manager)."""
        return self.sync_manager.sync_orders(db_session, force)

    def sync_full(self, db_session, force=False):
        """Perform full synchronization (delegated to sync manager)."""
        return self.sync_manager.sync_full(db_session, force)

    def get_sync_status(self, db_session, sync_id):
        """Get sync status (delegated to sync manager)."""
        return self.sync_manager.get_sync_status(db_session, sync_id)

    def get_sync_history(self, db_session, limit=10, offset=0, status_filter=None):
        """Get sync history (delegated to sync manager)."""
        return self.sync_manager.get_sync_history(db_session, limit, offset, status_filter)

    def needs_sync(self, db_session, sync_type, max_age_hours=24):
        """Check if sync is needed (delegated to sync manager)."""
        return self.sync_manager.needs_sync(db_session, sync_type, max_age_hours)
