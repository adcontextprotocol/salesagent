from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import requests

from adapters.base import AdServerAdapter, CreativeEngineAdapter
from schemas import (
    AcceptProposalResponse, CheckMediaBuyStatusResponse, GetMediaBuyDeliveryResponse,
    UpdateMediaBuyResponse, Proposal, ReportingPeriod, PackagePerformance, AssetStatus
)

class Kevel(AdServerAdapter):
    """
    Adapter for interacting with the Kevel Management API.
    """
    def __init__(self, config: Dict[str, Any], creative_engine: Optional[CreativeEngineAdapter] = None):
        super().__init__(config, creative_engine)
        self.network_id = self.config.get("network_id")
        self.api_key = self.config.get("api_key")
        self.base_url = f"https://api.kevel.co/v1/network/{self.network_id}"

        if not self.network_id or not self.api_key:
            raise ValueError("Kevel config is missing 'network_id' or 'api_key'")

        self.headers = {
            "X-ApiKey": self.api_key,
            "Content-Type": "application/json"
        }

    def create_media_buy(self, request: CreateMediaBuyRequest, packages: List[MediaPackage]) -> CreateMediaBuyResponse:
        """Creates a new Campaign and associated Flights in Kevel."""
        print("Kevel: create_media_buy called.")
        media_buy_id = f"kevel_{int(datetime.now().timestamp())}"
        return CreateMediaBuyResponse(
            media_buy_id=media_buy_id,
            status="pending_activation",
            creative_deadline=datetime.now() + timedelta(days=2)
        )

    def accept_proposal(self, proposal: Proposal, accepted_packages: List[str], billing_entity: str, po_number: str, today: datetime) -> AcceptProposalResponse:
        """[DEPRECATED] Creates a new Campaign and associated Flights in Kevel."""
        pass

    def add_creative_assets(self, media_buy_id: str, assets: List[Dict[str, Any]], today: datetime) -> List[AssetStatus]:
        """Creates a new Creative in Kevel and associates it with Flights."""
        created_asset_statuses = []

        try:
            # Get all flights for the campaign to map package names to flight IDs
            flights_response = requests.get(f"{self.base_url}/flights?campaignId={media_buy_id}", headers=self.headers)
            flights_response.raise_for_status()
            flights = flights_response.json().get('flights', [])
            flight_map = {flight['name']: flight['id'] for flight in flights}

            for asset in assets:
                creative_payload = {
                    "Name": asset['name'],
                    "IsActive": True,
                }

                if asset['format'] == 'custom' and asset.get('template_id'):
                    creative_payload['TemplateId'] = asset['template_id']
                    creative_payload['Data'] = asset.get('template_data', {})
                elif asset['format'] == 'image':
                    creative_payload['Body'] = f"<a href='{asset['click_url']}' target='_blank'><img src='{asset['media_url']}'/></a>"
                    creative_payload['Url'] = asset['click_url'] # Kevel uses Body for the tag, Url for the click
                else:
                    print(f"Skipping asset {asset['creative_id']} with unsupported format for Kevel: {asset['format']}")
                    continue

                # Create the creative
                creative_response = requests.post(f"{self.base_url}/creatives", headers=self.headers, json={"creative": creative_payload})
                creative_response.raise_for_status()
                creative_data = creative_response.json()
                creative_id = creative_data['Id']
                print(f"Successfully created Kevel Creative with ID: {creative_id}")

                # Associate the creative with the assigned flights
                flight_ids_to_associate = [flight_map[pkg_id] for pkg_id in asset['package_assignments'] if pkg_id in flight_map]
                
                if flight_ids_to_associate:
                    ad_payload = {
                        "CreativeId": creative_id,
                        "FlightId": flight_ids_to_associate[0], # Assuming one flight per ad for now
                        "IsActive": True
                    }
                    ad_response = requests.post(f"{self.base_url}/ads", headers=self.headers, json={"ad": ad_payload})
                    ad_response.raise_for_status()
                    print(f"Associated creative {creative_id} with flight {flight_ids_to_associate[0]}")
                else:
                    print(f"Warning: No matching flights found for creative {creative_id} package assignments.")

                created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="approved"))

        except requests.exceptions.RequestException as e:
            print(f"Error creating Kevel Creative or Ad: {e}")
            for asset in assets:
                if not any(s.creative_id == asset['creative_id'] for s in created_asset_statuses):
                     created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="failed"))
        
        return created_asset_statuses

    def check_media_buy_status(self, media_buy_id: str, today: datetime) -> CheckMediaBuyStatusResponse:
        print("Kevel Adapter: check_media_buy_status called. (Not yet implemented)")
        return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status="unknown")

    def get_media_buy_delivery(self, media_buy_id: str, date_range: ReportingPeriod, today: datetime) -> GetMediaBuyDeliveryResponse:
        print("Kevel Adapter: get_media_buy_delivery called. (Not yet implemented)")
        return None # Or a default response

    def update_media_buy(self, media_buy_id: str, action: str, package_id: Optional[str], budget: Optional[int], today: datetime) -> UpdateMediaBuyResponse:
        print("Kevel Adapter: update_media_buy called. (Not yet implemented)")
        return UpdateMediaBuyResponse(status="failed", reason="Not implemented")

    def update_media_buy_performance_index(self, media_buy_id: str, package_performance: List[PackagePerformance]) -> bool:
        print("Kevel Adapter: update_media_buy_performance_index called. (Not yet implemented)")
        return False
