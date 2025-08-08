"""
Google Ad Manager Orders and Line Items Discovery and Synchronization.

This module provides:
- Order discovery and sync
- Line item discovery and sync
- Delivery stats extraction
- Performance metrics tracking
"""

import json
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

from googleads import ad_manager
from adapters.gam_logging import logger, log_gam_operation, GAMOperation
from adapters.gam_error_handling import with_retry, GAMError
from zeep.helpers import serialize_object


class OrderStatus(Enum):
    """Order status in GAM."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PAUSED = "PAUSED"
    CANCELED = "CANCELED"
    DELETED = "DELETED"


class LineItemStatus(Enum):
    """Line item status in GAM."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"
    CANCELED = "CANCELED"
    DELIVERING = "DELIVERING"  # Active and currently delivering
    READY = "READY"  # Ready to deliver
    COMPLETED = "COMPLETED"  # Finished delivering


@dataclass
class Order:
    """Represents a GAM order."""
    order_id: str
    name: str
    advertiser_id: Optional[str]
    advertiser_name: Optional[str]
    agency_id: Optional[str]
    agency_name: Optional[str]
    trafficker_id: Optional[str]
    trafficker_name: Optional[str]
    salesperson_id: Optional[str]
    salesperson_name: Optional[str]
    status: OrderStatus
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    unlimited_end_date: bool
    total_budget: Optional[float]
    currency_code: Optional[str]
    external_order_id: Optional[str]  # PO number
    po_number: Optional[str]
    notes: Optional[str]
    last_modified_date: Optional[datetime]
    is_programmatic: bool
    applied_labels: List[str]
    effective_applied_labels: List[str]
    custom_field_values: Optional[Dict[str, Any]]
    order_metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['status'] = self.status.value
        # Convert datetime objects to ISO format strings
        if self.start_date:
            data['start_date'] = self.start_date.isoformat()
        if self.end_date:
            data['end_date'] = self.end_date.isoformat()
        if self.last_modified_date:
            data['last_modified_date'] = self.last_modified_date.isoformat()
        return data
    
    @classmethod
    def from_gam_object(cls, gam_order: Dict[str, Any]) -> 'Order':
        """Create from GAM API response."""
        # Extract dates
        start_date = None
        end_date = None
        if 'startDateTime' in gam_order and gam_order['startDateTime']:
            dt = gam_order['startDateTime']
            if dt and 'date' in dt and dt['date']:
                start_date = datetime(dt['date']['year'], dt['date']['month'], dt['date']['day'],
                                    dt.get('hour', 0), dt.get('minute', 0), dt.get('second', 0))
        if 'endDateTime' in gam_order and gam_order['endDateTime']:
            dt = gam_order['endDateTime']
            if dt and 'date' in dt and dt['date']:
                end_date = datetime(dt['date']['year'], dt['date']['month'], dt['date']['day'],
                                  dt.get('hour', 0), dt.get('minute', 0), dt.get('second', 0))
        
        last_modified = None
        if 'lastModifiedDateTime' in gam_order and gam_order['lastModifiedDateTime']:
            dt = gam_order['lastModifiedDateTime']
            if dt and 'date' in dt and dt['date']:
                last_modified = datetime(dt['date']['year'], dt['date']['month'], dt['date']['day'],
                                       dt.get('hour', 0), dt.get('minute', 0), dt.get('second', 0))
        
        # Extract money values
        total_budget = None
        currency_code = None
        if 'totalBudget' in gam_order:
            total_budget = gam_order['totalBudget'].get('microAmount', 0) / 1000000.0
            currency_code = gam_order['totalBudget'].get('currencyCode')
        
        # Extract labels
        applied_labels = []
        if 'appliedLabels' in gam_order:
            applied_labels = [str(label['labelId']) for label in gam_order['appliedLabels']]
        
        effective_labels = []
        if 'effectiveAppliedLabels' in gam_order:
            effective_labels = [str(label['labelId']) for label in gam_order['effectiveAppliedLabels']]
        
        # Extract custom field values
        custom_fields = None
        if 'customFieldValues' in gam_order:
            custom_fields = {cfv['customFieldId']: cfv.get('value') for cfv in gam_order['customFieldValues']}
        
        return cls(
            order_id=str(gam_order['id']),
            name=gam_order['name'],
            advertiser_id=str(gam_order.get('advertiserId')) if gam_order.get('advertiserId') else None,
            advertiser_name=gam_order.get('advertiserName'),
            agency_id=str(gam_order.get('agencyId')) if gam_order.get('agencyId') else None,
            agency_name=gam_order.get('agencyName'),
            trafficker_id=str(gam_order.get('traffickerId')) if gam_order.get('traffickerId') else None,
            trafficker_name=gam_order.get('traffickerName'),
            salesperson_id=str(gam_order.get('salespersonId')) if gam_order.get('salespersonId') else None,
            salesperson_name=gam_order.get('salespersonName'),
            status=OrderStatus(gam_order['status']),
            start_date=start_date,
            end_date=end_date,
            unlimited_end_date=gam_order.get('unlimitedEndDateTime', False),
            total_budget=total_budget,
            currency_code=currency_code,
            external_order_id=gam_order.get('externalOrderId'),
            po_number=gam_order.get('poNumber'),
            notes=gam_order.get('notes'),
            last_modified_date=last_modified,
            is_programmatic=gam_order.get('isProgrammatic', False),
            applied_labels=applied_labels,
            effective_applied_labels=effective_labels,
            custom_field_values=custom_fields,
            order_metadata={k: v for k, v in gam_order.items() 
                          if k not in ['id', 'name', 'advertiserId', 'status', 'startDateTime', 'endDateTime']}
        )


