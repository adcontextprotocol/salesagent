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
    
    @patch('zeep.helpers.serialize_object')
    @patch('googleads.ad_manager')
    @patch('gam_helper.get_ad_manager_client_for_tenant')
    @patch('admin_ui.get_db_connection')
    def test_get_gam_line_item_success(self, mock_db, mock_gam_client, mock_ad_manager, mock_serialize, 
                                       mock_line_item_response, 
                                       mock_order_response,
                                       mock_creative_response):
        """Test successful retrieval of GAM line item data."""
        from admin_ui import app
        
        # Setup mocks
        mock_conn = Mock()
        
        # Create two cursors for the two queries
        # First query: SELECT * FROM tenants WHERE tenant_id = ?
        mock_cursor1 = Mock()
        mock_cursor1.fetchone.return_value = (
            'test_tenant',  # tenant_id
            'Test Tenant',  # name
            'test',  # subdomain
            json.dumps({  # config
                'adapters': {
                    'google_ad_manager': {
                        'enabled': True,
                        'network_code': '123456'
                    }
                }
            }),
            'standard',  # billing_plan
            True,  # is_active
            json.dumps([]),  # authorized_emails
            json.dumps([])  # authorized_domains
        )
        
        # Second query: get_tenant_config_from_db columns
        mock_cursor2 = Mock()
        mock_cursor2.fetchone.return_value = (
            'google_ad_manager',  # ad_server
            10000,  # max_daily_budget
            True,  # enable_aee_signals
            json.dumps([]),  # authorized_emails
            json.dumps([]),  # authorized_domains
            None,  # slack_webhook_url
            None,  # slack_audit_webhook_url
            None,  # hitl_webhook_url
            'test_token',  # admin_token
            json.dumps(['display_300x250']),  # auto_approve_formats
            False,  # human_review_required
            json.dumps({'enabled': False})  # policy_settings
        )
        
        # Third query: adapter_config table
        mock_cursor3 = Mock()
        mock_cursor3.fetchone.return_value = (
            'test_tenant',  # tenant_id
            'google_ad_manager',  # adapter_type
            '123456',  # network_code
            None,  # refresh_token
            None  # company_id
        )
        
        # Setup execute to return different cursors for different queries
        mock_conn.execute.side_effect = [mock_cursor1, mock_cursor2, mock_cursor3]
        mock_conn.close = Mock()  # Mock the close method
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
        
        # Mock ad_manager.StatementBuilder
        mock_statement = Mock()
        mock_statement.Where.return_value = mock_statement
        mock_statement.WithBindVariable.return_value = mock_statement
        mock_statement.Limit.return_value = mock_statement
        mock_statement.ToStatement.return_value = {}
        mock_ad_manager.StatementBuilder.return_value = mock_statement
        
        # Mock serialize_object to return the appropriate test data
        def serialize_mock(obj):
            # Check what's being serialized and return the appropriate test data
            # This will be called for line_item, order, and creatives
            if hasattr(obj, 'id'):
                id_value = getattr(obj, 'id', None)
                if id_value == 7046143587:
                    return mock_line_item_response
                elif id_value == 12345:
                    return mock_order_response
                elif id_value == 138524791074:
                    return mock_creative_response[0]
            # For lists of objects
            if isinstance(obj, list) and len(obj) > 0:
                return mock_creative_response
            # Default behavior
            return mock_line_item_response
        
        mock_serialize.side_effect = serialize_mock
        
        # Test the endpoint
        with app.test_client() as client:
            # Mock authentication properly
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['role'] = 'super_admin'
                sess['email'] = 'test@example.com'
                sess['tenant_id'] = 'test_tenant'
            
            response = client.get('/api/tenant/test_tenant/gam/line-item/7046143587')
            
            # Debug the response if it fails
            if response.status_code != 200:
                print(f"Response status: {response.status_code}")
                print(f"Response data: {response.data}")
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Verify response structure
            assert 'line_item' in data
            assert 'order' in data
            assert 'creatives' in data
            assert 'creative_associations' in data
            assert 'media_product_json' in data
    
    @patch('admin_ui.get_db_connection')
    def test_line_item_id_validation(self, mock_db):
        """Test that line item ID validation works correctly."""
        from admin_ui import app
        
        # Setup database mock
        mock_conn = Mock()
        
        # Since we're testing multiple invalid IDs, we need to handle multiple calls
        # Each invalid ID will trigger two queries
        def create_cursor_tenant():
            cursor = Mock()
            cursor.fetchone.return_value = (
                'test_tenant',  # tenant_id
                'Test Tenant',  # name
                'test',  # subdomain
                json.dumps({  # config
                    'adapters': {
                        'google_ad_manager': {
                            'enabled': True,
                            'network_code': '123456'
                        }
                    }
                }),
                'standard',  # billing_plan
                True,  # is_active
                json.dumps([]),  # authorized_emails
                json.dumps([])  # authorized_domains
            )
            return cursor
        
        def create_cursor_config():
            cursor = Mock()
            cursor.fetchone.return_value = (
                'google_ad_manager',  # ad_server
                10000,  # max_daily_budget
                True,  # enable_aee_signals
                json.dumps([]),  # authorized_emails
                json.dumps([]),  # authorized_domains
                None,  # slack_webhook_url
                None,  # slack_audit_webhook_url
                None,  # hitl_webhook_url
                'test_token',  # admin_token
                json.dumps(['display_300x250']),  # auto_approve_formats
                False,  # human_review_required
                json.dumps({'enabled': False})  # policy_settings
            )
            return cursor
        
        # Create cursors for each invalid ID test (2 queries per test)
        cursors = []
        invalid_ids_400 = ['abc', '-123', '0', 'null']
        for _ in invalid_ids_400:
            cursors.append(create_cursor_tenant())
            cursors.append(create_cursor_config())
        
        mock_conn.execute.side_effect = cursors
        mock_conn.close = Mock()
        mock_db.return_value = mock_conn
        
        with app.test_client() as client:
            # Mock authentication properly
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['role'] = 'super_admin'
                sess['email'] = 'test@example.com'
                sess['tenant_id'] = 'test_tenant'
            
            # Test invalid line item IDs
            # Note: empty string won't match the route, so it returns 404
            invalid_ids_400 = ['abc', '-123', '0', 'null']
            
            for invalid_id in invalid_ids_400:
                response = client.get(f'/api/tenant/test_tenant/gam/line-item/{invalid_id}')
                assert response.status_code == 400, f"Expected 400 for ID '{invalid_id}', got {response.status_code}"
                data = json.loads(response.data)
                assert 'error' in data
            
            # Test empty string separately - should give 404 as route won't match
            response = client.get(f'/api/tenant/test_tenant/gam/line-item/')
            assert response.status_code == 404
    
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
        assert result['product_id'] == 'gam_line_item_7046143587'
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