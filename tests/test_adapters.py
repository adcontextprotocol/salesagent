import pytest
from datetime import datetime, timedelta

from adapters.mock_ad_server import MockAdServer
from schemas import *

@pytest.fixture
def sample_packages():
    """A fixture to create a sample list of media packages for use in tests."""
    return [
        MediaPackage(
            package_id="pkg_1",
            name="Guaranteed Banner",
            delivery_type="guaranteed",
            cpm=15.0,
            impressions=333333,  # 5000 budget / 15 CPM * 1000
            format_ids=["display_300x250", "display_728x90"]
        )
    ]

def test_mock_ad_server_create_media_buy(sample_packages):
    """
    Tests that the MockAdServer correctly creates a media buy
    when a create_media_buy request is received.
    """
    # Arrange
    principal = Principal(
        principal_id="test_principal",
        name="Test Principal",
        platform_mappings={"mock": {"advertiser_id": "test_advertiser"}}
    )
    adapter = MockAdServer({}, principal)
    start_time = datetime.now()
    end_time = start_time + timedelta(days=30)
    
    request = CreateMediaBuyRequest(
        selected_packages=[SelectedPackage(package_id="pkg_1")],
        billing_entity="Test Buyer Inc.",
        po_number="PO-12345"
    )
    
    # Act
    response = adapter.create_media_buy(
        request=request, 
        packages=sample_packages, 
        start_time=start_time, 
        end_time=end_time
    )

    # Assert
    assert response.media_buy_id == "buy_PO-12345"
    assert response.status == "pending_creative"
    
    # Check the internal state of the mock server
    internal_buy = adapter._media_buys.get("buy_PO-12345")
    assert internal_buy is not None
    assert internal_buy["total_budget"] == 5000
    assert len(internal_buy["packages"]) == 1
    assert internal_buy["packages"][0]["package_id"] == "pkg_1"