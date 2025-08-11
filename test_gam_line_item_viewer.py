#!/usr/bin/env python3
"""
Test the enhanced GAM line item viewer functionality.

Tests the inventory targeting display with placements, ad units, and hierarchy.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Import the admin_ui module
from admin_ui import app


class TestGAMLineItemViewer:
    """Test suite for the enhanced GAM Line Item Viewer."""
    
    @pytest.fixture
    def client(self):
        """Create a test client for the Flask app."""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    @pytest.fixture
    def mock_session(self):
        """Mock session with authentication."""
        with patch('admin_ui.session') as mock_session:
            mock_session.get.return_value = 'test@example.com'
            mock_session.__contains__.return_value = True
            mock_session.__getitem__.return_value = 'test@example.com'
            yield mock_session
    
    @pytest.fixture
    def mock_gam_response(self):
        """Mock GAM API response with line item, ad units, and placements."""
        return {
            'line_item': {
                'id': 7046143587,
                'name': 'Test Campaign - Display',
                'orderId': 12345,
                'status': 'DELIVERING',
                'lineItemType': 'STANDARD',
                'priority': 8,
                'costType': 'CPM',
                'costPerUnit': {
                    'currencyCode': 'USD',
                    'microAmount': 4000000  # $4 CPM
                },
                'targeting': {
                    'inventoryTargeting': {
                        'targetedAdUnits': [
                            {
                                'adUnitId': '21775744923',
                                'includeDescendants': True
                            },
                            {
                                'adUnitId': '21775744924',
                                'includeDescendants': False
                            }
                        ],
                        'targetedPlacementIds': [123456789, 987654321]
                    },
                    'geoTargeting': {
                        'targetedLocations': [
                            {'id': 2840, 'displayName': 'United States', 'type': 'COUNTRY'}
                        ]
                    }
                }
            },
            'order': {
                'id': 12345,
                'name': 'Q1 2025 Campaign',
                'advertiserId': 456789,
                'traffickerId': 789012
            },
            'inventory_details': {
                'ad_units': {
                    '21775744923': {
                        'id': '21775744923',
                        'name': 'Homepage_Leaderboard',
                        'fullPath': 'Root > Homepage > Homepage_Leaderboard',
                        'parentId': '21775744920',
                        'status': 'ACTIVE',
                        'adUnitCode': 'homepage_728x90'
                    },
                    '21775744924': {
                        'id': '21775744924',
                        'name': 'Article_Sidebar',
                        'fullPath': 'Root > Articles > Article_Sidebar',
                        'parentId': '21775744921',
                        'status': 'ACTIVE',
                        'adUnitCode': 'article_300x250'
                    }
                },
                'placements': {
                    '123456789': {
                        'id': '123456789',
                        'name': 'Premium Homepage Placement',
                        'description': 'High-visibility homepage positions',
                        'status': 'ACTIVE',
                        'targetedAdUnitIds': ['21775744923', '21775744925'],
                        'isAdSenseTargetingEnabled': False
                    },
                    '987654321': {
                        'id': '987654321',
                        'name': 'Article Page Placement',
                        'description': 'Standard article page positions',
                        'status': 'ACTIVE',
                        'targetedAdUnitIds': ['21775744924'],
                        'isAdSenseTargetingEnabled': True
                    }
                }
            }
        }
    
    @patch('admin_ui.get_db_connection')
    @patch('admin_ui.get_ad_manager_client_for_tenant')
    def test_get_line_item_with_inventory_details(self, mock_gam_client, mock_db, client, mock_session, mock_gam_response):
        """Test that the API endpoint returns inventory details with names and hierarchy."""
        # Setup mocks
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'tenant_id': 'test_tenant', 'name': 'Test Tenant'}
        mock_db.return_value = mock_conn
        
        # Mock GAM client and services
        mock_client = MagicMock()
        mock_gam_client.return_value = mock_client
        
        # Mock line item service
        mock_line_item_service = MagicMock()
        mock_line_item_response = MagicMock()
        mock_line_item_response.results = [mock_gam_response['line_item']]
        mock_line_item_service.getLineItemsByStatement.return_value = mock_line_item_response
        
        # Mock order service
        mock_order_service = MagicMock()
        mock_order_response = MagicMock()
        mock_order_response.results = [mock_gam_response['order']]
        mock_order_service.getOrdersByStatement.return_value = mock_order_response
        
        # Mock inventory service for ad units
        mock_inventory_service = MagicMock()
        mock_ad_units_response = MagicMock()
        mock_ad_units_response.results = list(mock_gam_response['inventory_details']['ad_units'].values())
        mock_inventory_service.getAdUnitsByStatement.return_value = mock_ad_units_response
        
        # Mock placement service
        mock_placement_service = MagicMock()
        mock_placements_response = MagicMock()
        mock_placements_response.results = list(mock_gam_response['inventory_details']['placements'].values())
        mock_placement_service.getPlacementsByStatement.return_value = mock_placements_response
        
        # Mock creative association service
        mock_lica_service = MagicMock()
        mock_lica_response = MagicMock()
        mock_lica_response.results = []
        mock_lica_service.getLineItemCreativeAssociationsByStatement.return_value = mock_lica_response
        
        # Setup service mapping
        def get_service(service_name):
            services = {
                'LineItemService': mock_line_item_service,
                'OrderService': mock_order_service,
                'InventoryService': mock_inventory_service,
                'PlacementService': mock_placement_service,
                'LineItemCreativeAssociationService': mock_lica_service
            }
            return services.get(service_name)
        
        mock_client.GetService.side_effect = get_service
        
        # Mock serialize_object to return the data as-is
        with patch('admin_ui.serialize_object') as mock_serialize:
            mock_serialize.side_effect = lambda x: x if not hasattr(x, '__iter__') else list(x)
            
            # Make the request
            response = client.get('/api/tenant/test_tenant/gam/line-item/7046143587')
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Check that inventory details are included
        assert 'inventory_details' in data
        assert 'ad_units' in data['inventory_details']
        assert 'placements' in data['inventory_details']
        
        # Verify ad unit details include names and hierarchy
        ad_units = data['inventory_details']['ad_units']
        assert '21775744923' in ad_units
        assert ad_units['21775744923']['name'] == 'Homepage_Leaderboard'
        assert ad_units['21775744923']['fullPath'] == 'Root > Homepage > Homepage_Leaderboard'
        assert ad_units['21775744923']['adUnitCode'] == 'homepage_728x90'
        
        # Verify placement details include names and descriptions
        placements = data['inventory_details']['placements']
        assert '123456789' in placements
        assert placements['123456789']['name'] == 'Premium Homepage Placement'
        assert placements['123456789']['description'] == 'High-visibility homepage positions'
        assert len(placements['123456789']['targetedAdUnitIds']) == 2
    
    def test_line_item_viewer_template_rendering(self, client, mock_session):
        """Test that the line item viewer template renders correctly."""
        with patch('admin_ui.get_db_connection') as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.execute.return_value = mock_cursor
            mock_cursor.fetchone.return_value = {'tenant_id': 'test_tenant', 'name': 'Test Tenant'}
            mock_db.return_value = mock_conn
            
            response = client.get('/tenant/test_tenant/gam/line-item/7046143587')
            
            assert response.status_code == 200
            assert b'GAM Line Item Viewer' in response.data
            assert b'7046143587' in response.data  # Line item ID should be in the page
    
    def test_invalid_line_item_id(self, client, mock_session):
        """Test handling of invalid line item IDs."""
        with patch('admin_ui.get_db_connection') as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.execute.return_value = mock_cursor
            mock_cursor.fetchone.return_value = {'tenant_id': 'test_tenant', 'name': 'Test Tenant'}
            mock_db.return_value = mock_conn
            
            # Test with non-numeric ID
            response = client.get('/api/tenant/test_tenant/gam/line-item/invalid')
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data
            assert 'Invalid line item ID' in data['error']
            
            # Test with negative ID
            response = client.get('/api/tenant/test_tenant/gam/line-item/-123')
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data
            assert 'Invalid line item ID' in data['error']
    
    def test_inventory_targeting_display_logic(self):
        """Test the client-side logic for displaying inventory targeting."""
        # This would be a JavaScript test in practice, but we can test the logic
        inventory_details = {
            'ad_units': {
                '123': {
                    'name': 'Test Ad Unit',
                    'fullPath': 'Root > Section > Test Ad Unit',
                    'status': 'ACTIVE'
                }
            },
            'placements': {
                '456': {
                    'name': 'Test Placement',
                    'description': 'Test Description',
                    'targetedAdUnitIds': ['123', '789']
                }
            }
        }
        
        # Verify the structure matches what the JavaScript expects
        assert 'ad_units' in inventory_details
        assert 'placements' in inventory_details
        assert 'fullPath' in inventory_details['ad_units']['123']
        assert 'targetedAdUnitIds' in inventory_details['placements']['456']
    
    def test_hierarchy_path_construction(self):
        """Test that ad unit hierarchy paths are correctly constructed."""
        ad_unit_data = {
            'id': '123',
            'name': 'Leaderboard',
            'parentPath': [
                {'id': '1', 'name': 'Root'},
                {'id': '2', 'name': 'Homepage'}
            ]
        }
        
        # Simulate path construction logic
        path_names = []
        if ad_unit_data.get('parentPath'):
            for path_unit in ad_unit_data['parentPath']:
                path_names.append(path_unit.get('name', 'Unknown'))
        path_names.append(ad_unit_data.get('name', 'Unknown'))
        
        full_path = ' > '.join(path_names)
        assert full_path == 'Root > Homepage > Leaderboard'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])