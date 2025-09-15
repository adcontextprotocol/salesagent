"""
GAM Orders Manager

Handles order creation, management, status checking, and lifecycle operations
for Google Ad Manager orders.
"""

import logging
from datetime import datetime
from typing import Any

from googleads import ad_manager

logger = logging.getLogger(__name__)


class GAMOrdersManager:
    """Manages Google Ad Manager order operations."""

    def __init__(self, client_manager, advertiser_id: str, trafficker_id: str, dry_run: bool = False):
        """Initialize orders manager.

        Args:
            client_manager: GAMClientManager instance
            advertiser_id: GAM advertiser ID
            trafficker_id: GAM trafficker ID
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
            Exception: If order creation fails
        """
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
        GUARANTEED_LINE_ITEM_TYPES = {"STANDARD", "SPONSORSHIP"}

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
            companies = result.get("results", [])

            # Format for UI
            advertisers = []
            for company in companies:
                advertisers.append(
                    {
                        "id": str(company["id"]),
                        "name": company["name"],
                        "type": company["type"],
                    }
                )

            logger.info(f"✓ Loaded {len(advertisers)} advertisers from GAM")
            return sorted(advertisers, key=lambda x: x["name"])

        except Exception as e:
            logger.error(f"Error loading advertisers: {str(e)}")
            return []
