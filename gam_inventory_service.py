"""
Service layer for GAM inventory management.

This service:
- Syncs inventory from GAM to database
- Provides inventory browsing and search
- Manages product-inventory mappings
- Handles inventory updates and caching
"""

import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from models import GAMInventory, ProductInventoryMapping, Product, Tenant
from adapters.gam_inventory_discovery import (
    GAMInventoryDiscovery, AdUnit, Placement, Label,
    AdUnitStatus, CustomTargetingKey, CustomTargetingValue, AudienceSegment
)
from database import db_session

logger = logging.getLogger(__name__)


class GAMInventoryService:
    """Service for managing GAM inventory data."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def sync_tenant_inventory(self, tenant_id: str, gam_client) -> Dict[str, Any]:
        """
        Sync all inventory for a tenant from GAM to database.
        
        Args:
            tenant_id: Tenant ID
            gam_client: Initialized GAM client
            
        Returns:
            Sync summary with counts and timing
        """
        logger.info(f"Starting inventory sync for tenant {tenant_id}")
        
        # Create discovery instance
        discovery = GAMInventoryDiscovery(gam_client, tenant_id)
        
        # Perform discovery
        sync_summary = discovery.sync_all()
        
        # Save to database
        self._save_inventory_to_db(tenant_id, discovery)
        
        # Update tenant config with sync timestamp
        tenant = self.db.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if tenant:
            if 'gam_inventory' not in tenant.config:
                tenant.config['gam_inventory'] = {}
            tenant.config['gam_inventory']['last_sync'] = datetime.now().isoformat()
            self.db.commit()
        
        return sync_summary
    
    def _save_inventory_to_db(self, tenant_id: str, discovery: GAMInventoryDiscovery):
        """Save discovered inventory to database."""
        sync_time = datetime.now()
        
        # Process ad units
        for ad_unit in discovery.ad_units.values():
            self._upsert_inventory_item(
                tenant_id=tenant_id,
                inventory_type='ad_unit',
                inventory_id=ad_unit.id,
                name=ad_unit.name,
                path=ad_unit.path,
                status=ad_unit.status.value,
                inventory_metadata={
                    'ad_unit_code': ad_unit.ad_unit_code,
                    'parent_id': ad_unit.parent_id,
                    'description': ad_unit.description,
                    'target_window': ad_unit.target_window,
                    'explicitly_targeted': ad_unit.explicitly_targeted,
                    'has_children': ad_unit.has_children,
                    'sizes': ad_unit.sizes,
                    'effective_applied_labels': ad_unit.effective_applied_labels
                },
                last_synced=sync_time
            )
        
        # Process placements
        for placement in discovery.placements.values():
            self._upsert_inventory_item(
                tenant_id=tenant_id,
                inventory_type='placement',
                inventory_id=placement.id,
                name=placement.name,
                path=[placement.name],  # Placements don't have hierarchy
                status=placement.status,
                inventory_metadata={
                    'placement_code': placement.placement_code,
                    'description': placement.description,
                    'is_ad_sense_targeting_enabled': placement.is_ad_sense_targeting_enabled,
                    'ad_unit_ids': placement.ad_unit_ids,
                    'targeting_description': placement.targeting_description
                },
                last_synced=sync_time
            )
        
        # Process labels
        for label in discovery.labels.values():
            self._upsert_inventory_item(
                tenant_id=tenant_id,
                inventory_type='label',
                inventory_id=label.id,
                name=label.name,
                path=[label.name],
                status='ACTIVE' if label.is_active else 'INACTIVE',
                inventory_metadata={
                    'description': label.description,
                    'ad_category': label.ad_category,
                    'label_type': label.label_type
                },
                last_synced=sync_time
            )
        
        # Process custom targeting keys
        for key in discovery.custom_targeting_keys.values():
            self._upsert_inventory_item(
                tenant_id=tenant_id,
                inventory_type='custom_targeting_key',
                inventory_id=key.id,
                name=key.name,
                path=[key.display_name],
                status=key.status,
                inventory_metadata={
                    'display_name': key.display_name,
                    'type': key.type,  # PREDEFINED or FREEFORM
                    'reportable_type': key.reportable_type
                },
                last_synced=sync_time
            )
            
            # Process values for this key
            values = discovery.custom_targeting_values.get(key.id, [])
            for value in values:
                self._upsert_inventory_item(
                    tenant_id=tenant_id,
                    inventory_type='custom_targeting_value',
                    inventory_id=value.id,
                    name=value.name,
                    path=[key.display_name, value.display_name],
                    status=value.status,
                    inventory_metadata={
                        'custom_targeting_key_id': value.custom_targeting_key_id,
                        'display_name': value.display_name,
                        'match_type': value.match_type,
                        'key_name': key.name,
                        'key_display_name': key.display_name
                    },
                    last_synced=sync_time
                )
        
        # Process audience segments
        for segment in discovery.audience_segments.values():
            self._upsert_inventory_item(
                tenant_id=tenant_id,
                inventory_type='audience_segment',
                inventory_id=segment.id,
                name=segment.name,
                path=[segment.type, segment.name],  # e.g. ["FIRST_PARTY", "Sports Enthusiasts"]
                status=segment.status,
                inventory_metadata={
                    'description': segment.description,
                    'category_ids': segment.category_ids,
                    'type': segment.type,  # FIRST_PARTY or THIRD_PARTY
                    'size': segment.size,
                    'data_provider_name': segment.data_provider_name,
                    'segment_type': segment.segment_type  # RULE_BASED, SHARED, etc.
                },
                last_synced=sync_time
            )
        
        # Mark old items as potentially stale
        stale_cutoff = sync_time - timedelta(seconds=1)
        self.db.query(GAMInventory).filter(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.last_synced < stale_cutoff
            )
        ).update({'status': 'STALE'})
        
        self.db.commit()
    
    def _upsert_inventory_item(self, **kwargs):
        """Insert or update inventory item."""
        existing = self.db.query(GAMInventory).filter(
            and_(
                GAMInventory.tenant_id == kwargs['tenant_id'],
                GAMInventory.inventory_type == kwargs['inventory_type'],
                GAMInventory.inventory_id == kwargs['inventory_id']
            )
        ).first()
        
        if existing:
            # Update existing
            for key, value in kwargs.items():
                setattr(existing, key, value)
        else:
            # Create new
            inventory_item = GAMInventory(**kwargs)
            self.db.add(inventory_item)
    
    def get_ad_unit_tree(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get hierarchical ad unit tree from database.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Hierarchical tree structure
        """
        # Get all ad units
        ad_units = self.db.query(GAMInventory).filter(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == 'ad_unit',
                GAMInventory.status != 'STALE'
            )
        ).all()
        
        # Build lookup maps
        unit_map = {}
        root_units = []
        
        for unit in ad_units:
            unit_data = {
                'id': unit.inventory_id,
                'name': unit.name,
                'path': unit.path,
                'status': unit.status,
                'metadata': unit.inventory_metadata,
                'children': []
            }
            unit_map[unit.inventory_id] = unit_data
            
            # Check if root (no parent or parent not in path)
            parent_id = unit.inventory_metadata.get('parent_id')
            if not parent_id:
                root_units.append(unit_data)
        
        # Build hierarchy
        for unit in ad_units:
            parent_id = unit.inventory_metadata.get('parent_id')
            if parent_id and parent_id in unit_map:
                unit_map[parent_id]['children'].append(unit_map[unit.inventory_id])
        
        # Get sync info
        tenant = self.db.query(Tenant).filter_by(tenant_id=tenant_id).first()
        last_sync = None
        if tenant and 'gam_inventory' in tenant.config:
            last_sync = tenant.config['gam_inventory'].get('last_sync')
        
        return {
            'root_units': root_units,
            'total_units': len(ad_units),
            'last_sync': last_sync,
            'needs_refresh': self._needs_refresh(last_sync)
        }
    
    def _needs_refresh(self, last_sync_str: Optional[str]) -> bool:
        """Check if inventory needs refresh (older than 24 hours)."""
        if not last_sync_str:
            return True
        
        try:
            last_sync = datetime.fromisoformat(last_sync_str)
            return datetime.now() - last_sync > timedelta(hours=24)
        except:
            return True
    
    def search_inventory(self, 
                        tenant_id: str,
                        query: Optional[str] = None,
                        inventory_type: Optional[str] = None,
                        status: Optional[str] = None,
                        sizes: Optional[List[Dict[str, int]]] = None) -> List[Dict[str, Any]]:
        """
        Search inventory with filters.
        
        Args:
            tenant_id: Tenant ID
            query: Text search in name/path
            inventory_type: Filter by type (ad_unit, placement, label)
            status: Filter by status
            sizes: Filter ad units by size support
            
        Returns:
            List of matching inventory items
        """
        filters = [
            GAMInventory.tenant_id == tenant_id,
            GAMInventory.status != 'STALE'
        ]
        
        if inventory_type:
            filters.append(GAMInventory.inventory_type == inventory_type)
        
        if status:
            filters.append(GAMInventory.status == status)
        
        if query:
            # Search in name and path
            filters.append(
                or_(
                    GAMInventory.name.ilike(f'%{query}%'),
                    func.cast(GAMInventory.path, String).ilike(f'%{query}%')
                )
            )
        
        results = self.db.query(GAMInventory).filter(and_(*filters)).all()
        
        # Filter by sizes if specified
        if sizes and inventory_type in (None, 'ad_unit'):
            filtered_results = []
            for result in results:
                if result.inventory_type != 'ad_unit':
                    if inventory_type is None:
                        continue
                    filtered_results.append(result)
                    continue
                
                unit_sizes = result.inventory_metadata.get('sizes', [])
                has_matching_size = False
                
                for required_size in sizes:
                    for unit_size in unit_sizes:
                        if (unit_size['width'] == required_size['width'] and 
                            unit_size['height'] == required_size['height']):
                            has_matching_size = True
                            break
                    if has_matching_size:
                        break
                
                if has_matching_size:
                    filtered_results.append(result)
            
            results = filtered_results
        
        # Convert to dict format
        return [
            {
                'id': item.inventory_id,
                'type': item.inventory_type,
                'name': item.name,
                'path': item.path,
                'status': item.status,
                'metadata': item.inventory_metadata,
                'last_synced': item.last_synced.isoformat()
            }
            for item in results
        ]
    
    def get_product_inventory(self, tenant_id: str, product_id: str) -> Dict[str, Any]:
        """
        Get inventory mappings for a product.
        
        Args:
            tenant_id: Tenant ID
            product_id: Product ID
            
        Returns:
            Product inventory configuration
        """
        # Get product
        product = self.db.query(Product).filter(
            and_(
                Product.tenant_id == tenant_id,
                Product.product_id == product_id
            )
        ).first()
        
        if not product:
            return None
        
        # Get mappings
        mappings = self.db.query(ProductInventoryMapping).filter(
            and_(
                ProductInventoryMapping.tenant_id == tenant_id,
                ProductInventoryMapping.product_id == product_id
            )
        ).all()
        
        # Get inventory details
        ad_units = []
        placements = []
        
        for mapping in mappings:
            inventory = self.db.query(GAMInventory).filter(
                and_(
                    GAMInventory.tenant_id == tenant_id,
                    GAMInventory.inventory_type == mapping.inventory_type,
                    GAMInventory.inventory_id == mapping.inventory_id
                )
            ).first()
            
            if inventory:
                item = {
                    'id': inventory.inventory_id,
                    'name': inventory.name,
                    'path': inventory.path,
                    'is_primary': mapping.is_primary,
                    'metadata': inventory.inventory_metadata
                }
                
                if mapping.inventory_type == 'ad_unit':
                    ad_units.append(item)
                elif mapping.inventory_type == 'placement':
                    placements.append(item)
        
        return {
            'product_id': product_id,
            'product_name': product.name,
            'ad_units': ad_units,
            'placements': placements,
            'total_mappings': len(mappings)
        }
    
    def update_product_inventory(self,
                               tenant_id: str,
                               product_id: str,
                               ad_unit_ids: List[str],
                               placement_ids: Optional[List[str]] = None,
                               primary_ad_unit_id: Optional[str] = None) -> bool:
        """
        Update product inventory mappings.
        
        Args:
            tenant_id: Tenant ID
            product_id: Product ID
            ad_unit_ids: List of ad unit IDs to map
            placement_ids: Optional list of placement IDs
            primary_ad_unit_id: Optional primary ad unit
            
        Returns:
            Success boolean
        """
        try:
            # Verify product exists
            product = self.db.query(Product).filter(
                and_(
                    Product.tenant_id == tenant_id,
                    Product.product_id == product_id
                )
            ).first()
            
            if not product:
                return False
            
            # Delete existing mappings
            self.db.query(ProductInventoryMapping).filter(
                and_(
                    ProductInventoryMapping.tenant_id == tenant_id,
                    ProductInventoryMapping.product_id == product_id
                )
            ).delete()
            
            # Add new ad unit mappings
            for ad_unit_id in ad_unit_ids:
                mapping = ProductInventoryMapping(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    inventory_type='ad_unit',
                    inventory_id=ad_unit_id,
                    is_primary=(ad_unit_id == primary_ad_unit_id)
                )
                self.db.add(mapping)
            
            # Add placement mappings if provided
            if placement_ids:
                for placement_id in placement_ids:
                    mapping = ProductInventoryMapping(
                        tenant_id=tenant_id,
                        product_id=product_id,
                        inventory_type='placement',
                        inventory_id=placement_id,
                        is_primary=False
                    )
                    self.db.add(mapping)
            
            # Update product implementation config
            if not product.implementation_config:
                product.implementation_config = {}
            
            product.implementation_config['targeted_ad_unit_ids'] = ad_unit_ids
            if placement_ids:
                product.implementation_config['targeted_placement_ids'] = placement_ids
            
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to update product inventory: {e}")
            self.db.rollback()
            return False
    
    def suggest_inventory_for_product(self,
                                    tenant_id: str,
                                    product_id: str,
                                    limit: int = 20) -> List[Dict[str, Any]]:
        """
        Suggest inventory based on product configuration.
        
        Args:
            tenant_id: Tenant ID
            product_id: Product ID
            limit: Maximum suggestions to return
            
        Returns:
            List of suggested inventory items with scores
        """
        # Get product
        product = self.db.query(Product).filter(
            and_(
                Product.tenant_id == tenant_id,
                Product.product_id == product_id
            )
        ).first()
        
        if not product:
            return []
        
        # Extract product characteristics
        creative_sizes = []
        if product.formats:
            # Parse formats to get sizes
            for format_id in product.formats:
                if 'display' in format_id:
                    # Extract size from format like "display_300x250"
                    parts = format_id.split('_')
                    if len(parts) > 1 and 'x' in parts[1]:
                        width, height = parts[1].split('x')
                        creative_sizes.append({
                            'width': int(width),
                            'height': int(height)
                        })
        
        # Get keywords from product name and description
        keywords = []
        if product.name:
            keywords.extend(product.name.lower().split())
        if product.description:
            keywords.extend(product.description.lower().split()[:5])  # First 5 words
        
        # Search for matching ad units
        suggestions = []
        
        # Get active ad units
        ad_units = self.db.query(GAMInventory).filter(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == 'ad_unit',
                GAMInventory.status == 'ACTIVE'
            )
        ).all()
        
        for unit in ad_units:
            score = 0
            reasons = []
            
            # Check size match
            unit_sizes = unit.inventory_metadata.get('sizes', [])
            for creative_size in creative_sizes:
                for unit_size in unit_sizes:
                    if (unit_size['width'] == creative_size['width'] and 
                        unit_size['height'] == creative_size['height']):
                        score += 10
                        reasons.append(f"Size match: {unit_size['width']}x{unit_size['height']}")
            
            # Check keyword match
            unit_text = ' '.join([unit.name.lower()] + [p.lower() for p in unit.path])
            for keyword in keywords:
                if keyword in unit_text:
                    score += 5
                    reasons.append(f"Keyword match: {keyword}")
            
            # Prefer explicitly targeted units
            if unit.inventory_metadata.get('explicitly_targeted'):
                score += 3
                reasons.append("Explicitly targeted")
            
            # Prefer specific placements
            if len(unit.path) > 2:
                score += 2
                reasons.append("Specific placement")
            
            if score > 0:
                suggestions.append({
                    'inventory': {
                        'id': unit.inventory_id,
                        'name': unit.name,
                        'path': ' > '.join(unit.path),
                        'sizes': unit_sizes
                    },
                    'score': score,
                    'reasons': reasons
                })
        
        # Sort by score and limit
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        return suggestions[:limit]
    
    def get_all_targeting_data(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get all targeting data for browsing.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with all targeting data organized by type
        """
        # Get custom targeting keys
        custom_keys = self.db.query(GAMInventory).filter(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == 'custom_targeting_key',
                GAMInventory.status != 'STALE'
            )
        ).all()
        
        # Get custom targeting values grouped by key
        custom_values = {}
        all_values = self.db.query(GAMInventory).filter(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == 'custom_targeting_value',
                GAMInventory.status != 'STALE'
            )
        ).all()
        
        for value in all_values:
            key_id = value.inventory_metadata.get('custom_targeting_key_id')
            if key_id:
                if key_id not in custom_values:
                    custom_values[key_id] = []
                custom_values[key_id].append({
                    'id': value.inventory_id,
                    'name': value.name,
                    'display_name': value.inventory_metadata.get('display_name', value.name),
                    'match_type': value.inventory_metadata.get('match_type', 'EXACT'),
                    'status': value.status
                })
        
        # Get audience segments
        audiences = self.db.query(GAMInventory).filter(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == 'audience_segment',
                GAMInventory.status != 'STALE'
            )
        ).all()
        
        # Get labels
        labels = self.db.query(GAMInventory).filter(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == 'label',
                GAMInventory.status != 'STALE'
            )
        ).all()
        
        # Get last sync info
        tenant = self.db.query(Tenant).filter_by(tenant_id=tenant_id).first()
        last_sync = None
        if tenant and 'gam_inventory' in tenant.config:
            last_sync = tenant.config['gam_inventory'].get('last_sync')
        
        # Format response
        return {
            'customKeys': [
                {
                    'id': key.inventory_id,
                    'name': key.name,
                    'display_name': key.inventory_metadata.get('display_name', key.name),
                    'type': key.inventory_metadata.get('type', 'UNKNOWN'),
                    'status': key.status,
                    'metadata': {
                        'reportable_type': key.inventory_metadata.get('reportable_type'),
                        'values_count': len(custom_values.get(key.inventory_id, []))
                    }
                }
                for key in custom_keys
            ],
            'customValues': custom_values,
            'audiences': [
                {
                    'id': seg.inventory_id,
                    'name': seg.name,
                    'description': seg.inventory_metadata.get('description'),
                    'type': seg.inventory_metadata.get('type', 'UNKNOWN'),
                    'size': seg.inventory_metadata.get('size'),
                    'data_provider_name': seg.inventory_metadata.get('data_provider_name'),
                    'segment_type': seg.inventory_metadata.get('segment_type', 'UNKNOWN'),
                    'status': seg.status,
                    'category_ids': seg.inventory_metadata.get('category_ids', [])
                }
                for seg in audiences
            ],
            'labels': [
                {
                    'id': label.inventory_id,
                    'name': label.name,
                    'description': label.inventory_metadata.get('description'),
                    'is_active': label.status == 'ACTIVE',
                    'ad_category': label.inventory_metadata.get('ad_category'),
                    'label_type': label.inventory_metadata.get('label_type', 'UNKNOWN')
                }
                for label in labels
            ],
            'last_sync': last_sync
        }


def create_inventory_endpoints(app):
    """Create Flask endpoints for inventory management."""
    
    @app.route('/api/tenant/<tenant_id>/inventory/sync', methods=['POST'])
    def sync_inventory(tenant_id):
        """Trigger inventory sync for tenant."""
        from flask import jsonify
        
        try:
            # Get GAM client
            from adapters.google_ad_manager import GoogleAdManager
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                return jsonify({'error': 'Tenant not found'}), 404
            
            gam_config = tenant.config.get('adapters', {}).get('google_ad_manager', {})
            if not gam_config.get('enabled'):
                return jsonify({'error': 'GAM not enabled for tenant'}), 400
            
            # Create dummy principal for client initialization
            from models import Principal
            principal = Principal(
                tenant_id=tenant_id,
                principal_id='system',
                name='System',
                platform_mappings={}
            )
            
            adapter = GoogleAdManager(gam_config, principal, tenant_id=tenant_id)
            
            # Perform sync
            service = GAMInventoryService(db_session)
            summary = service.sync_tenant_inventory(tenant_id, adapter.client)
            
            return jsonify(summary)
            
        except Exception as e:
            logger.error(f"Inventory sync failed: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/tenant/<tenant_id>/inventory/tree')
    def get_inventory_tree(tenant_id):
        """Get ad unit tree for tenant."""
        from flask import jsonify
        
        try:
            service = GAMInventoryService(db_session)
            tree = service.get_ad_unit_tree(tenant_id)
            return jsonify(tree)
            
        except Exception as e:
            logger.error(f"Failed to get inventory tree: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/tenant/<tenant_id>/inventory/search')
    def search_inventory(tenant_id):
        """Search inventory with filters."""
        from flask import request, jsonify
        
        try:
            service = GAMInventoryService(db_session)
            results = service.search_inventory(
                tenant_id=tenant_id,
                query=request.args.get('q'),
                inventory_type=request.args.get('type'),
                status=request.args.get('status')
            )
            return jsonify({
                'results': results,
                'total': len(results)
            })
            
        except Exception as e:
            logger.error(f"Inventory search failed: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/tenant/<tenant_id>/product/<product_id>/inventory')
    def get_product_inventory(tenant_id, product_id):
        """Get inventory configuration for a product."""
        from flask import jsonify
        
        try:
            service = GAMInventoryService(db_session)
            config = service.get_product_inventory(tenant_id, product_id)
            if not config:
                return jsonify({'error': 'Product not found'}), 404
            return jsonify(config)
            
        except Exception as e:
            logger.error(f"Failed to get product inventory: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/tenant/<tenant_id>/product/<product_id>/inventory', methods=['POST'])
    def update_product_inventory(tenant_id, product_id):
        """Update inventory mappings for a product."""
        from flask import request, jsonify
        
        try:
            data = request.get_json()
            
            service = GAMInventoryService(db_session)
            success = service.update_product_inventory(
                tenant_id=tenant_id,
                product_id=product_id,
                ad_unit_ids=data.get('ad_unit_ids', []),
                placement_ids=data.get('placement_ids'),
                primary_ad_unit_id=data.get('primary_ad_unit_id')
            )
            
            if success:
                return jsonify({'status': 'success'})
            else:
                return jsonify({'error': 'Update failed'}), 400
                
        except Exception as e:
            logger.error(f"Failed to update product inventory: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/tenant/<tenant_id>/product/<product_id>/inventory/suggest')
    def suggest_product_inventory(tenant_id, product_id):
        """Get inventory suggestions for a product."""
        from flask import jsonify
        
        try:
            service = GAMInventoryService(db_session)
            suggestions = service.suggest_inventory_for_product(
                tenant_id=tenant_id,
                product_id=product_id
            )
            return jsonify({
                'suggestions': suggestions,
                'total': len(suggestions)
            })
            
        except Exception as e:
            logger.error(f"Failed to get inventory suggestions: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/tenant/<tenant_id>/targeting/all')
    def get_all_targeting(tenant_id):
        """Get all targeting data for browsing."""
        from flask import jsonify
        
        try:
            service = GAMInventoryService(db_session)
            targeting_data = service.get_all_targeting_data(tenant_id)
            return jsonify(targeting_data)
            
        except Exception as e:
            logger.error(f"Failed to get targeting data: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500