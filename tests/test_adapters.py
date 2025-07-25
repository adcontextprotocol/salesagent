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
                creative_formats=["Banner"]
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

def test_gam_adapter_targeting(mocker, sample_proposal):
    """
    Tests that the GoogleAdManager adapter correctly builds the targeting
    payload based on the ad_server_targeting data.
    """
    # Arrange
    mocker.patch('adapters.google_ad_manager.GoogleAdManager._init_client', return_value=None)
    mock_order_service = mocker.Mock()
    mock_line_item_service = mocker.Mock()
    mock_client = mocker.Mock()
    def get_service_side_effect(service_name):
        if service_name == 'OrderService': return mock_order_service
        if service_name == 'LineItemService': return mock_line_item_service
        return mocker.Mock()
    mock_client.GetService.side_effect = get_service_side_effect
    mock_order_service.createOrders.return_value = [{'id': '12345678'}]
    mock_line_item_service.createLineItems.return_value = [{'id': '98765432'}]

    # Add rich ad_server_targeting data to the proposal
    sample_proposal.media_packages[0].provided_signals.ad_server_targeting = [
        {"gam": {"type": "audience_segment", "id": "12345"}},
        {"gam": {"type": "geography", "id": "2840"}}, # USA
        {"gam": {"type": "device_capability", "id": "5005"}} # Mobile
    ]

    gam_config = {
        "network_code": "12345", "service_account_key_file": "dummy.json",
        "advertiser_id": "adv-id-1", "trafficker_id": "trafficker-id-1", "company_id": "comp-id-1"
    }
    from adapters.google_ad_manager import GoogleAdManager
    adapter = GoogleAdManager(gam_config)
    adapter.client = mock_client

    # Act
    adapter.accept_proposal(
        proposal=sample_proposal, accepted_packages=["pkg_1"],
        billing_entity="Test Buyer", po_number="PO-54321", today=datetime.now().astimezone()
    )

    # Assert
    mock_line_item_service.createLineItems.assert_called_once()
    created_line_item_payload = mock_line_item_service.createLineItems.call_args[0][0][0]
    targeting = created_line_item_payload['targeting']
    
    assert targeting['audienceSegmentIds'] == ["12345"]
    assert targeting['geoTargeting']['targetedLocations'] == [{'id': '2840'}]
    assert targeting['deviceCapabilityTargeting']['targetedDeviceCapabilities'] == [{'id': '5005'}]

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

def test_triton_adapter_targeting(mocker, sample_proposal):
    """
    Tests that the TritonDigital adapter correctly builds the targeting
    payload based on the ad_server_targeting data.
    """
    # Arrange
    mock_post = mocker.patch('requests.post')
    mock_response = mocker.Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = [{'id': 'triton-campaign-123'}, {'id': 'triton-flight-456'}]
    mock_post.return_value = mock_response

    # Add rich ad_server_targeting data to the proposal
    sample_proposal.media_packages[0].provided_signals.ad_server_targeting = [
        {"triton": {"type": "station", "id": "STATION_ONE"}},
        {"triton": {"type": "geography", "country": "US"}},
        {"triton": {"type": "geography", "dma": "501"}}, # New York
        {"triton": {"type": "device", "os_family": "iOS"}},
        {"triton": {"type": "device", "device_type": "Mobile"}}
    ]

    triton_config = {
        "base_url": "https://fake-tap-api.tritondigital.com/v1",
        "auth_token": "fake-token"
    }
    from adapters.triton_digital import TritonDigital
    adapter = TritonDigital(triton_config)

    # Act
    adapter.accept_proposal(
        proposal=sample_proposal, accepted_packages=["pkg_1"],
        billing_entity="Test Buyer", po_number="PO-54321", today=datetime.now().astimezone()
    )

    # Assert
    assert mock_post.call_count == 2 # 1 for campaign, 1 for flight
    flight_call = mock_post.call_args_list[1]
    targeting = flight_call[1]['json']['targeting']

    assert targeting['stationIds'] == ["STATION_ONE"]
    assert targeting['countries'] == ["US"]
    assert targeting['dmas'] == ["501"]
    assert targeting['osFamilies'] == ["iOS"]
    assert targeting['deviceTypes'] == ["Mobile"]

