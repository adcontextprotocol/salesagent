#!/usr/bin/env python3
"""
Test script for GAM country and ad unit reporting functionality
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any

from adapters.gam_reporting_service import GAMReportingService


def create_mock_gam_client():
    """Create a mock GAM client for testing"""
    class MockGAMClient:
        def GetService(self, service_name):
            if service_name == 'ReportService':
                return MockReportService()
            elif service_name == 'NetworkService':
                return MockNetworkService()
            return None
        
        def GetDataDownloader(self):
            return MockDataDownloader()
    
    class MockNetworkService:
        def getCurrentNetwork(self):
            class Network:
                timeZone = "America/New_York"
            return Network()
    
    class MockReportService:
        def runReportJob(self, job):
            return {'id': 'test_report_123'}
        
        def getReportJobStatus(self, job_id):
            return 'COMPLETED'
    
    class MockDataDownloader:
        def DownloadReportToFile(self, job_id, format_type, file_obj):
            import gzip
            import csv
            
            # Generate mock CSV data with country and ad unit info
            rows = []
            countries = ['United States', 'Canada', 'United Kingdom', 'Germany', 'France']
            ad_units = ['Homepage_Top', 'Article_Sidebar', 'Video_Pre-Roll', 'Mobile_Banner']
            
            for country in countries:
                for ad_unit in ad_units:
                    rows.append({
                        'Dimension.DATE': '2025-01-13',
                        'Dimension.ADVERTISER_ID': '12345',
                        'Dimension.ADVERTISER_NAME': 'Test Advertiser',
                        'Dimension.ORDER_ID': '67890',
                        'Dimension.ORDER_NAME': 'Test Campaign',
                        'Dimension.LINE_ITEM_ID': '11111',
                        'Dimension.LINE_ITEM_NAME': 'Test Line Item',
                        'Dimension.COUNTRY_NAME': country,
                        'Dimension.AD_UNIT_ID': f'unit_{ad_unit}',
                        'Dimension.AD_UNIT_NAME': ad_unit,
                        'Column.AD_SERVER_IMPRESSIONS': str(10000 + hash(country + ad_unit) % 5000),
                        'Column.AD_SERVER_CLICKS': str(100 + hash(country + ad_unit) % 50),
                        'Column.AD_SERVER_CPM_AND_CPC_REVENUE': str(5000000 + hash(country + ad_unit) % 2000000)
                    })
            
            # Write to gzipped CSV
            with gzip.open(file_obj.name, 'wt', newline='') as gz_file:
                writer = csv.DictWriter(gz_file, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
    
    return MockGAMClient()


def test_country_breakdown():
    """Test the country breakdown functionality"""
    print("Testing Country Breakdown...")
    print("-" * 50)
    
    # Create mock client and service
    mock_client = create_mock_gam_client()
    service = GAMReportingService(mock_client, "America/New_York")
    
    # Test get_country_breakdown
    result = service.get_country_breakdown(
        date_range="this_month",
        advertiser_id="12345"
    )
    
    print(f"Total countries: {result['total_countries']}")
    print(f"Date range: {result['date_range']}")
    print(f"Timezone: {result['timezone']}")
    print(f"\nTop 5 Countries by Spend:")
    print("-" * 50)
    
    for i, country in enumerate(result['countries'][:5], 1):
        print(f"{i}. {country['country']}")
        print(f"   Impressions: {country['impressions']:,}")
        print(f"   Spend: ${country['spend']:.2f}")
        print(f"   CPM: ${country['avg_cpm']:.2f}")
        print(f"   CTR: {country['ctr']:.2f}%")
        print()
    
    return result


def test_ad_unit_breakdown():
    """Test the ad unit breakdown functionality"""
    print("Testing Ad Unit Breakdown...")
    print("-" * 50)
    
    # Create mock client and service
    mock_client = create_mock_gam_client()
    service = GAMReportingService(mock_client, "America/New_York")
    
    # Test get_ad_unit_breakdown
    result = service.get_ad_unit_breakdown(
        date_range="this_month",
        advertiser_id="12345",
        country="United States"  # Filter by US
    )
    
    print(f"Total ad units: {result['total_ad_units']}")
    print(f"Filtered by country: {result['filtered_by_country']}")
    print(f"\nTop Ad Units by Spend:")
    print("-" * 50)
    
    for i, ad_unit in enumerate(result['ad_units'][:5], 1):
        print(f"{i}. {ad_unit['ad_unit_name']} (ID: {ad_unit['ad_unit_id']})")
        print(f"   Impressions: {ad_unit['impressions']:,}")
        print(f"   Spend: ${ad_unit['spend']:.2f}")
        print(f"   CPM: ${ad_unit['avg_cpm']:.2f}")
        print(f"   Countries served: {len(ad_unit['countries'])}")
        
        # Show country breakdown for this ad unit
        if ad_unit['countries']:
            print(f"   Country breakdown:")
            for country, data in list(ad_unit['countries'].items())[:3]:
                print(f"     - {country}: ${data['cpm']:.2f} CPM")
        print()
    
    return result


def test_combined_reporting():
    """Test getting both country and ad unit data with the include flags"""
    print("Testing Combined Reporting with Country & Ad Unit...")
    print("-" * 50)
    
    # Create mock client and service
    mock_client = create_mock_gam_client()
    service = GAMReportingService(mock_client, "America/New_York")
    
    # Get reporting data with both dimensions
    result = service.get_reporting_data(
        date_range="today",
        advertiser_id="12345",
        include_country=True,
        include_ad_unit=True
    )
    
    print(f"Dimensions included: {result.dimensions}")
    print(f"Total rows: {len(result.data)}")
    print(f"Data valid until: {result.data_valid_until}")
    print(f"\nSample data rows (first 3):")
    print("-" * 50)
    
    for i, row in enumerate(result.data[:3], 1):
        print(f"{i}. {row['timestamp']}")
        print(f"   Country: {row.get('country', 'N/A')}")
        print(f"   Ad Unit: {row.get('ad_unit_name', 'N/A')}")
        print(f"   Impressions: {row['impressions']:,}")
        print(f"   CPM: ${row['cpm']:.2f}")
        print()
    
    # Show summary metrics
    print("Summary Metrics:")
    print("-" * 50)
    for key, value in result.metrics.items():
        if isinstance(value, float):
            print(f"{key}: ${value:.2f}" if 'spend' in key or 'ecpm' in key else f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value:,}" if isinstance(value, int) else f"{key}: {value}")


def main():
    """Run all tests"""
    print("=" * 60)
    print("GAM Country & Ad Unit Reporting Tests")
    print("=" * 60)
    print()
    
    try:
        # Test country breakdown
        country_result = test_country_breakdown()
        assert country_result['total_countries'] > 0, "Should have country data"
        print("✅ Country breakdown test passed")
        print()
        
        # Test ad unit breakdown
        ad_unit_result = test_ad_unit_breakdown()
        assert ad_unit_result['total_ad_units'] > 0, "Should have ad unit data"
        print("✅ Ad unit breakdown test passed")
        print()
        
        # Test combined reporting
        test_combined_reporting()
        print("✅ Combined reporting test passed")
        print()
        
        print("=" * 60)
        print("✅ All tests passed successfully!")
        print("=" * 60)
        
        # Show usage example
        print("\nUsage Example for API:")
        print("-" * 50)
        print("# Get country breakdown:")
        print("curl 'http://localhost:8001/api/tenant/{tenant_id}/gam/reporting/countries?date_range=this_month'")
        print()
        print("# Get ad unit breakdown:")
        print("curl 'http://localhost:8001/api/tenant/{tenant_id}/gam/reporting/ad-units?date_range=this_month&country=United%20States'")
        print()
        print("# Frontend will automatically call these endpoints when viewing the Country Heatmap and Ad Unit Analysis tabs")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())