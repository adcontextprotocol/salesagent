#!/usr/bin/env python3
"""
Unit tests for GAM Line Item Viewer functionality.

Tests the API endpoint, data conversion, and display logic.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import the functions we're testing
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestGAMLineItemViewer:
    """Test suite for GAM Line Item Viewer."""
    
    @pytest.fixture
    def mock_line_item_response(self):
        """Mock GAM line item response data."""
        return {
            'id': 7046143587,
            'name': 'Test Line Item',
            'orderId': 12345,
            'status': 'DELIVERING',
            'lineItemType': 'STANDARD',
            'priority': 8,
            'costType': 'CPM',
            'costPerUnit': {
                'currencyCode': 'USD',
                'microAmount': 4000000  # $4 CPM
            },
            'unitsBought': 1000000,
            'stats': {
                'impressionsDelivered': 500000,
                'clicksDelivered': 2500,
                'viewableImpressionsDelivered': 400000
            },
            'startDateTime': {
                'date': {'year': 2025, 'month': 2, 'day': 1},
                'hour': 0,
                'minute': 0,
                'second': 0,
                'timeZoneId': 'America/New_York'
            },
            'endDateTime': {
                'date': {'year': 2025, 'month': 2, 'day': 28},
                'hour': 23,
                'minute': 59,
                'second': 59,
                'timeZoneId': 'America/New_York'
            },
            'targeting': {
                'geoTargeting': {
                    'targetedLocations': [
                        {'id': 2840, 'type': 'COUNTRY', 'displayName': 'United States'}
                    ]
                },
                'customTargeting': {
                    'logicalOperator': 'OR',
                    'children': []
                },
                'inventoryTargeting': {
                    'targetedAdUnits': [
                        {'adUnitId': '12345', 'includeDescendants': True}
                    ]
                }
            }
        }
    
    @pytest.fixture
    def mock_order_response(self):
        """Mock GAM order response data."""
        return {
            'id': 12345,
            'name': 'Test Order',
            'advertiserId': 67890,
            'status': 'APPROVED',
            'traffickerId': 11111
        }
    
    @pytest.fixture
    def mock_creative_response(self):
        """Mock GAM creative response data."""
        return [
            {
                'id': 138524791074,
                'name': 'Test Creative',
                'size': {'width': 300, 'height': 250},
                'Creative.Type': 'ImageCreative',
                'previewUrl': 'https://example.com/preview/123'
            }
        ]
    
    @patch('admin_ui.get_ad_manager_client_for_tenant')
    @patch('admin_ui.get_db_connection')
    def test_get_gam_line_item_success(self, mock_db, mock_gam_client, 
                                       mock_line_item_response, 
                                       mock_order_response,
                                       mock_creative_response):
        """Test successful retrieval of GAM line item data."""
        from admin_ui import app
        
        # Setup mocks
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {'tenant_id': 'test_tenant'}
        mock_conn.execute.return_value = mock_cursor
        mock_db.return_value = mock_conn
        
        # Mock GAM client responses
        mock_client = Mock()
        mock_line_item_service = Mock()
        mock_order_service = Mock()
        mock_creative_service = Mock()
        mock_lica_service = Mock()
        
        # Setup service responses
        mock_line_item_response_obj = Mock()
        mock_line_item_response_obj.results = [Mock(**mock_line_item_response)]
        mock_line_item_service.getLineItemsByStatement.return_value = mock_line_item_response_obj
        
        mock_order_response_obj = Mock()
        mock_order_response_obj.results = [Mock(**mock_order_response)]
        mock_order_service.getOrdersByStatement.return_value = mock_order_response_obj
        
        mock_creative_response_obj = Mock()
        mock_creative_response_obj.results = [Mock(**c) for c in mock_creative_response]
        mock_creative_service.getCreativesByStatement.return_value = mock_creative_response_obj
        
        mock_lica_response_obj = Mock()
        mock_lica_response_obj.results = []
        mock_lica_service.getLineItemCreativeAssociationsByStatement.return_value = mock_lica_response_obj
        
        mock_client.GetService.side_effect = lambda s: {
            'LineItemService': mock_line_item_service,
            'OrderService': mock_order_service,
            'CreativeService': mock_creative_service,
            'LineItemCreativeAssociationService': mock_lica_service
        }[s]
        
        mock_gam_client.return_value = mock_client
        
        # Test the endpoint
        with app.test_client() as client:
            # Mock authentication
            with client.session_transaction() as sess:
                sess['user_email'] = 'test@example.com'
                sess['is_super_admin'] = True
            
            response = client.get('/api/tenant/test_tenant/gam/line-item/7046143587')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Verify response structure
            assert 'line_item' in data
            assert 'order' in data
            assert 'creatives' in data
            assert 'creative_associations' in data
            assert 'media_product_json' in data
    
    def test_line_item_id_validation(self):
        """Test that line item ID validation works correctly."""
        from admin_ui import app
        
        with app.test_client() as client:
            # Mock authentication
            with client.session_transaction() as sess:
                sess['user_email'] = 'test@example.com'
                sess['is_super_admin'] = True
            
            # Test invalid line item IDs
            invalid_ids = ['abc', '-123', '0', '', 'null']
            
            for invalid_id in invalid_ids:
                response = client.get(f'/api/tenant/test_tenant/gam/line-item/{invalid_id}')
                assert response.status_code == 400
                data = json.loads(response.data)
                assert 'error' in data
    
    def test_convert_line_item_to_product_json(self):
        """Test conversion of GAM line item to internal product JSON format."""
        from admin_ui import convert_line_item_to_product_json
        
        line_item = {
            'id': 7046143587,
            'name': 'Test Line Item',
            'lineItemType': 'STANDARD',
            'costType': 'CPM',
            'costPerUnit': {
                'microAmount': 4000000
            },
            'unitsBought': 1000000,
            'targeting': {
                'geoTargeting': {
                    'targetedLocations': [
                        {'id': 2840, 'type': 'COUNTRY', 'displayName': 'United States'}
                    ]
                },
                'inventoryTargeting': {
                    'targetedAdUnits': [
                        {'adUnitId': '12345', 'includeDescendants': True}
                    ]
                }
            },
            'creativePlaceholders': [
                {
                    'size': {'width': 300, 'height': 250},
                    'expectedCreativeCount': 1
                }
            ]
        }
        
        creatives = [
            {
                'id': 138524791074,
                'name': 'Test Creative',
                'size': {'width': 300, 'height': 250},
                'Creative.Type': 'ImageCreative'
            }
        ]
        
        result = convert_line_item_to_product_json(line_item, creatives)
        
        # Verify basic fields
        assert result['product_id'] == 'line_item_7046143587'
        assert result['name'] == 'Test Line Item'
        assert result['delivery_type'] == 'guaranteed'
        assert result['is_fixed_price'] is True
        assert result['cpm'] == 4.0
        
        # Verify targeting
        assert 'geo_country_any_of' in result['targeting_overlay']
        assert 'US' in result['targeting_overlay']['geo_country_any_of']
        
        # Verify formats
        assert len(result['formats']) == 1
        assert result['formats'][0]['id'] == 'display_300x250'
        
        # Verify implementation config
        assert 'gam' in result['implementation_config']
        assert result['implementation_config']['gam']['line_item_id'] == 7046143587
    
    def test_xss_protection_in_display(self):
        """Test that XSS vulnerabilities are prevented in display functions."""
        # This would be better as a JavaScript test, but we can verify
        # that the escapeHtml function is being used in the template
        with open('templates/gam_line_item_viewer.html', 'r') as f:
            template_content = f.read()
        
        # Check that escapeHtml is defined
        assert 'function escapeHtml' in template_content
        
        # Check that it's being used in display functions
        assert 'escapeHtml(lineItem.name)' in template_content
        assert 'escapeHtml(order.name)' in template_content
        assert 'escapeHtml(creative.name)' in template_content
        
        # Check dangerous patterns are not present
        assert '${lineItem.name}' not in template_content.replace('escapeHtml(lineItem.name)', '')
        assert '${order.name}' not in template_content.replace('escapeHtml(order.name)', '')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])