@dataclass
class LineItem:
    """Represents a GAM line item."""
    line_item_id: str
    order_id: str
    name: str
    status: LineItemStatus
    line_item_type: str
    priority: Optional[int]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    unlimited_end_date: bool
    auto_extension_days: Optional[int]
    cost_type: Optional[str]
    cost_per_unit: Optional[float]
    discount_type: Optional[str]
    discount: Optional[float]
    contracted_units_bought: Optional[int]
    delivery_rate_type: Optional[str]
    goal_type: Optional[str]
    primary_goal_type: Optional[str]
    primary_goal_units: Optional[int]
    impression_limit: Optional[int]
    click_limit: Optional[int]
    target_platform: Optional[str]
    environment_type: Optional[str]
    allow_overbook: bool
    skip_inventory_check: bool
    reserve_at_creation: bool
    stats: Optional[Dict[str, Any]]
    delivery_indicator_type: Optional[str]
    delivery_data: Optional[Dict[str, Any]]
    targeting: Optional[Dict[str, Any]]
    creative_placeholders: Optional[List[Dict[str, Any]]]
    frequency_caps: Optional[List[Dict[str, Any]]]
    applied_labels: List[str]
    effective_applied_labels: List[str]
    custom_field_values: Optional[Dict[str, Any]]
    third_party_measurement_settings: Optional[Dict[str, Any]]
    video_max_duration: Optional[int]
    line_item_metadata: Dict[str, Any]
    last_modified_date: Optional[datetime]
    creation_date: Optional[datetime]
    external_id: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['status'] = self.status.value
        # Convert datetime objects to ISO format strings
        if self.start_date:
            data['start_date'] = self.start_date.isoformat()
        if self.end_date:
            data['end_date'] = self.end_date.isoformat()
        if self.last_modified_date:
            data['last_modified_date'] = self.last_modified_date.isoformat()
        if self.creation_date:
            data['creation_date'] = self.creation_date.isoformat()
        return data
    
    @classmethod
    def from_gam_object(cls, gam_line_item: Dict[str, Any]) -> 'LineItem':
        """Create from GAM API response."""
        # Extract dates
        start_date = None
        end_date = None
        creation_date = None
        last_modified = None
        
        if 'startDateTime' in gam_line_item and gam_line_item['startDateTime']:
            dt = gam_line_item['startDateTime']
            if dt and 'date' in dt and dt['date']:
                start_date = datetime(dt['date']['year'], dt['date']['month'], dt['date']['day'],
                                    dt.get('hour', 0), dt.get('minute', 0), dt.get('second', 0))
        if 'endDateTime' in gam_line_item and gam_line_item['endDateTime']:
            dt = gam_line_item['endDateTime']
            if dt and 'date' in dt and dt['date']:
                end_date = datetime(dt['date']['year'], dt['date']['month'], dt['date']['day'],
                                  dt.get('hour', 0), dt.get('minute', 0), dt.get('second', 0))
        if 'creationDateTime' in gam_line_item and gam_line_item['creationDateTime']:
            dt = gam_line_item['creationDateTime']
            if dt and 'date' in dt and dt['date']:
                creation_date = datetime(dt['date']['year'], dt['date']['month'], dt['date']['day'],
                                       dt.get('hour', 0), dt.get('minute', 0), dt.get('second', 0))
        if 'lastModifiedDateTime' in gam_line_item and gam_line_item['lastModifiedDateTime']:
            dt = gam_line_item['lastModifiedDateTime']
            if dt and 'date' in dt and dt['date']:
                last_modified = datetime(dt['date']['year'], dt['date']['month'], dt['date']['day'],
                                   dt.get('hour', 0), dt.get('minute', 0), dt.get('second', 0))
        
        # Extract money values
        cost_per_unit = None
        if 'costPerUnit' in gam_line_item:
            cost_per_unit = gam_line_item['costPerUnit'].get('microAmount', 0) / 1000000.0
        
        # Extract goal units
        primary_goal_units = None
        if 'primaryGoal' in gam_line_item:
            primary_goal_units = gam_line_item['primaryGoal'].get('units')
        
        # Extract labels
        applied_labels = []
        if 'appliedLabels' in gam_line_item:
            applied_labels = [str(label['labelId']) for label in gam_line_item['appliedLabels']]
        
        effective_labels = []
        if 'effectiveAppliedLabels' in gam_line_item:
            effective_labels = [str(label['labelId']) for label in gam_line_item['effectiveAppliedLabels']]
        
        # Extract custom field values
        custom_fields = None
        if 'customFieldValues' in gam_line_item:
            custom_fields = {cfv['customFieldId']: cfv.get('value') for cfv in gam_line_item['customFieldValues']}
        
        # Extract stats if available
        stats = None
        if 'stats' in gam_line_item:
            stats = {
                'impressions': gam_line_item['stats'].get('impressionsDelivered'),
                'clicks': gam_line_item['stats'].get('clicksDelivered'),
                'video_completions': gam_line_item['stats'].get('videoCompletionsDelivered'),
                'video_starts': gam_line_item['stats'].get('videoStartsDelivered'),
                'viewable_impressions': gam_line_item['stats'].get('viewableImpressionsDelivered')
            }
        
        # Extract delivery data
        delivery_data = None
        if 'deliveryData' in gam_line_item:
            delivery_data = serialize_object(gam_line_item['deliveryData'])
        
        # Extract targeting
        targeting = None
        if 'targeting' in gam_line_item:
            targeting = serialize_object(gam_line_item['targeting'])
        
        # Extract creative placeholders
        creative_placeholders = None
        if 'creativePlaceholders' in gam_line_item:
            creative_placeholders = [serialize_object(cp) for cp in gam_line_item['creativePlaceholders']]
        
        # Extract frequency caps
        frequency_caps = None
        if 'frequencyCaps' in gam_line_item:
            frequency_caps = [serialize_object(fc) for fc in gam_line_item['frequencyCaps']]
        
        return cls(
            line_item_id=str(gam_line_item['id']),
            order_id=str(gam_line_item['orderId']),
            name=gam_line_item['name'],
            status=LineItemStatus(gam_line_item['status']),
            line_item_type=gam_line_item['lineItemType'],
            priority=gam_line_item.get('priority'),
            start_date=start_date,
            end_date=end_date,
            unlimited_end_date=gam_line_item.get('unlimitedEndDateTime', False),
            auto_extension_days=gam_line_item.get('autoExtensionDays'),
            cost_type=gam_line_item.get('costType'),
            cost_per_unit=cost_per_unit,
            discount_type=gam_line_item.get('discountType'),
            discount=gam_line_item.get('discount'),
            contracted_units_bought=gam_line_item.get('contractedUnitsBought'),
            delivery_rate_type=gam_line_item.get('deliveryRateType'),
            goal_type=gam_line_item.get('goalType'),
            primary_goal_type=gam_line_item.get('primaryGoal', {}).get('goalType'),
            primary_goal_units=primary_goal_units,
            impression_limit=gam_line_item.get('impressionLimit'),
            click_limit=gam_line_item.get('clickLimit'),
            target_platform=gam_line_item.get('targetPlatform'),
            environment_type=gam_line_item.get('environmentType'),
            allow_overbook=gam_line_item.get('allowOverbook', False),
            skip_inventory_check=gam_line_item.get('skipInventoryCheck', False),
            reserve_at_creation=gam_line_item.get('reserveAtCreation', False),
            stats=stats,
            delivery_indicator_type=gam_line_item.get('deliveryIndicator', {}).get('deliveryIndicatorType') if 'deliveryIndicator' in gam_line_item else None,
            delivery_data=delivery_data,
            targeting=targeting,
            creative_placeholders=creative_placeholders,
            frequency_caps=frequency_caps,
            applied_labels=applied_labels,
            effective_applied_labels=effective_labels,
            custom_field_values=custom_fields,
            third_party_measurement_settings=serialize_object(gam_line_item['thirdPartyMeasurementSettings']) if 'thirdPartyMeasurementSettings' in gam_line_item else None,
            video_max_duration=gam_line_item.get('videoMaxDuration'),
            line_item_metadata={k: v for k, v in gam_line_item.items() 
                              if k not in ['id', 'orderId', 'name', 'status', 'lineItemType']},
            last_modified_date=last_modified,
            creation_date=creation_date,
            external_id=gam_line_item.get('externalId')
        )