def test_gam_adapter_add_creatives(mocker, sample_proposal):
    """
    Tests that the GoogleAdManager adapter correctly creates creatives
    and associates them with the correct line items.
    """
    # Arrange
    mocker.patch('adapters.google_ad_manager.GoogleAdManager._init_client', return_value=None)
    mock_creative_service = mocker.Mock()
    mock_lica_service = mocker.Mock()
    mock_line_item_service = mocker.Mock()
    mock_client = mocker.Mock()

    def get_service_side_effect(service_name):
        if service_name == 'CreativeService': return mock_creative_service
        if service_name == 'LineItemCreativeAssociationService': return mock_lica_service
        if service_name == 'LineItemService': return mock_line_item_service
        return mocker.Mock()
    mock_client.GetService.side_effect = get_service_side_effect

    # Simulate the line items that were created for the order
    mock_line_item_service.getLineItemsByStatement.return_value = {
        'results': [{'name': 'Test Package 1', 'id': 'li-123'}]
    }
    mock_creative_service.createCreatives.return_value = [{'id': 'creative-abc'}]

    assets_to_add = [
        {
            "creative_id": "c1", "format": "image", "name": "Test Image Ad",
            "media_url": "http://example.com/img.png", "click_url": "http://example.com",
            "width": 300, "height": 250, "package_assignments": ["Test Package 1"]
        }
    ]

    gam_config = {
        "network_code": "12345", "service_account_key_file": "dummy.json",
        "advertiser_id": "adv-id-1", "trafficker_id": "trafficker-id-1", "company_id": "comp-id-1"
    }
    from adapters.google_ad_manager import GoogleAdManager
    adapter = GoogleAdManager(gam_config)
    adapter.client = mock_client

    # Act
    response = adapter.add_creative_assets(media_buy_id="12345678", assets=assets_to_add, today=datetime.now().astimezone())

    # Assert
    assert len(response) == 1
    assert response[0].status == "approved"

    # Verify creative was created correctly
    mock_creative_service.createCreatives.assert_called_once()
    created_creative_payload = mock_creative_service.createCreatives.call_args[0][0][0]
    assert created_creative_payload['xsi_type'] == 'ImageCreative'
    assert created_creative_payload['name'] == 'Test Image Ad'
    assert created_creative_payload['primaryImageAsset']['assetUrl'] == 'http://example.com/img.png'

    # Verify creative was associated with the correct line item
    mock_lica_service.createLineItemCreativeAssociations.assert_called_once()
    created_lica_payload = mock_lica_service.createLineItemCreativeAssociations.call_args[0][0][0]
    assert created_lica_payload['lineItemId'] == 'li-123'
    assert created_lica_payload['creativeId'] == 'creative-abc'

def test_triton_adapter_add_creatives(mocker, sample_proposal):
    """
    Tests that the TritonDigital adapter correctly creates creatives
    and associates them with the correct flights.
    """
    # Arrange
    mock_requests_get = mocker.patch('requests.get')
    mock_requests_post = mocker.patch('requests.post')
    mock_requests_put = mocker.patch('requests.put')

    # Simulate the flights that were created for the campaign
    mock_flights_response = mocker.Mock()
    mock_flights_response.raise_for_status.return_value = None
    mock_flights_response.json.return_value = [{'name': 'Test Package 1', 'id': 'flight-456'}]
    mock_requests_get.return_value = mock_flights_response

    # Simulate creative creation
    mock_creative_response = mocker.Mock()
    mock_creative_response.raise_for_status.return_value = None
    mock_creative_response.json.return_value = {'id': 'creative-xyz'}
    mock_requests_post.return_value = mock_creative_response
    
    # Simulate flight update for association
    mock_assoc_response = mocker.Mock()
    mock_assoc_response.raise_for_status.return_value = None
    mock_requests_put.return_value = mock_assoc_response

    assets_to_add = [
        {
            "creative_id": "c2", "format": "audio", "name": "Test Audio Ad",
            "media_url": "http://example.com/ad.mp3", "click_url": "http://example.com",
            "package_assignments": ["Test Package 1"]
        }
    ]

    triton_config = {
        "base_url": "https://fake-tap-api.tritondigital.com/v1",
        "auth_token": "fake-token"
    }
    from adapters.triton_digital import TritonDigital
    adapter = TritonDigital(triton_config)

    # Act
    response = adapter.add_creative_assets(media_buy_id="triton-campaign-123", assets=assets_to_add, today=datetime.now().astimezone())

    # Assert
    assert len(response) == 1
    assert response[0].status == "approved"

    # Verify creative was created correctly
    mock_requests_post.assert_called_once()
    create_creative_call = mock_requests_post.call_args_list[0]
    assert create_creative_call[0][0] == "https://fake-tap-api.tritondigital.com/v1/creatives"
    assert create_creative_call[1]['json']['name'] == 'Test Audio Ad'
    assert create_creative_call[1]['json']['url'] == 'http://example.com/ad.mp3'

    # Verify creative was associated with the correct flight
    mock_requests_put.assert_called_once()
    update_flight_call = mock_requests_put.call_args_list[0]
    assert update_flight_call[0][0] == "https://fake-tap-api.tritondigital.com/v1/flights/flight-456"
    assert update_flight_call[1]['json']['creativeIds'] == ['creative-xyz']

