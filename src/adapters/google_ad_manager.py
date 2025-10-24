"""
Google Ad Manager (GAM) Adapter - Refactored Version

This is the refactored Google Ad Manager adapter that uses a modular architecture.
The main adapter class acts as an orchestrator, delegating specific operations
to specialized manager classes.
"""

# Export constants for backward compatibility
__all__ = [
    "GUARANTEED_LINE_ITEM_TYPES",
    "NON_GUARANTEED_LINE_ITEM_TYPES",
]

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
    GAMWorkflowManager,
)

# Re-export constants for backward compatibility
from src.adapters.gam.managers.orders import (
    GUARANTEED_LINE_ITEM_TYPES,
    NON_GUARANTEED_LINE_ITEM_TYPES,
)
from src.adapters.gam.pricing_compatibility import PricingCompatibility
from src.core.audit_logger import AuditLogger
from src.core.schemas import (
    AssetStatus,
    CheckMediaBuyStatusResponse,
    CreateMediaBuyRequest,
    CreateMediaBuyResponse,
    Error,
    GetMediaBuyDeliveryResponse,
    MediaPackage,
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
        *,
        network_code: str,
        advertiser_id: str | None = None,
        trafficker_id: str | None = None,
        dry_run: bool = False,
        audit_logger: AuditLogger = None,
        tenant_id: str = None,
    ):
        """Initialize Google Ad Manager adapter with modular managers.

        Args:
            config: Configuration dictionary
            principal: Principal object for authentication
            network_code: GAM network code
            advertiser_id: GAM advertiser ID (optional, required only for order/campaign operations)
            trafficker_id: GAM trafficker ID (optional, required only for order/campaign operations)
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
        self.service_account_json = config.get("service_account_json")
        self.principal = principal

        # Validate configuration
        if not self.network_code:
            raise ValueError("GAM config requires 'network_code'")

        # Validate advertiser_id is numeric if provided (GAM expects integer company IDs)
        if advertiser_id is not None and advertiser_id != "":
            # Check if it's numeric (as string or int)
            try:
                int(advertiser_id)
            except (ValueError, TypeError):
                raise ValueError(
                    f"GAM advertiser_id must be numeric (got: '{advertiser_id}'). "
                    f"Check principal platform_mappings configuration."
                )

        # advertiser_id is only required for order/campaign operations, not inventory sync

        if not self.key_file and not self.service_account_json and not self.refresh_token:
            raise ValueError(
                "GAM config requires either 'service_account_key_file', 'service_account_json', or 'refresh_token'"
            )

        # Initialize modular components
        if not self.dry_run:
            self.client_manager = GAMClientManager(self.config, self.network_code)
            # Legacy client property for backward compatibility
            self.client = self.client_manager.get_client()

            # Auto-detect trafficker_id if not provided
            if not self.trafficker_id:
                try:
                    user_service = self.client.GetService("UserService", version="v202411")
                    current_user = user_service.getCurrentUser()
                    self.trafficker_id = str(current_user["id"])
                    logger.info(
                        f"Auto-detected trafficker_id: {self.trafficker_id} ({current_user.get('name', 'Unknown')})"
                    )
                except Exception as e:
                    logger.warning(f"Could not auto-detect trafficker_id: {e}")
        else:
            self.client_manager = None
            self.client = None
            self.log("[yellow]Running in dry-run mode - GAM client not initialized[/yellow]")

        # Initialize manager components
        self.targeting_manager = GAMTargetingManager()

        # Initialize orders manager (advertiser_id/trafficker_id optional for query operations)
        self.orders_manager = GAMOrdersManager(self.client_manager, self.advertiser_id, self.trafficker_id, dry_run)

        # Only initialize creative manager if we have advertiser_id (required for creative operations)
        if self.advertiser_id and self.trafficker_id:
            self.creatives_manager = GAMCreativesManager(
                self.client_manager, self.advertiser_id, dry_run, self.log, self
            )
        else:
            self.creatives_manager = None

        # Inventory manager doesn't need advertiser_id
        self.inventory_manager = GAMInventoryManager(self.client_manager, tenant_id, dry_run)

        # Sync manager only needs inventory manager for inventory sync
        self.sync_manager = GAMSyncManager(
            self.client_manager, self.inventory_manager, self.orders_manager, tenant_id, dry_run
        )
        self.workflow_manager = GAMWorkflowManager(tenant_id, principal, audit_logger, self.log)

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

    # HITL (Human-in-the-Loop) support methods
    def _requires_manual_approval(self, operation: str) -> bool:
        """Check if an operation requires manual approval based on configuration.

        Args:
            operation: The operation name (e.g., 'create_media_buy', 'add_creative_assets')

        Returns:
            bool: True if manual approval is required for this operation
        """
        return self.manual_approval_required and operation in self.manual_approval_operations

    # Legacy admin/business logic methods for backward compatibility
    def _is_admin_principal(self) -> bool:
        """Check if the current principal has admin privileges."""
        if not hasattr(self.principal, "platform_mappings"):
            return False

        gam_mappings = self.principal.platform_mappings.get("google_ad_manager", {})
        return bool(gam_mappings.get("gam_admin", False) or gam_mappings.get("is_admin", False))

    def _validate_creative_for_gam(self, asset):
        """Validate creative asset for GAM requirements (delegated to creatives manager)."""
        if not self.creatives_manager:
            raise ValueError("GAM adapter not configured for creative operations")
        return self.creatives_manager._validate_creative_for_gam(asset)

    def _get_creative_type(self, asset):
        """Determine creative type from asset (delegated to creatives manager)."""
        if not self.creatives_manager:
            raise ValueError("GAM adapter not configured for creative operations")
        return self.creatives_manager._get_creative_type(asset)

    def _create_gam_creative(self, asset, creative_type, asset_placeholders):
        """Create a GAM creative (delegated to creatives manager)."""
        if not self.creatives_manager:
            raise ValueError("GAM adapter not configured for creative operations")
        return self.creatives_manager._create_gam_creative(asset, creative_type, asset_placeholders)

    def _check_order_has_guaranteed_items(self, order_id):
        """Check if order has guaranteed line items (delegated to orders manager)."""
        if not self.orders_manager:
            raise ValueError("GAM adapter not configured for order operations")
        return self.orders_manager.check_order_has_guaranteed_items(order_id)

    def get_supported_pricing_models(self) -> set[str]:
        """Return set of pricing models GAM adapter supports.

        Google Ad Manager supports:
        - CPM: All line item types
        - VCPM: STANDARD only (viewable CPM)
        - CPC: STANDARD, SPONSORSHIP, NETWORK, PRICE_PRIORITY
        - FLAT_RATE: SPONSORSHIP (translated to CPD internally)

        Returns:
            Set of pricing model strings supported by this adapter
        """
        return {"cpm", "vcpm", "cpc", "flat_rate"}

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
        self,
        request: CreateMediaBuyRequest,
        packages: list[MediaPackage],
        start_time: datetime,
        end_time: datetime,
        package_pricing_info: dict[str, dict] | None = None,
    ) -> CreateMediaBuyResponse:
        """Create a new media buy (order) in GAM - main orchestration method.

        Args:
            request: Full create media buy request
            packages: Simplified package models
            start_time: Campaign start time
            end_time: Campaign end time
            package_pricing_info: Optional validated pricing info (AdCP PR #88)
                Maps package_id → {pricing_model, rate, currency, is_fixed, bid_price}

        Returns:
            CreateMediaBuyResponse with GAM order details
        """
        self.log("[bold]GoogleAdManager.create_media_buy[/bold] - Creating GAM order")

        # Validate pricing models - check GAM compatibility
        if package_pricing_info:
            for pkg_id, pricing in package_pricing_info.items():
                pricing_model = pricing["pricing_model"]

                # Check if pricing model is supported by GAM adapter at all
                try:
                    gam_cost_type = PricingCompatibility.get_gam_cost_type(pricing_model)
                except ValueError as e:
                    error_msg = (
                        f"Google Ad Manager adapter does not support '{pricing_model}' pricing. "
                        f"Supported pricing models: CPM, VCPM, CPC, FLAT_RATE. "
                        f"The requested pricing model ('{pricing_model}') is not available in GAM. "
                        f"Please choose a product with compatible pricing."
                    )
                    self.log(f"[red]Error: {error_msg}[/red]")
                    return CreateMediaBuyResponse(
                        buyer_ref=request.buyer_ref,
                        media_buy_id=None,
                        errors=[Error(code="unsupported_pricing_model", message=error_msg, details=None)],
                    )

                self.log(
                    f"📊 Package {pkg_id} pricing: {pricing_model} → GAM {gam_cost_type} "
                    f"({pricing['currency']}, {'fixed' if pricing['is_fixed'] else 'auction'})"
                )

        # Validate that advertiser_id and trafficker_id are configured
        if not self.advertiser_id or not self.trafficker_id:
            error_msg = "GAM adapter is not fully configured for order creation. Missing required configuration: "
            missing = []
            if not self.advertiser_id:
                missing.append("advertiser_id (company_id)")
            if not self.trafficker_id:
                missing.append("trafficker_id")
            error_msg += ", ".join(missing)

            self.log(f"[red]Error: {error_msg}[/red]")
            return CreateMediaBuyResponse(
                buyer_ref=request.buyer_ref,
                media_buy_id=None,
                errors=[Error(code="configuration_error", message=error_msg)],
            )

        # Get products to access implementation_config

        from src.core.database.database_session import get_db_session
        from src.core.database.models import Product

        products_map = {}
        with get_db_session() as db_session:
            for package in packages:
                from sqlalchemy import select

                stmt = select(Product).filter_by(
                    tenant_id=self.tenant_id,
                    product_id=package.package_id,  # package_id is actually product_id
                )
                product = db_session.scalars(stmt).first()
                if product:
                    products_map[package.package_id] = {
                        "product_id": product.product_id,
                        "implementation_config": (
                            product.implementation_config if product.implementation_config else {}
                        ),
                    }

        # Validate targeting
        unsupported_features = self._validate_targeting(request.targeting_overlay)
        if unsupported_features:
            error_msg = f"Unsupported targeting features: {', '.join(unsupported_features)}"
            self.log(f"[red]Error: {error_msg}[/red]")
            return CreateMediaBuyResponse(
                buyer_ref=request.buyer_ref,
                media_buy_id=None,
                errors=[Error(code="unsupported_targeting", message=error_msg)],
            )

        # Build base targeting from targeting overlay
        base_targeting = self._build_targeting(request.targeting_overlay)

        # Check if manual approval is required for media buy creation
        if self._requires_manual_approval("create_media_buy"):
            self.log("[yellow]Manual approval mode - creating workflow step for human intervention[/yellow]")

            # Generate a media buy ID for tracking
            import uuid

            media_buy_id = f"gam_order_{uuid.uuid4().hex[:8]}"

            # Create manual order workflow step
            step_id = self.workflow_manager.create_manual_order_workflow_step(
                request, packages, start_time, end_time, media_buy_id
            )

            # Build package responses with package_ids (no line_item_ids yet - order not created)
            package_responses = []
            for package in packages:
                package_responses.append(
                    {
                        "package_id": package.package_id,
                    }
                )

            if step_id:
                return CreateMediaBuyResponse(
                    buyer_ref=request.buyer_ref,
                    media_buy_id=media_buy_id,
                    workflow_step_id=step_id,
                    packages=package_responses,
                )
            else:
                error_msg = "Failed to create manual order workflow step"
                return CreateMediaBuyResponse(
                    buyer_ref=request.buyer_ref,
                    media_buy_id=media_buy_id,
                    errors=[Error(code="workflow_creation_failed", message=error_msg)],
                    packages=package_responses,
                )

        # Automatic mode - create order directly
        # Use naming template from adapter config, or fallback to default
        from sqlalchemy import select

        from src.adapters.gam.utils.constants import GAM_NAME_LIMITS
        from src.adapters.gam.utils.naming import truncate_name_with_suffix
        from src.core.database.database_session import get_db_session
        from src.core.database.models import AdapterConfig
        from src.core.utils.naming import apply_naming_template, build_order_name_context

        order_name_template = "{campaign_name|brand_name} - {date_range}"  # Default
        tenant_gemini_key = None
        with get_db_session() as db_session:
            from src.core.database.models import Tenant

            stmt = select(AdapterConfig).filter_by(tenant_id=self.tenant_id)
            adapter_config = db_session.scalars(stmt).first()
            if adapter_config and adapter_config.gam_order_name_template:
                order_name_template = adapter_config.gam_order_name_template

            # Get tenant's Gemini key for auto_name generation
            tenant_stmt = select(Tenant).filter_by(tenant_id=self.tenant_id)
            tenant = db_session.scalars(tenant_stmt).first()
            if tenant:
                tenant_gemini_key = tenant.gemini_api_key

        context = build_order_name_context(request, packages, start_time, end_time, tenant_gemini_key)
        base_order_name = apply_naming_template(order_name_template, context)

        # Add unique identifier to prevent duplicate order names
        # Use media_buy_id if available (from buyer_ref), otherwise timestamp
        unique_suffix = request.buyer_ref or f"mb_{int(datetime.now().timestamp())}"
        full_order_name = f"{base_order_name} [{unique_suffix}]"

        # Truncate to GAM's 255-character limit while preserving the unique suffix
        order_name = truncate_name_with_suffix(full_order_name, GAM_NAME_LIMITS["max_order_name_length"])

        # Extract budget amount (v1.8.0 compatible)
        from src.core.schemas import extract_budget_amount

        total_budget_amount, _ = extract_budget_amount(request.budget, request.currency or "USD")

        order_id = self.orders_manager.create_order(
            order_name=order_name,
            total_budget=total_budget_amount,
            start_time=start_time,
            end_time=end_time,
        )

        self.log(f"✓ Created GAM Order ID: {order_id}")

        # Create line items for each package
        try:
            line_item_ids = self.orders_manager.create_line_items(
                order_id=order_id,
                packages=packages,
                start_time=start_time,
                end_time=end_time,
                targeting=base_targeting,
                products_map=products_map,
                log_func=self.log,
                tenant_id=self.tenant_id,
                order_name=order_name,
                targeting_overlay=request.targeting_overlay,
                package_pricing_info=package_pricing_info,
            )
            self.log(f"✓ Created {len(line_item_ids)} line items")
        except Exception as e:
            error_msg = f"Order created but failed to create line items: {str(e)}"
            self.log(f"[red]Error: {error_msg}[/red]")
            return CreateMediaBuyResponse(
                buyer_ref=request.buyer_ref,
                media_buy_id=order_id,
                errors=[Error(code="line_item_creation_failed", message=error_msg)],
            )

        # Check if activation approval is needed (guaranteed line items require human approval)
        has_guaranteed, item_types = self._check_order_has_guaranteed_items(order_id)
        if has_guaranteed:
            self.log("[yellow]Order contains guaranteed line items - creating activation workflow step[/yellow]")

            step_id = self.workflow_manager.create_activation_workflow_step(order_id, packages)

            # Build package responses with line_item_ids for creative association
            package_responses = []
            for package, line_item_id in zip(packages, line_item_ids, strict=False):
                package_responses.append(
                    {
                        "package_id": package.package_id,
                        "platform_line_item_id": str(line_item_id),  # GAM line item ID for creative association
                    }
                )

            return CreateMediaBuyResponse(
                buyer_ref=request.buyer_ref,
                media_buy_id=order_id,
                workflow_step_id=step_id,
                packages=package_responses,
            )

        # Build package responses with line_item_ids for creative association
        package_responses = []
        for package, line_item_id in zip(packages, line_item_ids, strict=False):
            package_responses.append(
                {
                    "package_id": package.package_id,
                    "platform_line_item_id": str(line_item_id),  # GAM line item ID for creative association
                }
            )

        return CreateMediaBuyResponse(
            buyer_ref=request.buyer_ref,
            media_buy_id=order_id,
            packages=package_responses,
        )

    def archive_order(self, order_id: str) -> bool:
        """Archive a GAM order for cleanup purposes (delegated to orders manager)."""
        if not self.advertiser_id or not self.trafficker_id:
            self.log(
                "[red]Error: GAM adapter not configured for order operations (missing advertiser_id or trafficker_id)[/red]"
            )
            return False
        return self.orders_manager.archive_order(order_id)

    def get_advertisers(self) -> list[dict[str, Any]]:
        """Get list of advertisers from GAM (delegated to orders manager)."""
        return self.orders_manager.get_advertisers()

    def add_creative_assets(
        self, media_buy_id: str, assets: list[dict[str, Any]], today: datetime
    ) -> list[AssetStatus]:
        """Create and associate creatives with line items (delegated to creatives manager)."""

        # Validate that creatives manager is initialized
        if not self.creatives_manager:
            error_msg = "GAM adapter is not fully configured for creative operations. Missing required configuration: "
            missing = []
            if not self.advertiser_id:
                missing.append("advertiser_id (company_id)")
            if not self.trafficker_id:
                missing.append("trafficker_id")
            error_msg += ", ".join(missing)

            self.log(f"[red]Error: {error_msg}[/red]")
            return [
                AssetStatus(
                    asset_id=asset.get("asset_id", f"failed_{i}"),
                    status="failed",
                    message=error_msg,
                    creative_id=None,
                )
                for i, asset in enumerate(assets)
            ]

        # Check if manual approval is required for creative assets
        if self._requires_manual_approval("add_creative_assets"):
            self.log("[yellow]Manual approval mode - creating workflow step for creative asset approval[/yellow]")

            # Create approval workflow step
            step_id = self.workflow_manager.create_approval_workflow_step(media_buy_id, "creative_assets_approval")

            if step_id:
                # Return asset statuses indicating they are awaiting approval
                asset_statuses = []
                for asset in assets:
                    asset_statuses.append(
                        AssetStatus(
                            asset_id=asset.get("asset_id", f"pending_{len(asset_statuses)}"),
                            status="submitted",
                            message=f"Creative asset submitted for approval. Workflow step: {step_id}",
                            creative_id=None,
                            workflow_step_id=step_id,
                        )
                    )
                return asset_statuses
            else:
                # Return failed statuses if workflow creation failed
                asset_statuses = []
                for asset in assets:
                    asset_statuses.append(
                        AssetStatus(
                            asset_id=asset.get("asset_id", f"failed_{len(asset_statuses)}"),
                            status="failed",
                            message="Failed to create approval workflow step",
                            creative_id=None,
                        )
                    )
                return asset_statuses

        # Automatic mode - process creatives directly
        return self.creatives_manager.add_creative_assets(media_buy_id, assets, today)

    def associate_creatives(self, line_item_ids: list[str], platform_creative_ids: list[str]) -> list[dict[str, Any]]:
        """Associate already-uploaded creatives with line items.

        Used when buyer provides creative_ids in create_media_buy, indicating
        creatives were already synced and should be associated immediately.

        Args:
            line_item_ids: GAM line item IDs
            platform_creative_ids: GAM creative IDs (already uploaded)

        Returns:
            List of association results with status
        """
        if not self.creatives_manager:
            self.log("[red]Error: Creatives manager not initialized[/red]")
            return [
                {
                    "line_item_id": lid,
                    "creative_id": cid,
                    "status": "failed",
                    "error": "Creatives manager not initialized",
                }
                for lid in line_item_ids
                for cid in platform_creative_ids
            ]

        results = []

        if not self.dry_run:
            lica_service = self.client_manager.get_service("LineItemCreativeAssociationService")

        for line_item_id in line_item_ids:
            for creative_id in platform_creative_ids:
                if self.dry_run:
                    self.log(
                        f"[cyan][DRY RUN] Would associate creative {creative_id} with line item {line_item_id}[/cyan]"
                    )
                    results.append(
                        {"line_item_id": line_item_id, "creative_id": creative_id, "status": "success (dry-run)"}
                    )
                else:
                    association = {
                        "creativeId": int(creative_id),
                        "lineItemId": int(line_item_id),
                    }

                    try:
                        lica_service.createLineItemCreativeAssociations([association])
                        self.log(f"[green]✓ Associated creative {creative_id} with line item {line_item_id}[/green]")
                        results.append({"line_item_id": line_item_id, "creative_id": creative_id, "status": "success"})
                    except Exception as e:
                        error_msg = str(e)
                        self.log(
                            f"[red]✗ Failed to associate creative {creative_id} with line item {line_item_id}: {error_msg}[/red]"
                        )
                        results.append(
                            {
                                "line_item_id": line_item_id,
                                "creative_id": creative_id,
                                "status": "failed",
                                "error": error_msg,
                            }
                        )

        return results

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

    def update_media_buy(
        self,
        media_buy_id: str,
        buyer_ref: str,
        action: str,
        package_id: str | None,
        budget: int | None,
        today: datetime,
    ) -> UpdateMediaBuyResponse:
        """Update a media buy in GAM."""
        # Admin-only actions
        admin_only_actions = ["approve_order"]

        # Check if action requires admin privileges
        if action in admin_only_actions and not self._is_admin_principal():
            from src.core.schemas import Error

            return UpdateMediaBuyResponse(
                media_buy_id=media_buy_id,
                buyer_ref=buyer_ref,
                errors=[Error(code="insufficient_privileges", message="Only admin users can approve orders")],
            )

        # Check if manual approval is required for media buy updates
        if self._requires_manual_approval("update_media_buy"):
            self.log("[yellow]Manual approval mode - creating workflow step for media buy update approval[/yellow]")

            # Create approval workflow step for the update action
            step_id = self.workflow_manager.create_approval_workflow_step(media_buy_id, f"update_media_buy_{action}")

            if step_id:
                # Manual approval success - no errors
                return UpdateMediaBuyResponse(
                    media_buy_id=media_buy_id,
                    buyer_ref=buyer_ref,
                )
            else:
                from src.core.schemas import Error

                return UpdateMediaBuyResponse(
                    media_buy_id=media_buy_id,
                    buyer_ref=buyer_ref,
                    errors=[
                        Error(
                            code="workflow_creation_failed",
                            message="Failed to create approval workflow step",
                        )
                    ],
                )

        # Check for activate_order action with guaranteed items
        if action == "activate_order":
            # Check if order has guaranteed line items
            has_guaranteed, item_types = self._check_order_has_guaranteed_items(media_buy_id)
            if has_guaranteed:
                self.log("[yellow]Order contains guaranteed line items - creating activation workflow step[/yellow]")

                # Create activation workflow step
                step_id = self.workflow_manager.create_activation_workflow_step(media_buy_id, [])

                if step_id:
                    # Activation workflow created - success (no errors)
                    return UpdateMediaBuyResponse(
                        media_buy_id=media_buy_id,
                        buyer_ref=buyer_ref,
                    )
                else:
                    from src.core.schemas import Error

                    return UpdateMediaBuyResponse(
                        media_buy_id=media_buy_id,
                        buyer_ref=buyer_ref,
                        errors=[
                            Error(
                                code="activation_workflow_failed",
                                message=f"Cannot auto-activate order with guaranteed line items: {', '.join(item_types)}",
                            )
                        ],
                    )

        # For allowed actions in automatic mode, return success (no errors)
        return UpdateMediaBuyResponse(
            media_buy_id=media_buy_id,
            buyer_ref=buyer_ref,
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
    def sync_inventory(self, db_session, force=False, custom_targeting_limit=1000):
        """Synchronize inventory data from GAM (delegated to sync manager)."""
        return self.sync_manager.sync_inventory(db_session, force, custom_targeting_limit)

    def sync_orders(self, db_session, force=False):
        """Synchronize orders data from GAM (delegated to sync manager)."""
        return self.sync_manager.sync_orders(db_session, force)

    def sync_full(self, db_session, force=False, custom_targeting_limit=1000):
        """Perform full synchronization (delegated to sync manager)."""
        return self.sync_manager.sync_full(db_session, force, custom_targeting_limit)

    def sync_selective(self, db_session, sync_types, custom_targeting_limit=1000, audience_segment_limit=None):
        """Perform selective synchronization (delegated to sync manager)."""
        return self.sync_manager.sync_selective(db_session, sync_types, custom_targeting_limit, audience_segment_limit)

    def get_sync_status(self, db_session, sync_id):
        """Get sync status (delegated to sync manager)."""
        return self.sync_manager.get_sync_status(db_session, sync_id)

    def get_sync_history(self, db_session, limit=10, offset=0, status_filter=None):
        """Get sync history (delegated to sync manager)."""
        return self.sync_manager.get_sync_history(db_session, limit, offset, status_filter)

    def needs_sync(self, db_session, sync_type, max_age_hours=24):
        """Check if sync is needed (delegated to sync manager)."""
        return self.sync_manager.needs_sync(db_session, sync_type, max_age_hours)

    # Backward compatibility methods for tests
    def _is_admin_principal(self) -> bool:
        """Check if principal has admin privileges."""
        if not self.principal or not hasattr(self.principal, "platform_mappings"):
            return False
        gam_mapping = self.principal.platform_mappings.get("google_ad_manager", {})
        if isinstance(gam_mapping, dict):
            return gam_mapping.get("gam_admin", False) or gam_mapping.get("is_admin", False)
        return False

    def _validate_creative_for_gam(self, asset: dict) -> list:
        """Validate creative asset for GAM (backward compatibility)."""
        return self.creatives_manager._validate_creative_for_gam(asset)

    def _get_creative_type(self, asset: dict) -> str:
        """Determine creative type from asset (backward compatibility)."""
        return self.creatives_manager._get_creative_type(asset)

    def _check_order_has_guaranteed_items(self, order_id: str) -> tuple:
        """Check if order has guaranteed line items (backward compatibility)."""
        return self.orders_manager.check_order_has_guaranteed_items(order_id)
