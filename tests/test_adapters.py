import pytest
from datetime import datetime, timedelta

from adapters.mock_ad_server import MockAdServer
from schemas import Proposal, MediaPackage, ProvidedSignalsInPackage

# A fixture to create a sample proposal for use in tests
@pytest.fixture
def sample_proposal():
    start_time = datetime.now().astimezone()
    end_time = start_time + timedelta(days=30)
    return Proposal(
        proposal_id="test_proposal_01",
        total_budget=1000,
        currency="USD",
        start_time=start_time,
        end_time=end_time,
        creative_formats=[],
        media_packages=[
            MediaPackage(
                package_id="pkg_1",
                name="Test Package 1",
                description="A test package",
                delivery_restrictions="US",
                provided_signals=ProvidedSignalsInPackage(included_ids=["cat_lovers"]),
                cpm=10.0,
                budget=1000,
                budget_capacity=50000,
                creative_formats="Banner"
            )
        ]
    )

def test_mock_ad_server_accept_proposal(sample_proposal):
    """
    Tests that the MockAdServer correctly creates a media buy
    when a proposal is accepted.
    """
    # Arrange
    mock_config = {} # No config needed for the mock server
    adapter = MockAdServer(mock_config)
    
    # Act
    response = adapter.accept_proposal(
        proposal=sample_proposal,
        accepted_packages=["pkg_1"],
        billing_entity="Test Buyer Inc.",
        po_number="PO-12345",
        today=datetime.now().astimezone()
    )

    # Assert
    assert response.media_buy_id == "buy_po-12345"
    assert response.status == "pending_creative"
    
    # Check the internal state of the mock server
    internal_buy = adapter._media_buys.get("buy_po-12345")
    assert internal_buy is not None
    assert internal_buy["total_budget"] == 1000
    assert len(internal_buy["media_packages"]) == 1
    assert internal_buy["media_packages"][0]["package_id"] == "pkg_1"

def test_gam_adapter_accept_proposal(mocker, sample_proposal):
    """
    Tests that the GoogleAdManager adapter calls the correct services
    with the correct data when accepting a proposal.
    """
    # Arrange
    # Prevent the client from trying to initialize and read a dummy file
    mocker.patch('adapters.google_ad_manager.GoogleAdManager._init_client', return_value=None)

    # Mock the services that will be called
    mock_order_service = mocker.Mock()
    mock_line_item_service = mocker.Mock()

    # Create a mock for the client instance that the adapter will use
    mock_client = mocker.Mock()

    # Set up a side_effect to return the correct mock service from the client
    def get_service_side_effect(service_name):
        if service_name == 'OrderService':
            return mock_order_service
        elif service_name == 'LineItemService':
            return mock_line_item_service
        return mocker.Mock()
    mock_client.GetService.side_effect = get_service_side_effect

    # Mock the return values of the API calls
    mock_order_service.createOrders.return_value = [{'id': '12345678'}]
    mock_line_item_service.createLineItems.return_value = [{'id': '98765432'}]

    gam_config = {
        "network_code": "12345",
        "service_account_key_file": "dummy.json",
        "advertiser_id": "adv-id-1",
        "trafficker_id": "trafficker-id-1",
        "company_id": "comp-id-1"
    }

    # We need to import the class here to avoid issues with the mock
    from adapters.google_ad_manager import GoogleAdManager
    adapter = GoogleAdManager(gam_config)
    # Manually assign the mock client to the adapter instance
    adapter.client = mock_client

    # Act
    response = adapter.accept_proposal(
        proposal=sample_proposal,
        accepted_packages=["pkg_1"],
        billing_entity="Test Buyer Inc.",
        po_number="PO-12345",
        today=datetime.now().astimezone()
    )

    # Assert
    assert response.media_buy_id == "12345678"

    # Verify that the OrderService was called correctly
    mock_order_service.createOrders.assert_called_once()
    created_order_payload = mock_order_service.createOrders.call_args[0][0][0]
    assert created_order_payload['name'] == "ADCP Buy - PO-12345"
    assert created_order_payload['advertiserId'] == "adv-id-1"

    # Verify that the LineItemService was called correctly
    mock_line_item_service.createLineItems.assert_called_once()
    created_line_item_payload = mock_line_item_service.createLineItems.call_args[0][0][0]
    assert created_line_item_payload['orderId'] == '12345678'
    assert created_line_item_payload['name'] == "Test Package 1"
    assert created_line_item_payload['costType'] == "CPM"

def test_triton_adapter_accept_proposal(mocker, sample_proposal):
    """
    Tests that the TritonDigital adapter makes the correct HTTP requests
    when accepting a proposal.
    """
    # Arrange
    # Mock the requests library
    mock_post = mocker.patch('requests.post')
    
    # Mock the response from the API
    mock_response = mocker.Mock()
    mock_response.raise_for_status.return_value = None
    # Simulate the response for campaign creation and flight creation
    mock_response.json.side_effect = [{'id': 'triton-campaign-123'}, {'id': 'triton-flight-456'}]
    mock_post.return_value = mock_response

    triton_config = {
        "base_url": "https://fake-tap-api.tritondigital.com/v1",
        "auth_token": "fake-token"
    }
    
    from adapters.triton_digital import TritonDigital
    adapter = TritonDigital(triton_config)

    # Act
    response = adapter.accept_proposal(
        proposal=sample_proposal,
        accepted_packages=["pkg_1"],
        billing_entity="Test Buyer Inc.",
        po_number="PO-12345",
        today=datetime.now().astimezone()
    )

    # Assert
    assert response.media_buy_id == "triton-campaign-123"
    
    # Verify that the campaign was created correctly
    campaign_call = mock_post.call_args_list[0]
    assert campaign_call[0][0] == "https://fake-tap-api.tritondigital.com/v1/campaigns"
    assert campaign_call[1]['json']['name'] == "ADCP Buy - PO-12345"

    # Verify that the flight was created correctly
    flight_call = mock_post.call_args_list[1]
    assert flight_call[0][0] == "https://fake-tap-api.tritondigital.com/v1/flights"
    assert flight_call[1]['json']['campaignId'] == "triton-campaign-123"
    assert flight_call[1]['json']['name'] == "Test Package 1"
    assert flight_call[1]['json']['rateType'] == "CPM"