class GAMOrdersDiscovery:
    """Discovery and sync service for GAM orders and line items."""
    
    def __init__(self, gam_client, tenant_id: str):
        """
        Initialize discovery service.
        
        Args:
            gam_client: Initialized GAM client
            tenant_id: Tenant ID for this discovery
        """
        self.client = gam_client
        self.tenant_id = tenant_id
        self.orders: Dict[str, Order] = {}
        self.line_items: Dict[str, LineItem] = {}
        self.last_sync: Optional[datetime] = None
    
    @with_retry()
    @log_gam_operation(GAMOperation.GET_REPORT, "Order")
    def discover_orders(self, limit: Optional[int] = None) -> List[Order]:
        """
        Discover all orders from GAM.
        
        Args:
            limit: Optional limit on number of orders to fetch
            
        Returns:
            List of discovered orders
        """
        logger.info(f"Discovering orders for tenant {self.tenant_id}")
        
        order_service = self.client.GetService('OrderService', version='v202411')
        
        # Build statement to get all orders
        statement_builder = ad_manager.StatementBuilder(version='v202411')
        if limit:
            statement_builder.limit = limit
        
        discovered_orders = []
        
        while True:
            response = order_service.getOrdersByStatement(
                statement_builder.ToStatement()
            )
            
            if 'results' in response and response['results']:
                for gam_order in response['results']:
                    try:
                        # Serialize SUDS object to dict
                        order_dict = serialize_object(gam_order)
                        order = Order.from_gam_object(order_dict)
                        self.orders[order.order_id] = order
                        discovered_orders.append(order)
                    except Exception as e:
                        order_id = 'unknown'
                        try:
                            order_id = str(getattr(gam_order, 'id', 'unknown'))
                        except:
                            pass
                        logger.error(f"Error processing order {order_id}: {e}")
                        continue
                
                statement_builder.offset += len(response['results'])
                logger.info(f"Fetched {len(response['results'])} orders (total: {len(discovered_orders)})")
            else:
                break
        
        logger.info(f"Discovered {len(discovered_orders)} orders")
        return discovered_orders
    
    @with_retry()
    @log_gam_operation(GAMOperation.GET_REPORT, "LineItem")
    def discover_line_items(self, order_id: Optional[str] = None, limit: Optional[int] = None) -> List[LineItem]:
        """
        Discover line items from GAM.
        
        Args:
            order_id: Optional order ID to filter by
            limit: Optional limit on number of line items to fetch
            
        Returns:
            List of discovered line items
        """
        logger.info(f"Discovering line items for tenant {self.tenant_id}" + 
                   (f" (order: {order_id})" if order_id else ""))
        
        line_item_service = self.client.GetService('LineItemService', version='v202411')
        
        # Build statement to get line items
        statement_builder = ad_manager.StatementBuilder(version='v202411')
        if order_id:
            statement_builder.Where('orderId = :orderId').WithBindVariable('orderId', int(order_id))
        if limit:
            statement_builder.limit = limit
        
        discovered_line_items = []
        
        while True:
            response = line_item_service.getLineItemsByStatement(
                statement_builder.ToStatement()
            )
            
            if 'results' in response and response['results']:
                for gam_line_item in response['results']:
                    try:
                        # Serialize SUDS object to dict
                        line_item_dict = serialize_object(gam_line_item)
                        line_item = LineItem.from_gam_object(line_item_dict)
                        self.line_items[line_item.line_item_id] = line_item
                        discovered_line_items.append(line_item)
                    except Exception as e:
                        li_id = 'unknown'
                        try:
                            li_id = str(getattr(gam_line_item, 'id', 'unknown'))
                        except:
                            pass
                        logger.error(f"Error processing line item {li_id}: {e}")
                        continue
                
                statement_builder.offset += len(response['results'])
                logger.info(f"Fetched {len(response['results'])} line items (total: {len(discovered_line_items)})")
            else:
                break
        
        logger.info(f"Discovered {len(discovered_line_items)} line items")
        return discovered_line_items
    
    def sync_all(self) -> Dict[str, Any]:
        """
        Sync all orders and line items from GAM.
        
        Returns:
            Summary of synced data
        """
        logger.info(f"Starting full orders sync for tenant {self.tenant_id}")
        
        start_time = datetime.now()
        
        # Clear existing data
        self.orders.clear()
        self.line_items.clear()
        
        # Discover all data
        orders = self.discover_orders()
        line_items = self.discover_line_items()
        
        self.last_sync = datetime.now()
        
        # Group line items by order
        line_items_by_order = {}
        for li in line_items:
            if li.order_id not in line_items_by_order:
                line_items_by_order[li.order_id] = []
            line_items_by_order[li.order_id].append(li)
        
        summary = {
            'tenant_id': self.tenant_id,
            'sync_time': self.last_sync.isoformat(),
            'duration_seconds': (self.last_sync - start_time).total_seconds(),
            'orders': {
                'total': len(orders),
                'by_status': {}
            },
            'line_items': {
                'total': len(line_items),
                'by_status': {},
                'by_type': {},
                'by_order': {order_id: len(items) for order_id, items in line_items_by_order.items()}
            }
        }
        
        # Count orders by status
        for order in orders:
            status = order.status.value
            if status not in summary['orders']['by_status']:
                summary['orders']['by_status'][status] = 0
            summary['orders']['by_status'][status] += 1
        
        # Count line items by status and type
        for li in line_items:
            status = li.status.value
            if status not in summary['line_items']['by_status']:
                summary['line_items']['by_status'][status] = 0
            summary['line_items']['by_status'][status] += 1
            
            li_type = li.line_item_type
            if li_type not in summary['line_items']['by_type']:
                summary['line_items']['by_type'][li_type] = 0
            summary['line_items']['by_type'][li_type] += 1
        
        logger.info(f"Orders sync completed: {summary}")
        return summary