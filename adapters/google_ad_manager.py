from datetime import datetime, timedelta, timedelta
from typing import List, Dict, Any, Optional
from googleads import ad_manager
import google.oauth2.service_account

from adapters.base import AdServerAdapter, CreativeEngineAdapter
from schemas import (
    AcceptProposalResponse, CheckMediaBuyStatusResponse, GetMediaBuyDeliveryResponse,
    UpdateMediaBuyResponse, Proposal, ReportingPeriod, PackagePerformance, AssetStatus
)

class GoogleAdManager(AdServerAdapter):
    """
    Adapter for interacting with the Google Ad Manager API.
    """
    def __init__(self, config: Dict[str, Any], creative_engine: Optional[CreativeEngineAdapter] = None):
        super().__init__(config, creative_engine)
        self.network_code = self.config.get("network_code")
        self.key_file = self.config.get("service_account_key_file")
        self.advertiser_id = self.config.get("advertiser_id")
        self.company_id = self.config.get("company_id")
        self.trafficker_id = self.config.get("trafficker_id", None)

        if not all([self.network_code, self.key_file, self.advertiser_id, self.trafficker_id, self.company_id]):
            raise ValueError("GAM config is missing one of 'network_code', 'service_account_key_file', 'advertiser_id', 'trafficker_id', or 'company_id'")

        self.client = self._init_client()

    def _init_client(self):
        """Initializes the Ad Manager client."""
        try:
            oauth2_credentials = google.oauth2.service_account.Credentials.from_service_account_file(
                self.key_file,
                scopes=['https.www.googleapis.com/auth/dfp']
            )
            return google.ads.ad_manager.GoogleAdManagerClient(
                oauth2_credentials,
                application_name=f"ADCP-Buy-Side-Agent-{self.network_code}"
            )
        except FileNotFoundError:
            print(f"Error: Service account key file not found at '{self.key_file}'.")
            print("Please ensure the path in your config.json is correct.")
            raise
        except Exception as e:
            print(f"Error initializing GAM client: {e}")
            raise

    def accept_proposal(self, proposal: Proposal, accepted_packages: List[str], billing_entity: str, po_number: str, today: datetime) -> AcceptProposalResponse:
        """Creates a new Order and associated LineItems in Google Ad Manager."""
        order_service = self.client.GetService('OrderService')
        line_item_service = self.client.GetService('LineItemService')
        targeting_map = self.config.get('targeting_mapping', {})

        order = {
            'name': f"ADCP Buy - {po_number}",
            'poNumber': po_number,
            'advertiserId': self.advertiser_id,
            'traffickerId': self.trafficker_id
        }

        try:
            created_orders = order_service.createOrders([order])
            if not created_orders:
                raise Exception("Failed to create order in GAM.")

            order_id = created_orders[0]['id']
            print(f"Successfully created GAM Order with ID: {order_id}")

            line_items_to_create = []
            for package in proposal.media_packages:
                if package.package_id not in accepted_packages:
                    continue

                # Build targeting based on the new ad_server_targeting data
                targeting = {'geoTargeting': {}, 'deviceCapabilityTargeting': {}}
                ad_server_targeting = package.provided_signals.ad_server_targeting
                if ad_server_targeting:
                    gam_targets = [t.get('gam') for t in ad_server_targeting if 'gam' in t]
                    
                    # Audience Segment Targeting
                    audience_segment_ids = [t['id'] for t in gam_targets if t.get('type') == 'audience_segment']
                    if audience_segment_ids:
                        targeting['audienceSegmentIds'] = audience_segment_ids

                    # Custom Key-Value Targeting
                    custom_targeting = {'children': []}
                    for t in gam_targets:
                        if t.get('type') == 'custom_key':
                            key_id = targeting_map.get('custom_keys', {}).get(t['key_name'])
                            if key_id:
                                custom_targeting['children'].append({
                                    'xsi_type': 'CustomCriteriaSet',
                                    'logicalOperator': 'OR',
                                    'children': [{'xsi_type': 'CustomCriteria', 'keyId': key_id, 'valueIds': [t['value_id']], 'operator': 'IS'}]
                                })
                    if custom_targeting['children']:
                        targeting['customTargeting'] = custom_targeting

                    # Geography Targeting
                    geo_locations = []
                    for t in gam_targets:
                        if t.get('type') == 'geography':
                            geo_locations.append({'id': t['id']})
                    if geo_locations:
                        targeting['geoTargeting']['targetedLocations'] = geo_locations

                    # Device Targeting
                    device_capabilities = []
                    for t in gam_targets:
                        if t.get('type') == 'device_capability':
                            device_capabilities.append({'id': t['id']})
                    if device_capabilities:
                        targeting['deviceCapabilityTargeting']['targetedDeviceCapabilities'] = device_capabilities

                line_item = {
                    'orderId': order_id,
                    'name': package.name,
                    'startDateTime': proposal.start_time,
                    'endDateTime': proposal.end_time,
                    'lineItemType': 'STANDARD',
                    'costType': 'CPM',
                    'costPerUnit': {'currencyCode': 'USD', 'microAmount': int(package.cpm * 1000000)},
                    'primaryGoal': {
                        'goalType': 'LIFETIME',
                        'unitType': 'IMPRESSIONS',
                        'units': int((package.budget / package.cpm) * 1000) if package.cpm > 0 else 0
                    },
                    'targeting': targeting
                }
                line_items_to_create.append(line_item)

            if line_items_to_create:
                created_line_items = line_item_service.createLineItems(line_items_to_create)
                print(f"Successfully created {len(created_line_items)} LineItems for Order {order_id}")

            creative_deadline = max(proposal.start_time - timedelta(days=5), today)
            return AcceptProposalResponse(
                media_buy_id=str(order_id),
                status="pending_creative",
                creative_deadline=creative_deadline
            )

        except Exception as e:
            print(f"Error in accept_proposal for GAM: {e}")
            raise

    def add_creative_assets(self, media_buy_id: str, assets: List[Dict[str, Any]], today: datetime) -> List[AssetStatus]:
        """Creates a new Creative in GAM and associates it with LineItems."""
        creative_service = self.client.GetService('CreativeService')
        lica_service = self.client.GetService('LineItemCreativeAssociationService')
        line_item_service = self.client.GetService('LineItemService')

        created_asset_statuses = []

        # Create a mapping from package_id (which is the line item name) to line_item_id
        statement = (self.client.new_statement_builder()
                     .where('orderId = :orderId')
                     .with_bind_variable('orderId', int(media_buy_id)))
        response = line_item_service.getLineItemsByStatement(statement.to_statement())
        line_item_map = {item['name']: item['id'] for item in response.get('results', [])}

        for asset in assets:
            creative = {
                'advertiserId': self.company_id,
                'name': asset['name'],
                'size': {'width': asset.get('width', 300), 'height': asset.get('height', 250)}, # Use provided or default size
                'destinationUrl': asset['click_url'],
            }

            if asset['format'] == 'image':
                creative['xsi_type'] = 'ImageCreative'
                creative['primaryImageAsset'] = {'assetUrl': asset['media_url']}
            elif asset['format'] == 'video':
                creative['xsi_type'] = 'VideoCreative'
                creative['videoSourceUrl'] = asset['media_url']
                creative['duration'] = asset.get('duration', 0) # Duration in milliseconds
            else:
                print(f"Skipping asset {asset['creative_id']} with unsupported format: {asset['format']}")
                continue

            try:
                created_creatives = creative_service.createCreatives([creative])
                if not created_creatives:
                    raise Exception(f"Failed to create creative for asset {asset['creative_id']}")

                creative_id = created_creatives[0]['id']
                print(f"Successfully created GAM Creative with ID: {creative_id}")

                # Associate the creative with the assigned line items
                line_item_ids_to_associate = [line_item_map[pkg_id] for pkg_id in asset['package_assignments'] if pkg_id in line_item_map]

                if line_item_ids_to_associate:
                    licas = [{'lineItemId': line_item_id, 'creativeId': creative_id} for line_item_id in line_item_ids_to_associate]
                    lica_service.createLineItemCreativeAssociations(licas)
                    print(f"Associated creative {creative_id} with {len(line_item_ids_to_associate)} line items.")
                else:
                    print(f"Warning: No matching line items found for creative {creative_id} package assignments.")

                created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="approved"))

            except Exception as e:
                print(f"Error creating GAM Creative or LICA for asset {asset['creative_id']}: {e}")
                created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="failed"))

        return created_asset_statuses

    def check_media_buy_status(self, media_buy_id: str, today: datetime) -> CheckMediaBuyStatusResponse:
        """Checks the status of all LineItems in a GAM Order."""
        line_item_service = self.client.GetService('LineItemService')
        statement = (self.client.new_statement_builder()
                     .where('orderId = :orderId')
                     .with_bind_variable('orderId', int(media_buy_id)))

        try:
            response = line_item_service.getLineItemsByStatement(statement.to_statement())
            line_items = response.get('results', [])

            if not line_items:
                return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status="pending_creative")

            # Determine the overall status. This is a simplified logic.
            # A real implementation might need to handle more nuanced statuses.
            statuses = {item['status'] for item in line_items}
            
            overall_status = "live"
            if 'PAUSED' in statuses:
                overall_status = "paused"
            elif all(s == 'DELIVERING' for s in statuses):
                overall_status = "delivering"
            elif all(s == 'COMPLETED' for s in statuses):
                overall_status = "completed"
            elif any(s in ['PENDING_APPROVAL', 'DRAFT'] for s in statuses):
                overall_status = "pending_approval"

            # For delivery data, we'd need a reporting call.
            # For now, we'll return placeholder data.
            return CheckMediaBuyStatusResponse(
                media_buy_id=media_buy_id,
                status=overall_status,
                last_updated=datetime.now().astimezone()
            )

        except Exception as e:
            print(f"Error checking media buy status in GAM: {e}")
            raise

    def get_media_buy_delivery(self, media_buy_id: str, date_range: ReportingPeriod, today: datetime) -> GetMediaBuyDeliveryResponse:
        """Runs and parses a delivery report in GAM to get detailed performance data."""
        report_service = self.client.GetService('ReportService')
        report_downloader = self.client.GetDataDownloader()

        report_job = {
            'reportQuery': {
                'dimensions': ['DATE', 'ORDER_ID', 'LINE_ITEM_ID', 'CREATIVE_ID'],
                'columns': [
                    'AD_SERVER_IMPRESSIONS',
                    'AD_SERVER_CLICKS',
                    'AD_SERVER_CTR',
                    'AD_SERVER_CPM_AND_CPC_REVENUE', # This is spend from the buyer's view
                    'VIDEO_COMPLETIONS',
                    'VIDEO_COMPLETION_RATE'
                ],
                'dateRangeType': 'CUSTOM_DATE',
                'startDate': {'year': date_range.start.year, 'month': date_range.start.month, 'day': date_range.start.day},
                'endDate': {'year': date_range.end.year, 'month': date_range.end.month, 'day': date_range.end.day},
                'statement': (self.client.new_statement_builder()
                              .where('ORDER_ID = :orderId')
                              .with_bind_variable('orderId', int(media_buy_id)))
            }
        }

        try:
            report_job_id = report_service.runReportJob(report_job)
            
            import time
            while report_service.getReportJobStatus(report_job_id) == 'IN_PROGRESS':
                time.sleep(1)

            if report_service.getReportJobStatus(report_job_id) != 'COMPLETED':
                raise Exception("GAM report failed to complete.")

            report_data = report_downloader.DownloadReportToFile(
                report_job_id, 'CSV_DUMP', open('/tmp/gam_report.csv.gz', 'wb'))

            import gzip, io, csv
            
            report_csv = gzip.open('/tmp/gam_report.csv.gz', 'rt').read()
            report_reader = csv.reader(io.StringIO(report_csv))
            
            # Skip header row
            header = next(report_reader)
            
            # Map columns to indices for robust parsing
            col_map = {col: i for i, col in enumerate(header)}

            totals = {'impressions': 0, 'spend': 0.0, 'clicks': 0, 'video_completions': 0}
            by_package = {}

            for row in report_reader:
                impressions = int(row[col_map['AD_SERVER_IMPRESSIONS']])
                spend = float(row[col_map['AD_SERVER_CPM_AND_CPC_REVENUE']]) / 1000000 # Convert from micros
                clicks = int(row[col_map['AD_SERVER_CLICKS']])
                video_completions = int(row[col_map['VIDEO_COMPLETIONS']])
                line_item_id = row[col_map['LINE_ITEM_ID']]

                totals['impressions'] += impressions
                totals['spend'] += spend
                totals['clicks'] += clicks
                totals['video_completions'] += video_completions

                if line_item_id not in by_package:
                    by_package[line_item_id] = {'impressions': 0, 'spend': 0.0}
                
                by_package[line_item_id]['impressions'] += impressions
                by_package[line_item_id]['spend'] += spend

            return GetMediaBuyDeliveryResponse(
                media_buy_id=media_buy_id,
                reporting_period=date_range,
                totals=totals,
                by_package=[{'package_id': k, **v} for k, v in by_package.items()],
                currency="USD"
            )

        except Exception as e:
            print(f"Error getting delivery report from GAM: {e}")
            raise

    def update_media_buy_performance_index(self, media_buy_id: str, package_performance: List[PackagePerformance]) -> bool:
        print("GAM Adapter: update_media_buy_performance_index called. (Not yet implemented)")
        return True

    def update_media_buy(self, media_buy_id: str, action: str, package_id: Optional[str], budget: Optional[int], today: datetime) -> UpdateMediaBuyResponse:
        """Updates a LineItem in GAM."""
        if action != "change_package_budget" or not package_id or budget is None:
            raise ValueError(f"Action '{action}' is not supported or required parameters are missing.")

        line_item_service = self.client.GetService('LineItemService')
        
        # To map our package_id to a GAM LineItem, we'll need to find the LineItem by name.
        # This assumes the package name is unique within the order.
        # A more robust solution might store the mapping of package_id to line_item_id.
        statement = (self.client.new_statement_builder()
                     .where('orderId = :orderId AND name = :name')
                     .with_bind_variable('orderId', int(media_buy_id))
                     .with_bind_variable('name', package_id)) # Assuming package_id is the name for now

        try:
            response = line_item_service.getLineItemsByStatement(statement.to_statement())
            line_items = response.get('results', [])

            if not line_items:
                raise ValueError(f"Could not find LineItem with name '{package_id}' in Order '{media_buy_id}'")

            line_item_to_update = line_items[0]
            
            # Calculate new impression goal based on the new budget
            cpm = line_item_to_update['costPerUnit']['microAmount'] / 1000000
            new_impression_goal = int((budget / cpm) * 1000) if cpm > 0 else 0
            
            line_item_to_update['primaryGoal']['units'] = new_impression_goal

            updated_line_items = line_item_service.updateLineItems([line_item_to_update])

            if not updated_line_items:
                raise Exception("Failed to update LineItem in GAM.")

            print(f"Successfully updated budget for LineItem {line_item_to_update['id']}")
            return UpdateMediaBuyResponse(status="accepted", implementation_date=today + timedelta(days=1))

        except Exception as e:
            print(f"Error updating LineItem in GAM: {e}")
            raise