def test_kevel_adapter_accept_proposal(mocker, sample_proposal):
    """
    Tests that the Kevel adapter correctly creates a campaign and flights.
    """
    # Arrange
    mock_post = mocker.patch('requests.post')
    mock_response = mocker.Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {'Id': 'kevel-campaign-789'}
    mock_post.return_value = mock_response

    kevel_config = {"network_id": "123", "api_key": "fake-key"}
    from adapters.kevel import Kevel
    adapter = Kevel(kevel_config)

    # Act
    response = adapter.accept_proposal(
        proposal=sample_proposal, accepted_packages=["pkg_1"],
        billing_entity="Test Buyer", po_number="PO-kevel-1", today=datetime.now().astimezone()
    )

    # Assert
    assert response.media_buy_id == "kevel-campaign-789"
    mock_post.assert_called_once()
    campaign_payload = mock_post.call_args[1]['json']['campaign']
    assert campaign_payload['Name'] == "ADCP Buy - PO-kevel-1"
    assert len(campaign_payload['Flights']) == 1
    assert campaign_payload['Flights'][0]['Name'] == "Test Package 1"

def test_kevel_adapter_add_creatives(mocker, sample_proposal):
    """
    Tests that the Kevel adapter correctly creates a creative from a custom template
    and associates it with the correct flight.
    """
    # Arrange
    mock_requests_get = mocker.patch('requests.get')
    mock_requests_post = mocker.patch('requests.post')

    # Simulate getting the flights for the campaign
    mock_flights_response = mocker.Mock()
    mock_flights_response.raise_for_status.return_value = None
    mock_flights_response.json.return_value = {'flights': [{'name': 'Test Package 1', 'id': 'flight-789'}]}
    mock_requests_get.return_value = mock_flights_response

    # Simulate creative and ad creation
    mock_creative_response = mocker.Mock()
    mock_creative_response.raise_for_status.return_value = None
    mock_creative_response.json.side_effect = [{'Id': 'creative-uvw'}, {'Id': 'ad-xyz'}]
    mock_requests_post.return_value = mock_creative_response

    assets_to_add = [
        {
            "creative_id": "c3", "format": "custom", "name": "Test Custom Ad",
            "template_id": 12345, "template_data": {"title": "My Ad", "description": "Click here!"},
            "package_assignments": ["Test Package 1"]
        }
    ]

    kevel_config = {"network_id": "123", "api_key": "fake-key"}
    from adapters.kevel import Kevel
    adapter = Kevel(kevel_config)

    # Act
    response = adapter.add_creative_assets(media_buy_id="kevel-campaign-789", assets=assets_to_add, today=datetime.now().astimezone())

    # Assert
    assert len(response) == 1
    assert response[0].status == "approved"

    # Verify creative was created correctly
    create_creative_call = mock_requests_post.call_args_list[0]
    assert create_creative_call[0][0].endswith("/creatives")
    assert create_creative_call[1]['json']['creative']['TemplateId'] == 12345
    assert create_creative_call[1]['json']['creative']['Data']['title'] == "My Ad"

    # Verify ad was created to associate creative with flight
    create_ad_call = mock_requests_post.call_args_list[1]
    assert create_ad_call[0][0].endswith("/ads")
    assert create_ad_call[1]['json']['ad']['CreativeId'] == 'creative-uvw'
    assert create_ad_call[1]['json']['ad']['FlightId'] == 'flight-789'
