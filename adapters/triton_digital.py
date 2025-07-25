from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import requests # We'll need this to make HTTP requests to the API

from adapters.base import AdServerAdapter, CreativeEngineAdapter
from schemas import (
    AcceptProposalResponse, CheckMediaBuyStatusResponse, GetMediaBuyDeliveryResponse,
    UpdateMediaBuyResponse, Proposal, ReportingPeriod, PackagePerformance, AssetStatus
)

class TritonDigital(AdServerAdapter):
    """
    Adapter for interacting with the Triton Digital TAP API.
    """
    def __init__(self, config: Dict[str, Any], creative_engine: Optional[CreativeEngineAdapter] = None):
        super().__init__(config, creative_engine)
        self.base_url = self.config.get("base_url")
        self.auth_token = self.config.get("auth_token")

        if not self.base_url or not self.auth_token:
            raise ValueError("Triton Digital config is missing 'base_url' or 'auth_token'")

        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

    def accept_proposal(self, proposal: Proposal, accepted_packages: List[str], billing_entity: str, po_number: str, today: datetime) -> AcceptProposalResponse:
        """Creates a new Campaign and Flights in the Triton TAP API."""
        
        campaign_payload = {
            "name": f"ADCP Buy - {po_number}",
            "startDate": proposal.start_time.isoformat(),
            "endDate": proposal.end_time.isoformat(),
        }
        
        try:
            campaign_response = requests.post(f"{self.base_url}/campaigns", headers=self.headers, json=campaign_payload)
            campaign_response.raise_for_status()
            campaign_data = campaign_response.json()
            campaign_id = campaign_data['id']
            print(f"Successfully created Triton Campaign with ID: {campaign_id}")

            for package in proposal.media_packages:
                if package.package_id not in accepted_packages:
                    continue

                # Build targeting for Triton
                targeting = {}
                ad_server_targeting = package.provided_signals.ad_server_targeting
                if ad_server_targeting:
                    triton_targets = [t.get('triton') for t in ad_server_targeting if 'triton' in t]
                    for t in triton_targets:
                        if t.get('type') == 'station':
                            targeting['stationIds'] = targeting.get('stationIds', []) + [t['id']]
                        elif t.get('type') == 'genre':
                            targeting['genres'] = targeting.get('genres', []) + [t['name']]

                flight_payload = {
                    "campaignId": campaign_id,
                    "name": package.name,
                    "startDate": proposal.start_time.isoformat(),
                    "endDate": proposal.end_time.isoformat(),
                    "rate": package.cpm,
                    "rateType": "CPM",
                    "goal": {"type": "IMPRESSIONS", "value": int((package.budget / package.cpm) * 1000) if package.cpm > 0 else 0},
                    "targeting": targeting
                }
                
                flight_response = requests.post(f"{self.base_url}/flights", headers=self.headers, json=flight_payload)
                flight_response.raise_for_status()
                flight_data = flight_response.json()
                print(f"Successfully created Triton Flight with ID: {flight_data['id']}")

            creative_deadline = max(proposal.start_time - timedelta(days=5), today)
            return AcceptProposalResponse(
                media_buy_id=campaign_id,
                status="pending_creative",
                creative_deadline=creative_deadline
            )

        except requests.exceptions.RequestException as e:
            print(f"Error creating Triton Campaign/Flight: {e}")
            raise

    def add_creative_assets(self, media_buy_id: str, assets: List[Dict[str, Any]], today: datetime) -> List[AssetStatus]:
        """Uploads creatives and associates them with flights in a campaign."""
        created_asset_statuses = []

        for asset in assets:
            # This is a simplified example for an audio creative.
            creative_payload = {
                "name": asset['name'],
                "type": "AUDIO",
                "url": asset['video_url'] # Assuming video_url is a placeholder for the audio file url
            }
            
            try:
                creative_response = requests.post(
                    f"{self.base_url}/creatives",
                    headers=self.headers,
                    json=creative_payload
                )
                creative_response.raise_for_status()
                creative_data = creative_response.json()
                creative_id = creative_data['id']
                print(f"Successfully created Triton Creative with ID: {creative_id}")

                # Associate the creative with all flights in the campaign
                flights_response = requests.get(f"{self.base_url}/flights?campaignId={media_buy_id}", headers=self.headers)
                flights_response.raise_for_status()
                flights = flights_response.json()

                for flight in flights:
                    flight_id = flight['id']
                    association_payload = {"creativeIds": [creative_id]}
                    assoc_response = requests.put(
                        f"{self.base_url}/flights/{flight_id}",
                        headers=self.headers,
                        json=association_payload
                    )
                    assoc_response.raise_for_status()
                    print(f"Associated creative {creative_id} with flight {flight_id}")

                created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="approved"))

            except requests.exceptions.RequestException as e:
                print(f"Error creating Triton Creative or associating with flight: {e}")
                created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="failed"))

        return created_asset_statuses

    def check_media_buy_status(self, media_buy_id: str, today: datetime) -> CheckMediaBuyStatusResponse:
        """Checks the status of a Campaign in the Triton TAP API."""
        try:
            response = requests.get(
                f"{self.base_url}/campaigns/{media_buy_id}",
                headers=self.headers
            )
            response.raise_for_status()
            campaign_data = response.json()

            # The Triton API has a simple 'active' boolean. We can map this
            # to our more detailed status enum. This is a simplified mapping.
            status = "live" if campaign_data.get('active', False) else "paused"
            
            # If the campaign's end date is in the past, it's completed.
            end_date = datetime.fromisoformat(campaign_data['endDate'])
            if end_date < today:
                status = "completed"

            return CheckMediaBuyStatusResponse(
                media_buy_id=media_buy_id,
                status=status,
                last_updated=datetime.now().astimezone()
            )

        except requests.exceptions.RequestException as e:
            print(f"Error checking Triton Campaign status: {e}")
            raise

    def get_media_buy_delivery(self, media_buy_id: str, date_range: ReportingPeriod, today: datetime) -> GetMediaBuyDeliveryResponse:
        """Runs and parses a delivery report from the Triton TAP API."""
        
        report_payload = {
            "reportType": "FLIGHT",
            "startDate": date_range.start.strftime('%Y-%m-%d'),
            "endDate": date_range.end.strftime('%Y-%m-%d'),
            "filters": {"campaigns": [media_buy_id]},
            "columns": ["flightName", "impressions", "totalRevenue"]
        }

        try:
            response = requests.post(f"{self.base_url}/reports", headers=self.headers, json=report_payload)
            response.raise_for_status()
            report_job = response.json()
            job_id = report_job['id']
            print(f"Successfully initiated Triton report job: {job_id}")

            import time
            for _ in range(10): # Poll for up to 5 seconds
                status_response = requests.get(f"{self.base_url}/reports/{job_id}", headers=self.headers)
                status_response.raise_for_status()
                status_data = status_response.json()
                if status_data['status'] == 'COMPLETED':
                    report_url = status_data['url']
                    break
                time.sleep(0.5)
            else:
                raise Exception("Triton report did not complete in time.")

            report_response = requests.get(report_url)
            report_response.raise_for_status()
            
            import io, csv
            report_reader = csv.reader(io.StringIO(report_response.text))
            header = next(report_reader)
            col_map = {col: i for i, col in enumerate(header)}

            totals = {'impressions': 0, 'spend': 0.0, 'clicks': 0, 'video_completions': 0}
            by_package = {}

            for row in report_reader:
                impressions = int(row[col_map['impressions']])
                spend = float(row[col_map['totalRevenue']])
                package_name = row[col_map['flightName']]

                totals['impressions'] += impressions
                totals['spend'] += spend

                if package_name not in by_package:
                    by_package[package_name] = {'impressions': 0, 'spend': 0.0}
                
                by_package[package_name]['impressions'] += impressions
                by_package[package_name]['spend'] += spend

            return GetMediaBuyDeliveryResponse(
                media_buy_id=media_buy_id,
                reporting_period=date_range,
                totals=totals,
                by_package=[{'package_id': k, **v} for k, v in by_package.items()],
                currency="USD"
            )

        except requests.exceptions.RequestException as e:
            print(f"Error getting delivery report from Triton: {e}")
            raise

    def update_media_buy_performance_index(self, media_buy_id: str, package_performance: List[PackagePerformance]) -> bool:
        print(f"Triton Adapter: update_media_buy_performance_index for campaign {media_buy_id} called.")
        # This concept may not map directly to Triton. It might involve updating flight priorities or targeting.
        return True

    def update_media_buy(self, media_buy_id: str, action: str, package_id: Optional[str], budget: Optional[int], today: datetime) -> UpdateMediaBuyResponse:
        """Updates a Flight within a Campaign in the Triton TAP API."""
        if action != "change_package_budget" or not package_id or budget is None:
            raise ValueError(f"Action '{action}' is not supported or required parameters are missing.")

        try:
            # Find the flight by campaign ID and name (package_id)
            flights_response = requests.get(f"{self.base_url}/flights?campaignId={media_buy_id}", headers=self.headers)
            flights_response.raise_for_status()
            flights = flights_response.json()
            
            flight_to_update = next((f for f in flights if f['name'] == package_id), None)

            if not flight_to_update:
                raise ValueError(f"Could not find Flight with name '{package_id}' in Campaign '{media_buy_id}'")

            flight_id = flight_to_update['id']
            
            # Calculate the new impression goal from the budget
            cpm = flight_to_update.get('rate', 0)
            new_impression_goal = int((budget / cpm) * 1000) if cpm > 0 else 0
            
            update_payload = {
                "goal": {
                    "type": "IMPRESSIONS",
                    "value": new_impression_goal
                }
            }

            update_response = requests.put(
                f"{self.base_url}/flights/{flight_id}",
                headers=self.headers,
                json=update_payload
            )
            update_response.raise_for_status()
            
            print(f"Successfully updated budget for Triton Flight {flight_id}")
            return UpdateMediaBuyResponse(status="accepted", implementation_date=today + timedelta(days=1))

        except requests.exceptions.RequestException as e:
            print(f"Error updating Triton Flight: {e}")
            raise
