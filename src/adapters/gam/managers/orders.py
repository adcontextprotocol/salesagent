"""
GAM Orders Manager

Handles order creation, management, status checking, and lifecycle operations
for Google Ad Manager orders.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from googleads import ad_manager

logger = logging.getLogger(__name__)

# Line item type constants for GAM automation
GUARANTEED_LINE_ITEM_TYPES = {"STANDARD", "SPONSORSHIP"}
NON_GUARANTEED_LINE_ITEM_TYPES = {"NETWORK", "BULK", "PRICE_PRIORITY", "HOUSE"}


class GAMOrdersManager:
    """Manages Google Ad Manager order operations."""

    def __init__(
        self, client_manager, advertiser_id: str | None = None, trafficker_id: str | None = None, dry_run: bool = False
    ):
        """Initialize orders manager.

        Args:
            client_manager: GAMClientManager instance
            advertiser_id: GAM advertiser ID (required for order creation operations)
            trafficker_id: GAM trafficker ID (required for order creation operations)
            dry_run: Whether to run in dry-run mode
        """
        self.client_manager = client_manager
        self.advertiser_id = advertiser_id
        self.trafficker_id = trafficker_id
        self.dry_run = dry_run

    def create_order(
        self,
        order_name: str,
        total_budget: float,
        start_time: datetime,
        end_time: datetime,
        applied_team_ids: list[str] | None = None,
        po_number: str | None = None,
    ) -> str:
        """Create a new GAM order.

        Args:
            order_name: Name for the order
            total_budget: Total budget in USD
            start_time: Order start datetime
            end_time: Order end datetime
            applied_team_ids: Optional list of team IDs to apply
            po_number: Optional PO number

        Returns:
            Created order ID as string

        Raises:
            ValueError: If advertiser_id or trafficker_id not configured
            Exception: If order creation fails
        """
        # Validate required configuration for order creation
        if not self.advertiser_id or not self.trafficker_id:
            raise ValueError(
                "Order creation requires both advertiser_id and trafficker_id. "
                "These must be provided when initializing GAMOrdersManager for order operations."
            )

        # Create Order object
        order = {
            "name": order_name,
            "advertiserId": self.advertiser_id,
            "traffickerId": self.trafficker_id,
            "totalBudget": {"currencyCode": "USD", "microAmount": int(total_budget * 1_000_000)},
            "startDateTime": {
                "date": {"year": start_time.year, "month": start_time.month, "day": start_time.day},
                "hour": start_time.hour,
                "minute": start_time.minute,
                "second": start_time.second,
            },
            "endDateTime": {
                "date": {"year": end_time.year, "month": end_time.month, "day": end_time.day},
                "hour": end_time.hour,
                "minute": end_time.minute,
                "second": end_time.second,
            },
        }

        # Add PO number if provided
        if po_number:
            order["poNumber"] = po_number

        # Add team IDs if configured
        if applied_team_ids:
            order["appliedTeamIds"] = applied_team_ids

        if self.dry_run:
            logger.info(f"Would call: order_service.createOrders([{order['name']}])")
            logger.info(f"  Advertiser ID: {self.advertiser_id}")
            logger.info(f"  Total Budget: ${total_budget:,.2f}")
            logger.info(f"  Flight Dates: {start_time.date()} to {end_time.date()}")
            # Return a mock order ID for dry run
            return f"dry_run_order_{int(datetime.now().timestamp())}"
        else:
            order_service = self.client_manager.get_service("OrderService")
            created_orders = order_service.createOrders([order])
            if created_orders:
                order_id = str(created_orders[0]["id"])
                logger.info(f"✓ Created GAM Order ID: {order_id}")
                return order_id
            else:
                raise Exception("Failed to create order - no orders returned")

    def get_order_status(self, order_id: str) -> str:
        """Get the status of a GAM order.

        Args:
            order_id: GAM order ID

        Returns:
            Order status string
        """
        if self.dry_run:
            logger.info(f"Would call: order_service.getOrdersByStatement(WHERE id={order_id})")
            return "DRAFT"

        try:
            order_service = self.client_manager.get_service("OrderService")
            statement_builder = ad_manager.StatementBuilder()
            statement_builder.Where("id = :orderId")
            statement_builder.WithBindVariable("orderId", int(order_id))
            statement = statement_builder.ToStatement()

            result = order_service.getOrdersByStatement(statement)
            if result and result.get("results"):
                return result["results"][0].get("status", "UNKNOWN")
            else:
                return "NOT_FOUND"
        except Exception as e:
            logger.error(f"Error getting order status for {order_id}: {e}")
            return "ERROR"

    def archive_order(self, order_id: str) -> bool:
        """Archive a GAM order for cleanup purposes.

        Args:
            order_id: The GAM order ID to archive

        Returns:
            True if archival succeeded, False otherwise
        """
        logger.info(f"Archiving GAM Order {order_id} for cleanup")

        if self.dry_run:
            logger.info(f"Would call: order_service.performOrderAction(ArchiveOrders, {order_id})")
            return True

        try:
            order_service = self.client_manager.get_service("OrderService")

            # Use ArchiveOrders action
            archive_action = {"xsi_type": "ArchiveOrders"}

            statement_builder = ad_manager.StatementBuilder()
            statement_builder.Where("id = :orderId")
            statement_builder.WithBindVariable("orderId", int(order_id))
            statement = statement_builder.ToStatement()

            result = order_service.performOrderAction(archive_action, statement)

            if result and result.get("numChanges", 0) > 0:
                logger.info(f"✓ Successfully archived GAM Order {order_id}")
                return True
            else:
                logger.warning(f"No changes made when archiving Order {order_id} (may already be archived)")
                return True  # Consider this successful

        except Exception as e:
            logger.error(f"Failed to archive GAM Order {order_id}: {str(e)}")
            return False

    def get_order_line_items(self, order_id: str) -> list[dict]:
        """Get all line items associated with an order.

        Args:
            order_id: GAM order ID

        Returns:
            List of line item dictionaries
        """
        if self.dry_run:
            logger.info(f"Would call: lineitem_service.getLineItemsByStatement(WHERE orderId={order_id})")
            return []

        try:
            lineitem_service = self.client_manager.get_service("LineItemService")
            statement_builder = ad_manager.StatementBuilder()
            statement_builder.Where("orderId = :orderId")
            statement_builder.WithBindVariable("orderId", int(order_id))
            statement = statement_builder.ToStatement()

            result = lineitem_service.getLineItemsByStatement(statement)
            return result.get("results", [])
        except Exception as e:
            logger.error(f"Error getting line items for order {order_id}: {e}")
            return []

    def check_order_has_guaranteed_items(self, order_id: str) -> tuple[bool, list[str]]:
        """Check if order has guaranteed line items.

        Args:
            order_id: GAM order ID

        Returns:
            Tuple of (has_guaranteed_items, list_of_guaranteed_types)
        """
        line_items = self.get_order_line_items(order_id)
        guaranteed_types = []

        for line_item in line_items:
            line_item_type = line_item.get("lineItemType")
            if line_item_type in GUARANTEED_LINE_ITEM_TYPES:
                guaranteed_types.append(line_item_type)

        return len(guaranteed_types) > 0, guaranteed_types

    def create_order_statement(self, order_id: int):
        """Helper method to create a GAM statement for order filtering.

        Args:
            order_id: GAM order ID as integer

        Returns:
            GAM statement object for order queries
        """
        statement_builder = ad_manager.StatementBuilder()
        statement_builder.Where("orderId = :orderId")
        statement_builder.WithBindVariable("orderId", order_id)
        return statement_builder.ToStatement()

    def create_line_items(
        self,
        order_id: str,
        packages: list,
        start_time: datetime,
        end_time: datetime,
        targeting: dict[str, Any],
        products_map: dict[str, Any],
        log_func: Callable | None = None,
        tenant_id: str | None = None,
        order_name: str | None = None,
        targeting_overlay: Any | None = None,
        package_pricing_info: dict[str, dict] | None = None,
    ) -> list[str]:
        """Create line items for an order.

        Args:
            order_id: GAM order ID
            packages: List of MediaPackage objects
            start_time: Flight start datetime
            end_time: Flight end datetime
            targeting: Base targeting dict (built from targeting overlay)
            products_map: Map of product_id to product config
            log_func: Optional logging function
            tenant_id: Tenant ID for fetching naming templates
            order_name: Order name for line item naming context
            targeting_overlay: Original AdCP targeting overlay for frequency caps, etc.
            package_pricing_info: Optional pricing info per package (AdCP PR #88)
                Maps package_id → {pricing_model, rate, currency, is_fixed, bid_price}

        Returns:
            List of created line item IDs

        Raises:
            ValueError: If required configuration missing
            Exception: If line item creation fails
        """
        if not self.advertiser_id or not self.trafficker_id:
            raise ValueError(
                "Line item creation requires both advertiser_id and trafficker_id. "
                "These must be provided when initializing GAMOrdersManager."
            )

        def log(msg):
            if log_func:
                log_func(msg)
            else:
                logger.info(msg)

        # Get line item naming template from adapter config
        line_item_name_template = "{product_name}"  # Default
        if tenant_id:
            from sqlalchemy import select

            from src.core.database.database_session import get_db_session
            from src.core.database.models import AdapterConfig

            with get_db_session() as db_session:
                stmt = select(AdapterConfig).filter_by(tenant_id=tenant_id)
                adapter_config = db_session.scalars(stmt).first()
                if adapter_config and adapter_config.gam_line_item_name_template:
                    line_item_name_template = adapter_config.gam_line_item_name_template  # type: ignore[assignment]

        created_line_item_ids: list[str] = []
        flight_duration_days = (end_time - start_time).days

        for package_index, package in enumerate(packages, start=1):
            # Get product-specific configuration
            product = products_map.get(package.package_id)
            impl_config = product.get("implementation_config", {}) if product else {}

            # Build line item targeting (merge base targeting with product config)
            line_item_targeting = dict(targeting)  # Copy base targeting

            # Add ad unit/placement targeting from product config
            if impl_config.get("targeted_ad_unit_ids"):
                if "inventoryTargeting" not in line_item_targeting:
                    line_item_targeting["inventoryTargeting"] = {}

                # Validate ad unit IDs are numeric (GAM requires numeric IDs, not codes/names)
                ad_unit_ids = impl_config["targeted_ad_unit_ids"]
                invalid_ids = [id for id in ad_unit_ids if not str(id).isdigit()]
                if invalid_ids:
                    error_msg = (
                        f"Product '{package.package_id}' has invalid ad unit IDs: {invalid_ids}. "
                        f"GAM requires numeric ad unit IDs (e.g., '23312403859'), not ad unit codes or names. "
                        f"\n\nInvalid values found: {', '.join(str(id) for id in invalid_ids)}"
                        f"\n\nTo fix: Update the product's targeted_ad_unit_ids to use numeric IDs from GAM."
                        f"\nFind IDs in GAM Admin UI → Inventory → Ad Units (the numeric ID column)."
                    )
                    log(f"[red]Error: {error_msg}[/red]")
                    raise ValueError(error_msg)

                line_item_targeting["inventoryTargeting"]["targetedAdUnits"] = [
                    {"adUnitId": ad_unit_id, "includeDescendants": impl_config.get("include_descendants", True)}
                    for ad_unit_id in ad_unit_ids
                ]

            if impl_config.get("targeted_placement_ids"):
                if "inventoryTargeting" not in line_item_targeting:
                    line_item_targeting["inventoryTargeting"] = {}
                line_item_targeting["inventoryTargeting"]["targetedPlacements"] = [
                    {"placementId": placement_id} for placement_id in impl_config["targeted_placement_ids"]
                ]

            # Require inventory targeting - no fallback
            if "inventoryTargeting" not in line_item_targeting or not line_item_targeting["inventoryTargeting"]:
                error_msg = (
                    f"Product '{package.package_id}' is not configured with inventory targeting. "
                    f"GAM requires all line items to target specific ad units or placements. "
                    f"\n\nTo fix this product, add one of the following to implementation_config:"
                    f"\n  - 'targeted_ad_unit_ids': ['your_ad_unit_id'] (list of GAM ad unit IDs)"
                    f"\n  - 'targeted_placement_ids': ['your_placement_id'] (list of GAM placement IDs)"
                    f"\n\nYou can find ad unit IDs in GAM Admin UI → Inventory → Ad Units"
                    f"\n\nFor testing, you can use Mock adapter instead of GAM (set ad_server='mock' on tenant)."
                )
                log(f"[red]Error: {error_msg}[/red]")
                raise ValueError(error_msg)

            # Add custom targeting from product config
            # IMPORTANT: Merge without overwriting buyer's targeting (e.g., AEE signals from key_value_pairs)
            if impl_config.get("custom_targeting_keys"):
                if "customTargeting" not in line_item_targeting:
                    line_item_targeting["customTargeting"] = {}
                # Add product custom targeting, but don't overwrite existing keys from buyer
                for key, value in impl_config["custom_targeting_keys"].items():
                    if key not in line_item_targeting["customTargeting"]:
                        line_item_targeting["customTargeting"][key] = value
                    else:
                        log(
                            f"[yellow]Product config custom targeting key '{key}' conflicts with buyer targeting, keeping buyer value[/yellow]"
                        )

            # Build creative placeholders from format_ids
            # First try to get from package.format_ids (buyer-specified)
            creative_placeholders = []

            if package.format_ids:
                from src.core.format_resolver import get_format

                # Validate format types against product supported types
                supported_format_types = impl_config.get("supported_format_types", ["display", "video", "native"])

                for format_id in package.format_ids:
                    # Use format resolver to support custom formats and product overrides
                    try:
                        format_obj = get_format(format_id, tenant_id=tenant_id, product_id=package.package_id)
                    except ValueError as e:
                        error_msg = f"Format lookup failed for '{format_id}': {e}"
                        log(f"[red]Error: {error_msg}[/red]")
                        raise ValueError(error_msg)

                    # Check if format type is supported by product
                    if format_obj.type not in supported_format_types:
                        error_msg = (
                            f"Format '{format_id}' (type: {format_obj.type}) is not supported by product {package.package_id}. "
                            f"Product supports: {', '.join(supported_format_types)}. "
                            f"Configure 'supported_format_types' in product implementation_config if this should be supported."
                        )
                        log(f"[red]Error: {error_msg}[/red]")
                        raise ValueError(error_msg)

                    # Audio formats are not supported in GAM (no creative placeholders)
                    if format_obj.type == "audio":
                        error_msg = (
                            f"Audio format '{format_id}' is not supported. "
                            f"GAM does not support standalone audio line items. "
                            f"Audio can only be used as companion creatives to video ads. "
                            f"To deliver audio ads, use a different ad server (e.g., Triton, Kevel) that supports audio."
                        )
                        log(f"[red]Error: {error_msg}[/red]")
                        raise ValueError(error_msg)

                    # Check if format has GAM-specific config
                    platform_cfg = format_obj.platform_config or {}
                    gam_cfg = platform_cfg.get("gam", {})
                    placeholder_cfg = gam_cfg.get("creative_placeholder", {})

                    # Build creative placeholder
                    placeholder = {
                        "expectedCreativeCount": 1,
                    }

                    # Check for GAM custom creative template (1x1 placeholder)
                    if "creative_template_id" in placeholder_cfg:
                        # Use 1x1 placeholder with custom template
                        placeholder["size"] = {
                            "width": 1,
                            "height": 1,
                            "isAspectRatio": False,
                        }
                        placeholder["creativeTemplateId"] = placeholder_cfg["creative_template_id"]
                        log(
                            f"  Custom template placeholder: 1x1 with template_id={placeholder_cfg['creative_template_id']}"
                        )

                    else:
                        # Use platform config if available, otherwise fall back to requirements
                        if placeholder_cfg:
                            width = placeholder_cfg.get("width")
                            height = placeholder_cfg.get("height")
                            creative_size_type = placeholder_cfg.get("creative_size_type", "PIXEL")
                        else:
                            # Fallback to requirements (legacy formats)
                            requirements = format_obj.requirements or {}
                            width = requirements.get("width")
                            height = requirements.get("height")
                            creative_size_type = "NATIVE" if format_obj.type == "native" else "PIXEL"

                        if width and height:
                            placeholder["size"] = {"width": width, "height": height}
                            placeholder["creativeSizeType"] = creative_size_type

                            # Log video-specific info
                            if format_obj.type == "video":
                                aspect_ratio = (
                                    format_obj.requirements.get("aspect_ratio", "unknown")
                                    if format_obj.requirements
                                    else "unknown"
                                )
                                log(f"  Video placeholder: {width}x{height} ({aspect_ratio} aspect ratio)")
                        else:
                            # For formats without dimensions
                            error_msg = (
                                f"Format '{format_id}' has no width/height configuration for GAM. "
                                f"Add 'platform_config.gam.creative_placeholder' to format definition or "
                                f"ensure format has width/height in requirements."
                            )
                            log(f"[red]Error: {error_msg}[/red]")
                            raise ValueError(error_msg)

                    creative_placeholders.append(placeholder)

            # Fall back to product config only if no valid placeholders from format_ids
            if not creative_placeholders and impl_config.get("creative_placeholders"):
                for placeholder in impl_config["creative_placeholders"]:
                    creative_placeholders.append(
                        {
                            "size": {"width": placeholder["width"], "height": placeholder["height"]},
                            "expectedCreativeCount": placeholder.get("expected_creative_count", 1),
                            "creativeSizeType": "NATIVE" if placeholder.get("is_native") else "PIXEL",
                        }
                    )

            # Require creative placeholders - no defaults
            if not creative_placeholders:
                error_msg = (
                    f"No creative placeholders for package {package.package_id}. "
                    f"Package must have format_ids or product must have creative_placeholders configured."
                )
                log(f"[red]Error: {error_msg}[/red]")
                raise ValueError(error_msg)

            # Determine goal type and units
            goal_type = impl_config.get("primary_goal_type", "LIFETIME")
            goal_unit_type = impl_config.get("primary_goal_unit_type", "IMPRESSIONS")

            if goal_type == "LIFETIME":
                goal_units = package.impressions
            elif goal_type == "DAILY":
                # For DAILY goals, divide total impressions by flight days
                goal_units = int(package.impressions / max(flight_duration_days, 1))
            else:
                # For other goal types (NONE, etc), use package impressions
                goal_units = package.impressions

            # Apply line item naming template
            from src.adapters.gam.utils.constants import GAM_NAME_LIMITS
            from src.adapters.gam.utils.naming import (
                apply_naming_template,
                build_line_item_name_context,
                truncate_name_with_suffix,
            )

            # Get product name from database for template
            product_name = product.get("product_id", package.name) if product else package.name

            line_item_name_context = build_line_item_name_context(
                order_name=order_name or f"Order {order_id}",
                product_name=product_name,
                package_name=package.name,
                package_index=package_index,
            )
            full_line_item_name = apply_naming_template(line_item_name_template, line_item_name_context)

            # Truncate to GAM's 255-character limit
            line_item_name = truncate_name_with_suffix(
                full_line_item_name, GAM_NAME_LIMITS["max_line_item_name_length"]
            )

            # Determine pricing configuration - use package_pricing_info if available, else fallback
            pricing_info = package_pricing_info.get(package.package_id) if package_pricing_info else None

            if pricing_info:
                # Use pricing info from AdCP request (AdCP PR #88)
                from src.adapters.gam.pricing_compatibility import PricingCompatibility

                pricing_model = pricing_info["pricing_model"]
                rate = pricing_info["rate"] if pricing_info["is_fixed"] else pricing_info.get("bid_price", package.cpm)
                currency = pricing_info["currency"]
                is_guaranteed = pricing_info["is_fixed"]

                # Map AdCP pricing model to GAM cost type
                gam_cost_type = PricingCompatibility.get_gam_cost_type(pricing_model)

                # For FLAT_RATE, calculate CPD rate (total budget / days)
                if pricing_model == "flat_rate":
                    rate_per_day = rate / max(flight_duration_days, 1)
                    log(f"  FLAT_RATE pricing: ${rate:,.2f} total → ${rate_per_day:,.2f} per day (CPD)")
                    cost_type = "CPD"
                    cost_per_unit_micro = int(rate_per_day * 1_000_000)
                else:
                    cost_type = gam_cost_type
                    cost_per_unit_micro = int(rate * 1_000_000)

                # Select appropriate line item type based on pricing + guarantees
                line_item_type = PricingCompatibility.select_line_item_type(pricing_model, is_guaranteed)
                priority = PricingCompatibility.get_default_priority(line_item_type)

                # Update goal units based on pricing model
                if pricing_model == "cpc":
                    # CPC: goal should be in clicks, not impressions
                    goal_unit_type = "CLICKS"
                    # Keep goal_units as-is (package.impressions serves as click goal)
                elif pricing_model == "vcpm":
                    # VCPM: goal should be in viewable impressions
                    goal_unit_type = "VIEWABLE_IMPRESSIONS"
                    # Keep goal_units as-is (package.impressions serves as viewable impression goal)
                else:
                    # CPM, FLAT_RATE: use impressions (already set above)
                    pass

                log(
                    f"  Package pricing: {pricing_model.upper()} @ ${rate:,.2f} {currency} "
                    f"→ GAM {cost_type} @ ${rate:,.2f}, line_item_type={line_item_type}, priority={priority}"
                )
            else:
                # Fallback to product config (legacy behavior)
                line_item_type = impl_config.get("line_item_type", "STANDARD")
                priority = impl_config.get("priority", 8)
                cost_type = impl_config.get("cost_type", "CPM")
                currency = "USD"
                cost_per_unit_micro = int(package.cpm * 1_000_000)

            # Build line item object
            line_item = {
                "name": line_item_name,
                "orderId": int(order_id),
                "targeting": line_item_targeting,
                "creativePlaceholders": creative_placeholders,
                "lineItemType": line_item_type,
                "priority": priority,
                "costType": cost_type,
                "costPerUnit": {"currencyCode": currency, "microAmount": cost_per_unit_micro},
                "primaryGoal": {
                    "goalType": goal_type,
                    "unitType": goal_unit_type,
                    "units": goal_units,
                },
                "creativeRotationType": impl_config.get("creative_rotation_type", "EVEN"),
                "deliveryRateType": impl_config.get("delivery_rate_type", "EVENLY"),
                "startDateTime": {
                    "date": {"year": start_time.year, "month": start_time.month, "day": start_time.day},
                    "hour": start_time.hour,
                    "minute": start_time.minute,
                    "second": start_time.second,
                    "timeZoneId": impl_config.get("time_zone", "America/New_York"),
                },
                "endDateTime": {
                    "date": {"year": end_time.year, "month": end_time.month, "day": end_time.day},
                    "hour": end_time.hour,
                    "minute": end_time.minute,
                    "second": end_time.second,
                    "timeZoneId": impl_config.get("time_zone", "America/New_York"),
                },
                # Set status based on whether manual approval is required
                # DRAFT = needs manual approval, READY = ready to serve (when creatives added)
                "status": "READY",  # Always create as READY since creatives will be added
            }

            # Add frequency caps - merge buyer's frequency cap with product config
            frequency_caps = []

            # First, add product-level frequency caps from impl_config
            if impl_config.get("frequency_caps"):
                for cap in impl_config["frequency_caps"]:
                    frequency_caps.append(
                        {
                            "maxImpressions": cap["max_impressions"],
                            "numTimeUnits": cap["time_range"],
                            "timeUnit": cap["time_unit"],
                        }
                    )

            # Then, add buyer's frequency cap from targeting_overlay if present
            if targeting_overlay and targeting_overlay.frequency_cap:
                freq_cap = targeting_overlay.frequency_cap
                # Convert AdCP FrequencyCap (suppress_minutes) to GAM format
                # AdCP: suppress_minutes (e.g., 60 = 1 hour)
                # GAM: maxImpressions=1, numTimeUnits=X, timeUnit="MINUTE"/"HOUR"/"DAY"

                # Determine best GAM time unit
                if freq_cap.suppress_minutes < 60:
                    time_unit = "MINUTE"
                    num_time_units = freq_cap.suppress_minutes
                elif freq_cap.suppress_minutes < 1440:  # Less than 24 hours
                    time_unit = "HOUR"
                    num_time_units = freq_cap.suppress_minutes // 60
                else:
                    time_unit = "DAY"
                    num_time_units = freq_cap.suppress_minutes // 1440

                frequency_caps.append(
                    {
                        "maxImpressions": 1,  # Suppress after 1 impression
                        "numTimeUnits": num_time_units,
                        "timeUnit": time_unit,
                    }
                )
                log(f"Added buyer frequency cap: 1 impression per {num_time_units} {time_unit.lower()}(s)")

            if frequency_caps:
                line_item["frequencyCaps"] = frequency_caps

            # Add competitive exclusion labels
            if impl_config.get("competitive_exclusion_labels"):
                line_item["effectiveAppliedLabels"] = [
                    {"labelId": label} for label in impl_config["competitive_exclusion_labels"]
                ]

            # Add discount if configured
            if impl_config.get("discount_type") and impl_config.get("discount_value"):
                line_item["discount"] = impl_config["discount_value"]
                line_item["discountType"] = impl_config["discount_type"]

            # Determine environment type - prefer buyer's media_type, fallback to product config
            environment_type = line_item_targeting.get("_media_type_environment")  # From targeting overlay
            if not environment_type:
                environment_type = impl_config.get("environment_type", "BROWSER")

            # Clean up internal field from targeting
            if "_media_type_environment" in line_item_targeting:
                del line_item_targeting["_media_type_environment"]

            # Add video-specific settings
            if environment_type == "VIDEO_PLAYER":
                line_item["environmentType"] = "VIDEO_PLAYER"
                if impl_config.get("companion_delivery_option"):
                    line_item["companionDeliveryOption"] = impl_config["companion_delivery_option"]
                if impl_config.get("video_max_duration"):
                    line_item["videoMaxDuration"] = impl_config["video_max_duration"]
                if impl_config.get("skip_offset"):
                    line_item["videoSkippableAdType"] = "ENABLED"
                    line_item["videoSkipOffset"] = impl_config["skip_offset"]
            else:
                line_item["environmentType"] = environment_type

            # Advanced settings
            if impl_config.get("allow_overbook"):
                line_item["allowOverbook"] = True
            if impl_config.get("skip_inventory_check"):
                line_item["skipInventoryCheck"] = True
            if impl_config.get("disable_viewability_avg_revenue_optimization"):
                line_item["disableViewabilityAvgRevenueOptimization"] = True

            if self.dry_run:
                log(f"Would call: line_item_service.createLineItems(['{package.name}'])")
                log(f"  Package: {package.name}")
                log(f"  Line Item Type: {impl_config.get('line_item_type', 'STANDARD')}")
                log(f"  Priority: {impl_config.get('priority', 8)}")
                log(f"  CPM: ${package.cpm}")
                log(f"  Impressions Goal: {package.impressions:,}")
                log(f"  Creative Placeholders: {len(creative_placeholders)} sizes")
                for cp in creative_placeholders[:3]:
                    log(
                        f"    - {cp['size']['width']}x{cp['size']['height']} ({'Native' if cp.get('creativeSizeType') == 'NATIVE' else 'Display'})"
                    )
                if len(creative_placeholders) > 3:
                    log(f"    - ... and {len(creative_placeholders) - 3} more")
                created_line_item_ids.append(f"dry_run_line_item_{len(created_line_item_ids)}")
            else:
                try:
                    line_item_service = self.client_manager.get_service("LineItemService")
                    created_line_items = line_item_service.createLineItems([line_item])
                    if created_line_items:
                        line_item_id = str(created_line_items[0]["id"])
                        created_line_item_ids.append(line_item_id)
                        log(f"✓ Created LineItem ID: {line_item_id} for {package.name}")
                except Exception as e:
                    error_msg = f"Failed to create LineItem for {package.name}: {str(e)}"
                    log(f"[red]Error: {error_msg}[/red]")
                    log(f"[red]Targeting structure: {line_item_targeting}[/red]")
                    raise

        return created_line_item_ids

    def get_advertisers(self) -> list[dict[str, Any]]:
        """Get list of advertisers (companies) from GAM for advertiser selection.

        Returns:
            List of advertisers with id, name, and type for dropdown selection
        """
        logger.info("Loading GAM advertisers")

        if self.dry_run:
            logger.info("Would call: company_service.getCompaniesByStatement(WHERE type='ADVERTISER')")
            # Return mock data for dry-run
            return [
                {"id": "123456789", "name": "Test Advertiser 1", "type": "ADVERTISER"},
                {"id": "987654321", "name": "Test Advertiser 2", "type": "ADVERTISER"},
            ]

        try:
            company_service = self.client_manager.get_service("CompanyService")
            statement_builder = ad_manager.StatementBuilder()
            statement_builder.Where("type = :type")
            statement_builder.WithBindVariable("type", "ADVERTISER")
            statement = statement_builder.ToStatement()

            result = company_service.getCompaniesByStatement(statement)
            companies = result.results if result and hasattr(result, "results") else []

            # Format for UI
            advertisers = []
            for company in companies:
                advertisers.append(
                    {
                        "id": str(company.id),
                        "name": company.name,
                        "type": company.type,
                    }
                )

            logger.info(f"✓ Loaded {len(advertisers)} advertisers from GAM")
            return sorted(advertisers, key=lambda x: x["name"])

        except Exception as e:
            logger.error(f"Error loading advertisers: {str(e)}")
            return []
