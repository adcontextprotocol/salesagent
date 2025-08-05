from datetime import datetime, timedelta
import random
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from googleads import ad_manager
import google.oauth2.service_account
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash

from adapters.base import AdServerAdapter, CreativeEngineAdapter
from schemas import (
    CheckMediaBuyStatusResponse, AdapterGetMediaBuyDeliveryResponse,
    UpdateMediaBuyResponse, ReportingPeriod, PackagePerformance, AssetStatus,
    CreateMediaBuyResponse, CreateMediaBuyRequest, MediaPackage, DeliveryTotals,
    PackageDelivery, Principal
)
from adapters.constants import UPDATE_ACTIONS, REQUIRED_UPDATE_ACTIONS
from adapters.gam_implementation_config_schema import GAMImplementationConfig

class GoogleAdManager(AdServerAdapter):
    """
    Adapter for interacting with the Google Ad Manager API.
    """
    adapter_name = "gam"
    def __init__(
        self, 
        config: Dict[str, Any], 
        principal: Principal,
        dry_run: bool = False,
        creative_engine: Optional[CreativeEngineAdapter] = None,
        tenant_id: Optional[str] = None
    ):
        super().__init__(config, principal, dry_run, creative_engine, tenant_id)
        self.network_code = self.config.get("network_code")
        self.key_file = self.config.get("service_account_key_file")
        self.refresh_token = self.config.get("refresh_token")
        self.company_id = self.config.get("company_id")
        self.trafficker_id = self.config.get("trafficker_id", None)

        # Use adapter_principal_id as the advertiser_id
        self.advertiser_id = self.adapter_principal_id

        # Check for either service account or OAuth credentials
        if not self.dry_run:
            if not self.network_code:
                raise ValueError("GAM config is missing 'network_code'")
            if not self.advertiser_id:
                raise ValueError("GAM config is missing 'advertiser_id'")
            if not self.trafficker_id:
                raise ValueError("GAM config is missing 'trafficker_id'")
            if not self.company_id:
                raise ValueError("GAM config is missing 'company_id'")
            if not self.key_file and not self.refresh_token:
                raise ValueError("GAM config requires either 'service_account_key_file' or 'refresh_token'")

        if not self.dry_run:
            self.client = self._init_client()
        else:
            self.client = None
            self.log("[yellow]Running in dry-run mode - GAM client not initialized[/yellow]")
        
        # Load geo mappings
        self._load_geo_mappings()

    def _init_client(self):
        """Initializes the Ad Manager client using the helper function."""
        try:
            # Use the new helper function if we have a tenant_id
            if self.tenant_id:
                from gam_helper import get_ad_manager_client_for_tenant
                return get_ad_manager_client_for_tenant(self.tenant_id)
            
            # Fallback to old method for backward compatibility
            if self.refresh_token:
                # Use OAuth with refresh token
                oauth2_credentials = self._get_oauth_credentials()
            else:
                # Use service account (legacy)
                oauth2_credentials = google.oauth2.service_account.Credentials.from_service_account_file(
                    self.key_file,
                    scopes=['https://www.googleapis.com/auth/dfp']
                )
            
            # This should not be reached anymore since we use gam_helper
            # but keeping for backward compatibility
            raise NotImplementedError("Direct GoogleAdManagerClient creation is deprecated. Use gam_helper instead.")
        except Exception as e:
            print(f"Error initializing GAM client: {e}")
            raise
    
    def _get_oauth_credentials(self):
        """Get OAuth credentials using refresh token and superadmin config."""
        from db_config import get_db_connection
        from googleads import oauth2
        
        # Get OAuth client credentials from superadmin config
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT config_value FROM superadmin_config WHERE config_key = 'gam_oauth_client_id'"
            )
            client_id_row = cursor.fetchone()
            
            cursor.execute(
                "SELECT config_value FROM superadmin_config WHERE config_key = 'gam_oauth_client_secret'"
            )
            client_secret_row = cursor.fetchone()
            
            if not client_id_row or not client_id_row[0]:
                raise ValueError("GAM OAuth Client ID not configured in superadmin settings")
            if not client_secret_row or not client_secret_row[0]:
                raise ValueError("GAM OAuth Client Secret not configured in superadmin settings")
            
            client_id = client_id_row[0]
            client_secret = client_secret_row[0]
        
        # Create GoogleAds OAuth2 client
        oauth2_client = oauth2.GoogleRefreshTokenClient(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=self.refresh_token
        )
        
        return oauth2_client
    
    # Supported device types and their GAM mappings
    DEVICE_TYPE_MAP = {
        "mobile": "MOBILE",
        "desktop": "DESKTOP", 
        "tablet": "TABLET",
        "ctv": "CONNECTED_TV",
        "dooh": "SET_TOP_BOX"
    }
    
    def _load_geo_mappings(self):
        """Load geo mappings from JSON file."""
        try:
            mapping_file = os.path.join(os.path.dirname(__file__), 'gam_geo_mappings.json')
            with open(mapping_file, 'r') as f:
                geo_data = json.load(f)
                
            self.GEO_COUNTRY_MAP = geo_data.get('countries', {})
            self.GEO_REGION_MAP = geo_data.get('regions', {})
            self.GEO_METRO_MAP = geo_data.get('metros', {}).get('US', {})  # Currently only US metros
            
            self.log(f"Loaded GAM geo mappings: {len(self.GEO_COUNTRY_MAP)} countries, "
                    f"{sum(len(v) for v in self.GEO_REGION_MAP.values())} regions, "
                    f"{len(self.GEO_METRO_MAP)} metros")
        except Exception as e:
            self.log(f"[yellow]Warning: Could not load geo mappings file: {e}[/yellow]")
            self.log("[yellow]Using empty geo mappings - geo targeting will not work properly[/yellow]")
            self.GEO_COUNTRY_MAP = {}
            self.GEO_REGION_MAP = {}
            self.GEO_METRO_MAP = {}
    
    def _lookup_region_id(self, region_code):
        """Look up region ID across all countries."""
        # First check if we have country context (not implemented yet)
        # For now, search across all countries
        for country, regions in self.GEO_REGION_MAP.items():
            if region_code in regions:
                return regions[region_code]
        return None
    
    # Supported media types
    SUPPORTED_MEDIA_TYPES = {"video", "display", "native"}
    
    def _validate_targeting(self, targeting_overlay):
        """Validate targeting and return unsupported features."""
        unsupported = []
        
        if not targeting_overlay:
            return unsupported
        
        # Check device types
        if targeting_overlay.device_type_any_of:
            for device in targeting_overlay.device_type_any_of:
                if device not in self.DEVICE_TYPE_MAP:
                    unsupported.append(f"Device type '{device}' not supported")
        
        # Check media types
        if targeting_overlay.media_type_any_of:
            for media in targeting_overlay.media_type_any_of:
                if media not in self.SUPPORTED_MEDIA_TYPES:
                    unsupported.append(f"Media type '{media}' not supported")
        
        # Audio-specific targeting not supported
        if targeting_overlay.media_type_any_of and "audio" in targeting_overlay.media_type_any_of:
            unsupported.append("Audio media type not supported by Google Ad Manager")
        
        # City and postal targeting require GAM API lookups (not implemented)
        if targeting_overlay.geo_city_any_of or targeting_overlay.geo_city_none_of:
            unsupported.append("City targeting requires GAM geo service integration (not implemented)")
        if targeting_overlay.geo_zip_any_of or targeting_overlay.geo_zip_none_of:
            unsupported.append("Postal code targeting requires GAM geo service integration (not implemented)")
        
        # GAM supports all other standard targeting dimensions
        
        return unsupported

    def _build_targeting(self, targeting_overlay):
        """Build GAM targeting criteria from AdCP targeting."""
        if not targeting_overlay:
            return {}
        
        gam_targeting = {}
        
        # Geographic targeting
        geo_targeting = {}
        
        # Build targeted locations
        if any([targeting_overlay.geo_country_any_of, targeting_overlay.geo_region_any_of,
                targeting_overlay.geo_metro_any_of, targeting_overlay.geo_city_any_of,
                targeting_overlay.geo_zip_any_of]):
            geo_targeting['targetedLocations'] = []
            
            # Map countries
            if targeting_overlay.geo_country_any_of:
                for country in targeting_overlay.geo_country_any_of:
                    if country in self.GEO_COUNTRY_MAP:
                        geo_targeting['targetedLocations'].append({'id': self.GEO_COUNTRY_MAP[country]})
                    else:
                        self.log(f"[yellow]Warning: Country code '{country}' not in GAM mapping[/yellow]")
            
            # Map regions
            if targeting_overlay.geo_region_any_of:
                for region in targeting_overlay.geo_region_any_of:
                    region_id = self._lookup_region_id(region)
                    if region_id:
                        geo_targeting['targetedLocations'].append({'id': region_id})
                    else:
                        self.log(f"[yellow]Warning: Region code '{region}' not in GAM mapping[/yellow]")
            
            # Map metros (DMAs)
            if targeting_overlay.geo_metro_any_of:
                for metro in targeting_overlay.geo_metro_any_of:
                    if metro in self.GEO_METRO_MAP:
                        geo_targeting['targetedLocations'].append({'id': self.GEO_METRO_MAP[metro]})
                    else:
                        self.log(f"[yellow]Warning: Metro code '{metro}' not in GAM mapping[/yellow]")
            
            # City and postal require real GAM API lookup - for now we log a warning
            if targeting_overlay.geo_city_any_of:
                self.log("[yellow]Warning: City targeting requires GAM geo service lookup (not implemented)[/yellow]")
            if targeting_overlay.geo_zip_any_of:
                self.log("[yellow]Warning: Postal code targeting requires GAM geo service lookup (not implemented)[/yellow]")
                
        # Build excluded locations
        if any([targeting_overlay.geo_country_none_of, targeting_overlay.geo_region_none_of,
                targeting_overlay.geo_metro_none_of, targeting_overlay.geo_city_none_of,
                targeting_overlay.geo_zip_none_of]):
            geo_targeting['excludedLocations'] = []
            
            # Map excluded countries
            if targeting_overlay.geo_country_none_of:
                for country in targeting_overlay.geo_country_none_of:
                    if country in self.GEO_COUNTRY_MAP:
                        geo_targeting['excludedLocations'].append({'id': self.GEO_COUNTRY_MAP[country]})
            
            # Map excluded regions
            if targeting_overlay.geo_region_none_of:
                for region in targeting_overlay.geo_region_none_of:
                    region_id = self._lookup_region_id(region)
                    if region_id:
                        geo_targeting['excludedLocations'].append({'id': region_id})
            
            # Map excluded metros
            if targeting_overlay.geo_metro_none_of:
                for metro in targeting_overlay.geo_metro_none_of:
                    if metro in self.GEO_METRO_MAP:
                        geo_targeting['excludedLocations'].append({'id': self.GEO_METRO_MAP[metro]})
            
            # City and postal exclusions
            if targeting_overlay.geo_city_none_of:
                self.log("[yellow]Warning: City exclusion requires GAM geo service lookup (not implemented)[/yellow]")
            if targeting_overlay.geo_zip_none_of:
                self.log("[yellow]Warning: Postal code exclusion requires GAM geo service lookup (not implemented)[/yellow]")
            
        if geo_targeting:
            gam_targeting['geoTargeting'] = geo_targeting
        
        # Technology/Device targeting
        tech_targeting = {}
        
        if targeting_overlay.device_type_any_of:
            device_categories = []
            for device in targeting_overlay.device_type_any_of:
                if device in self.DEVICE_TYPE_MAP:
                    device_categories.append(self.DEVICE_TYPE_MAP[device])
            if device_categories:
                tech_targeting['deviceCategories'] = device_categories
        
        if targeting_overlay.os_any_of:
            tech_targeting['operatingSystems'] = [os.upper() for os in targeting_overlay.os_any_of]
            
        if targeting_overlay.browser_any_of:
            tech_targeting['browsers'] = [b.upper() for b in targeting_overlay.browser_any_of]
            
        if tech_targeting:
            gam_targeting['technologyTargeting'] = tech_targeting
        
        # Content targeting
        if targeting_overlay.content_cat_any_of or targeting_overlay.keywords_any_of:
            content_targeting = {}
            if targeting_overlay.content_cat_any_of:
                content_targeting['targetedContentCategories'] = targeting_overlay.content_cat_any_of
            if targeting_overlay.keywords_any_of:
                content_targeting['targetedKeywords'] = targeting_overlay.keywords_any_of
            gam_targeting['contentTargeting'] = content_targeting
        
        # Dayparting
        if targeting_overlay.dayparting:
            daypart_targeting = []
            
            for schedule in targeting_overlay.dayparting.schedules:
                daypart_targeting.append({
                    'dayOfWeek': [f'DAY_{d}' for d in schedule.days],
                    'startTime': {'hour': schedule.start_hour, 'minute': 0},
                    'endTime': {'hour': schedule.end_hour, 'minute': 0},
                    'timeZone': schedule.timezone or targeting_overlay.dayparting.timezone
                })
            
            gam_targeting['dayPartTargeting'] = daypart_targeting
        
        # Custom key-value targeting
        custom_targeting = {}
        
        # Platform-specific custom targeting
        if targeting_overlay.custom and 'gam' in targeting_overlay.custom:
            custom_targeting.update(targeting_overlay.custom['gam'].get('key_values', {}))
        
        # AEE signal integration via key-value pairs (managed-only)
        if targeting_overlay.key_value_pairs:
            self.log("[bold cyan]Adding AEE signals to GAM key-value targeting[/bold cyan]")
            for key, value in targeting_overlay.key_value_pairs.items():
                custom_targeting[key] = value
                self.log(f"  {key}: {value}")
        
        if custom_targeting:
            gam_targeting['customTargeting'] = custom_targeting
        
        self.log(f"Applying GAM targeting: {list(gam_targeting.keys())}")
        return gam_targeting

    def create_media_buy(self, request: CreateMediaBuyRequest, packages: List[MediaPackage], start_time: datetime, end_time: datetime) -> CreateMediaBuyResponse:
        """Creates a new Order and associated LineItems in Google Ad Manager."""
        # Get products to access implementation_config
        from db_config import get_db_connection
        
        # Create a map of package_id to product for easy lookup
        products_map = {}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for package in packages:
                cursor.execute(
                    "SELECT product_id, implementation_config FROM products WHERE tenant_id = %s AND product_id = %s",
                    (self.tenant_id, package.package_id)  # package_id is actually product_id
                )
                product_row = cursor.fetchone()
                if product_row:
                    products_map[package.package_id] = {
                        'product_id': product_row[0],
                        'implementation_config': product_row[1] or {}
                    }
        
        # Log operation
        self.audit_logger.log_operation(
            operation="create_media_buy",
            principal_name=self.principal.name,
            principal_id=self.principal.principal_id,
            adapter_id=self.advertiser_id,
            success=True,
            details={
                "po_number": request.po_number,
                "flight_dates": f"{start_time.date()} to {end_time.date()}"
            }
        )
        
        self.log(f"[bold]GoogleAdManager.create_media_buy[/bold] for principal '{self.principal.name}' (GAM advertiser ID: {self.advertiser_id})", dry_run_prefix=False)
        
        # Validate targeting
        unsupported_features = self._validate_targeting(request.targeting_overlay)
        if unsupported_features:
            error_msg = f"Unsupported targeting features for Google Ad Manager: {', '.join(unsupported_features)}"
            self.log(f"[red]Error: {error_msg}[/red]")
            return CreateMediaBuyResponse(
                media_buy_id="",
                status="failed",
                detail=error_msg
            )
        
        media_buy_id = f"gam_{int(datetime.now().timestamp())}"
        
        # Get order name template from first product's config (they should all be the same)
        order_name_template = "AdCP-{po_number}-{timestamp}"
        applied_team_ids = []
        if products_map:
            first_product = next(iter(products_map.values()))
            if first_product.get('implementation_config'):
                order_name_template = first_product['implementation_config'].get('order_name_template', order_name_template)
                applied_team_ids = first_product['implementation_config'].get('applied_team_ids', [])
        
        # Format order name
        order_name = order_name_template.format(
            po_number=request.po_number or media_buy_id,
            product_name=packages[0].name if packages else "Unknown",
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
            principal_name=self.principal.name
        )
        
        # Create Order object
        order = {
            'name': order_name,
            'advertiserId': self.advertiser_id,
            'traffickerId': self.trafficker_id,
            'totalBudget': {
                'currencyCode': 'USD',
                'microAmount': int(request.total_budget * 1_000_000)
            },
            'startDateTime': {
                'date': {
                    'year': start_time.year,
                    'month': start_time.month,
                    'day': start_time.day
                },
                'hour': start_time.hour,
                'minute': start_time.minute,
                'second': start_time.second
            },
            'endDateTime': {
                'date': {
                    'year': end_time.year,
                    'month': end_time.month,
                    'day': end_time.day
                },
                'hour': end_time.hour,
                'minute': end_time.minute,
                'second': end_time.second
            }
        }
        
        # Add team IDs if configured
        if applied_team_ids:
            order['appliedTeamIds'] = applied_team_ids
        
        if self.dry_run:
            self.log(f"Would call: order_service.createOrders([{order['name']}])")
            self.log(f"  Advertiser ID: {self.advertiser_id}")
            self.log(f"  Total Budget: ${request.total_budget:,.2f}")
            self.log(f"  Flight Dates: {start_time.date()} to {end_time.date()}")
        else:
            order_service = self.client.GetService('OrderService')
            created_orders = order_service.createOrders([order])
            if created_orders:
                media_buy_id = str(created_orders[0]['id'])
                self.log(f"✓ Created GAM Order ID: {media_buy_id}")
                self.audit_logger.log_success(f"Created GAM Order ID: {media_buy_id}")
        
        # Create LineItems for each package
        for package in packages:
            # Get product-specific configuration
            product = products_map.get(package.package_id)
            impl_config = product.get('implementation_config', {}) if product else {}
            
            # Build targeting - merge product targeting with request overlay
            targeting = self._build_targeting(request.targeting_overlay)
            
            # Add ad unit/placement targeting from product config
            if impl_config.get('targeted_ad_unit_ids'):
                if 'inventoryTargeting' not in targeting:
                    targeting['inventoryTargeting'] = {}
                targeting['inventoryTargeting']['targetedAdUnits'] = [
                    {'adUnitId': ad_unit_id, 'includeDescendants': impl_config.get('include_descendants', True)}
                    for ad_unit_id in impl_config['targeted_ad_unit_ids']
                ]
            
            if impl_config.get('targeted_placement_ids'):
                if 'inventoryTargeting' not in targeting:
                    targeting['inventoryTargeting'] = {}
                targeting['inventoryTargeting']['targetedPlacements'] = [
                    {'placementId': placement_id} for placement_id in impl_config['targeted_placement_ids']
                ]
            
            # Add custom targeting from product config
            if impl_config.get('custom_targeting_keys'):
                if 'customTargeting' not in targeting:
                    targeting['customTargeting'] = {}
                targeting['customTargeting'].update(impl_config['custom_targeting_keys'])
            
            # Build creative placeholders from config
            creative_placeholders = []
            if impl_config.get('creative_placeholders'):
                for placeholder in impl_config['creative_placeholders']:
                    creative_placeholders.append({
                        'size': {'width': placeholder['width'], 'height': placeholder['height']},
                        'expectedCreativeCount': placeholder.get('expected_creative_count', 1),
                        'creativeSizeType': 'NATIVE' if placeholder.get('is_native') else 'PIXEL'
                    })
            else:
                # Default placeholder if none configured
                creative_placeholders = [{
                    'size': {'width': 300, 'height': 250},
                    'expectedCreativeCount': 1,
                    'creativeSizeType': 'PIXEL'
                }]
            
            line_item = {
                'name': package.name,
                'orderId': media_buy_id,
                'targeting': targeting,
                'creativePlaceholders': creative_placeholders,
                'lineItemType': impl_config.get('line_item_type', 'STANDARD'),
                'priority': impl_config.get('priority', 8),
                'costType': impl_config.get('cost_type', 'CPM'),
                'costPerUnit': {
                    'currencyCode': 'USD',
                    'microAmount': int(package.cpm * 1_000_000)
                },
                'primaryGoal': {
                    'goalType': impl_config.get('primary_goal_type', 'LIFETIME'),
                    'unitType': impl_config.get('primary_goal_unit_type', 'IMPRESSIONS'),
                    'units': package.impressions
                },
                'creativeRotationType': impl_config.get('creative_rotation_type', 'EVEN'),
                'deliveryRateType': impl_config.get('delivery_rate_type', 'EVENLY')
            }
            
            # Add frequency caps if configured
            if impl_config.get('frequency_caps'):
                frequency_caps = []
                for cap in impl_config['frequency_caps']:
                    frequency_caps.append({
                        'maxImpressions': cap['max_impressions'],
                        'numTimeUnits': cap['time_range'],
                        'timeUnit': cap['time_unit']
                    })
                line_item['frequencyCaps'] = frequency_caps
            
            # Add competitive exclusion labels
            if impl_config.get('competitive_exclusion_labels'):
                line_item['effectiveAppliedLabels'] = [
                    {'labelId': label} for label in impl_config['competitive_exclusion_labels']
                ]
            
            # Add discount if configured
            if impl_config.get('discount_type') and impl_config.get('discount_value'):
                line_item['discount'] = impl_config['discount_value']
                line_item['discountType'] = impl_config['discount_type']
            
            # Add video-specific settings
            if impl_config.get('environment_type') == 'VIDEO_PLAYER':
                line_item['environmentType'] = 'VIDEO_PLAYER'
                if impl_config.get('companion_delivery_option'):
                    line_item['companionDeliveryOption'] = impl_config['companion_delivery_option']
                if impl_config.get('video_max_duration'):
                    line_item['videoMaxDuration'] = impl_config['video_max_duration']
                if impl_config.get('skip_offset'):
                    line_item['videoSkippableAdType'] = 'ENABLED'
                    line_item['videoSkipOffset'] = impl_config['skip_offset']
            else:
                line_item['environmentType'] = impl_config.get('environment_type', 'BROWSER')
            
            # Advanced settings
            if impl_config.get('allow_overbook'):
                line_item['allowOverbook'] = True
            if impl_config.get('skip_inventory_check'):
                line_item['skipInventoryCheck'] = True
            if impl_config.get('disable_viewability_avg_revenue_optimization'):
                line_item['disableViewabilityAvgRevenueOptimization'] = True
            
            if self.dry_run:
                self.log(f"Would call: line_item_service.createLineItems(['{package.name}'])")
                self.log(f"  Package: {package.name}")
                self.log(f"  Line Item Type: {impl_config.get('line_item_type', 'STANDARD')}")
                self.log(f"  Priority: {impl_config.get('priority', 8)}")
                self.log(f"  CPM: ${package.cpm}")
                self.log(f"  Impressions Goal: {package.impressions:,}")
                self.log(f"  Creative Placeholders: {len(creative_placeholders)} sizes")
                for cp in creative_placeholders[:3]:  # Show first 3
                    self.log(f"    - {cp['size']['width']}x{cp['size']['height']} ({'Native' if cp.get('creativeSizeType') == 'NATIVE' else 'Display'})")
                if len(creative_placeholders) > 3:
                    self.log(f"    - ... and {len(creative_placeholders) - 3} more")
                if impl_config.get('frequency_caps'):
                    self.log(f"  Frequency Caps: {len(impl_config['frequency_caps'])} configured")
                if impl_config.get('targeted_ad_unit_ids'):
                    self.log(f"  Targeted Ad Units: {len(impl_config['targeted_ad_unit_ids'])} units")
                if impl_config.get('environment_type') == 'VIDEO_PLAYER':
                    self.log(f"  Video Settings: max duration {impl_config.get('video_max_duration', 'N/A')}ms, skip after {impl_config.get('skip_offset', 'N/A')}ms")
            else:
                line_item_service = self.client.GetService('LineItemService')
                created_line_items = line_item_service.createLineItems([line_item])
                if created_line_items:
                    self.log(f"✓ Created LineItem ID: {created_line_items[0]['id']} for {package.name}")
                    self.audit_logger.log_success(f"Created GAM LineItem ID: {created_line_items[0]['id']}")
        
        return CreateMediaBuyResponse(
            media_buy_id=media_buy_id,
            status="pending_activation",
            detail="Media buy created in Google Ad Manager",
            creative_deadline=datetime.now() + timedelta(days=2)
        )


    def add_creative_assets(self, media_buy_id: str, assets: List[Dict[str, Any]], today: datetime) -> List[AssetStatus]:
        """Creates a new Creative in GAM and associates it with LineItems."""
        self.log(f"[bold]GoogleAdManager.add_creative_assets[/bold] for order '{media_buy_id}'")
        self.log(f"Adding {len(assets)} creative assets")
        
        if not self.dry_run:
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
                self.log(f"Skipping asset {asset['creative_id']} with unsupported format: {asset['format']}")
                continue

            if self.dry_run:
                self.log(f"Would call: creative_service.createCreatives(['{creative['name']}'])")
                self.log(f"  Type: {creative.get('xsi_type', 'Unknown')}")
                self.log(f"  Size: {creative['size']['width']}x{creative['size']['height']}")
                self.log(f"  Destination URL: {creative['destinationUrl']}")
                created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="approved"))
            else:
                try:
                    created_creatives = creative_service.createCreatives([creative])
                    if not created_creatives:
                        raise Exception(f"Failed to create creative for asset {asset['creative_id']}")

                    creative_id = created_creatives[0]['id']
                    self.log(f"✓ Created GAM Creative with ID: {creative_id}")

                    # Associate the creative with the assigned line items
                    line_item_ids_to_associate = [line_item_map[pkg_id] for pkg_id in asset['package_assignments'] if pkg_id in line_item_map]

                    if line_item_ids_to_associate:
                        licas = [{'lineItemId': line_item_id, 'creativeId': creative_id} for line_item_id in line_item_ids_to_associate]
                        lica_service.createLineItemCreativeAssociations(licas)
                        self.log(f"✓ Associated creative {creative_id} with {len(line_item_ids_to_associate)} line items.")
                    else:
                        self.log(f"[yellow]Warning: No matching line items found for creative {creative_id} package assignments.[/yellow]")

                    created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="approved"))

                except Exception as e:
                    self.log(f"[red]Error creating GAM Creative or LICA for asset {asset['creative_id']}: {e}[/red]")
                    created_asset_statuses.append(AssetStatus(creative_id=asset['creative_id'], status="failed"))

        return created_asset_statuses

    def check_media_buy_status(self, media_buy_id: str, today: datetime) -> CheckMediaBuyStatusResponse:
        """Checks the status of all LineItems in a GAM Order."""
        self.log(f"[bold]GoogleAdManager.check_media_buy_status[/bold] for order '{media_buy_id}'")
        
        if self.dry_run:
            self.log(f"Would call: line_item_service.getLineItemsByStatement()")
            self.log(f"  Query: WHERE orderId = {media_buy_id}")
            return CheckMediaBuyStatusResponse(
                media_buy_id=media_buy_id,
                status="delivering",
                last_updated=datetime.now().astimezone()
            )
        
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

    def get_media_buy_delivery(self, media_buy_id: str, date_range: ReportingPeriod, today: datetime) -> AdapterGetMediaBuyDeliveryResponse:
        """Runs and parses a delivery report in GAM to get detailed performance data."""
        self.log(f"[bold]GoogleAdManager.get_media_buy_delivery[/bold] for order '{media_buy_id}'")
        self.log(f"Date range: {date_range.start.date()} to {date_range.end.date()}")
        
        if self.dry_run:
            # Simulate the report query
            self.log(f"Would call: report_service.runReportJob()")
            self.log(f"  Report Query:")
            self.log(f"    Dimensions: DATE, ORDER_ID, LINE_ITEM_ID, CREATIVE_ID")
            self.log(f"    Columns: AD_SERVER_IMPRESSIONS, AD_SERVER_CLICKS, AD_SERVER_CPM_AND_CPC_REVENUE")
            self.log(f"    Date Range: {date_range.start.date()} to {date_range.end.date()}")
            self.log(f"    Filter: ORDER_ID = {media_buy_id}")
            
            # Return simulated data
            simulated_impressions = random.randint(50000, 150000)
            simulated_spend = simulated_impressions * 0.01  # $10 CPM
            
            self.log(f"Would return: {simulated_impressions:,} impressions, ${simulated_spend:,.2f} spend")
            
            return AdapterGetMediaBuyDeliveryResponse(
                media_buy_id=media_buy_id,
                reporting_period=date_range,
                totals=DeliveryTotals(
                    impressions=simulated_impressions,
                    spend=simulated_spend,
                    clicks=int(simulated_impressions * 0.002),  # 0.2% CTR
                    video_completions=int(simulated_impressions * 0.7)  # 70% completion rate
                ),
                by_package=[],
                currency="USD"
            )
        
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

            return AdapterGetMediaBuyDeliveryResponse(
                media_buy_id=media_buy_id,
                reporting_period=date_range,
                totals=DeliveryTotals(**totals),
                by_package=[PackageDelivery(package_id=k, **v) for k, v in by_package.items()],
                currency="USD"
            )

        except Exception as e:
            print(f"Error getting delivery report from GAM: {e}")
            raise

    def update_media_buy_performance_index(self, media_buy_id: str, package_performance: List[PackagePerformance]) -> bool:
        print("GAM Adapter: update_media_buy_performance_index called. (Not yet implemented)")
        return True

    def update_media_buy(self, media_buy_id: str, action: str, package_id: Optional[str], budget: Optional[int], today: datetime) -> UpdateMediaBuyResponse:
        """Updates an Order or LineItem in GAM using standardized actions."""
        self.log(f"[bold]GoogleAdManager.update_media_buy[/bold] for {media_buy_id} with action {action}", dry_run_prefix=False)
        
        if action not in REQUIRED_UPDATE_ACTIONS:
            return UpdateMediaBuyResponse(
                status="failed", 
                reason=f"Action '{action}' not supported. Supported actions: {REQUIRED_UPDATE_ACTIONS}"
            )
        
        if self.dry_run:
            if action == "pause_media_buy":
                self.log(f"Would pause Order {media_buy_id}")
                self.log(f"Would call: order_service.performOrderAction(PauseOrders, {media_buy_id})")
            elif action == "resume_media_buy":
                self.log(f"Would resume Order {media_buy_id}")
                self.log(f"Would call: order_service.performOrderAction(ResumeOrders, {media_buy_id})")
            elif action == "pause_package" and package_id:
                self.log(f"Would pause LineItem '{package_id}' in Order {media_buy_id}")
                self.log(f"Would call: line_item_service.performLineItemAction(PauseLineItems, WHERE orderId={media_buy_id} AND name='{package_id}')")
            elif action == "resume_package" and package_id:
                self.log(f"Would resume LineItem '{package_id}' in Order {media_buy_id}")
                self.log(f"Would call: line_item_service.performLineItemAction(ResumeLineItems, WHERE orderId={media_buy_id} AND name='{package_id}')")
            elif action in ["update_package_budget", "update_package_impressions"] and package_id and budget is not None:
                self.log(f"Would update budget for LineItem '{package_id}' to ${budget}")
                if action == "update_package_impressions":
                    self.log(f"Would directly set impression goal")
                else:
                    self.log(f"Would calculate new impression goal based on CPM")
                self.log(f"Would call: line_item_service.updateLineItems([updated_line_item])")
            
            return UpdateMediaBuyResponse(
                status="accepted",
                implementation_date=today + timedelta(days=1),
                detail=f"Would {action} in Google Ad Manager"
            )
        else:
            try:
                if action in ["pause_media_buy", "resume_media_buy"]:
                    order_service = self.client.GetService('OrderService')
                    
                    if action == "pause_media_buy":
                        order_action = {'xsi_type': 'PauseOrders'}
                    else:
                        order_action = {'xsi_type': 'ResumeOrders'}
                    
                    statement = (self.client.new_statement_builder()
                                .where('id = :orderId')
                                .with_bind_variable('orderId', int(media_buy_id)))
                    
                    result = order_service.performOrderAction(order_action, statement.to_statement())
                    
                    if result and result['numChanges'] > 0:
                        self.log(f"✓ Successfully performed {action} on Order {media_buy_id}")
                    else:
                        return UpdateMediaBuyResponse(
                            status="failed",
                            reason=f"No orders were updated"
                        )
                
                elif action in ["pause_package", "resume_package"] and package_id:
                    line_item_service = self.client.GetService('LineItemService')
                    
                    if action == "pause_package":
                        line_item_action = {'xsi_type': 'PauseLineItems'}
                    else:
                        line_item_action = {'xsi_type': 'ResumeLineItems'}
                    
                    statement = (self.client.new_statement_builder()
                                .where('orderId = :orderId AND name = :name')
                                .with_bind_variable('orderId', int(media_buy_id))
                                .with_bind_variable('name', package_id))
                    
                    result = line_item_service.performLineItemAction(line_item_action, statement.to_statement())
                    
                    if result and result['numChanges'] > 0:
                        self.log(f"✓ Successfully performed {action} on LineItem '{package_id}'")
                    else:
                        return UpdateMediaBuyResponse(
                            status="failed",
                            reason=f"No line items were updated"
                        )
                
                elif action in ["update_package_budget", "update_package_impressions"] and package_id and budget is not None:
                    line_item_service = self.client.GetService('LineItemService')
                    
                    statement = (self.client.new_statement_builder()
                                .where('orderId = :orderId AND name = :name')
                                .with_bind_variable('orderId', int(media_buy_id))
                                .with_bind_variable('name', package_id))
                    
                    response = line_item_service.getLineItemsByStatement(statement.to_statement())
                    line_items = response.get('results', [])
                    
                    if not line_items:
                        return UpdateMediaBuyResponse(
                            status="failed",
                            reason=f"Could not find LineItem with name '{package_id}' in Order '{media_buy_id}'"
                        )
                    
                    line_item_to_update = line_items[0]
                    
                    if action == "update_package_budget":
                        # Calculate new impression goal based on the new budget
                        cpm = line_item_to_update['costPerUnit']['microAmount'] / 1000000
                        new_impression_goal = int((budget / cpm) * 1000) if cpm > 0 else 0
                    else:  # update_package_impressions
                        # Direct impression update
                        new_impression_goal = budget  # In this case, budget parameter contains impressions
                    
                    line_item_to_update['primaryGoal']['units'] = new_impression_goal
                    
                    updated_line_items = line_item_service.updateLineItems([line_item_to_update])
                    
                    if not updated_line_items:
                        return UpdateMediaBuyResponse(
                            status="failed",
                            reason="Failed to update LineItem in GAM"
                        )
                    
                    self.log(f"✓ Successfully updated budget for LineItem {line_item_to_update['id']}")
                
                return UpdateMediaBuyResponse(
                    status="accepted",
                    implementation_date=today + timedelta(days=1),
                    detail=f"Successfully executed {action} in Google Ad Manager"
                )
                
            except Exception as e:
                self.log(f"[red]Error updating GAM Order/LineItem: {e}[/red]")
                return UpdateMediaBuyResponse(
                    status="failed",
                    reason=str(e)
                )
    
    def get_config_ui_endpoint(self) -> Optional[str]:
        """Return the endpoint path for GAM-specific configuration UI."""
        return "/adapters/gam/config"
    
    def register_ui_routes(self, app: Flask) -> None:
        """Register GAM-specific configuration UI routes."""
        
        @app.route('/adapters/gam/config/<tenant_id>/<product_id>', methods=['GET', 'POST'])
        def gam_product_config(tenant_id, product_id):
            from db_config import get_db_connection
            
            # Get tenant and product
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT name FROM tenants WHERE tenant_id = %s",
                    (tenant_id,)
                )
                tenant_row = cursor.fetchone()
                if not tenant_row:
                    flash('Tenant not found', 'error')
                    return redirect(url_for('tenants'))
                
                cursor.execute(
                    "SELECT product_id, name, implementation_config FROM products WHERE tenant_id = %s AND product_id = %s",
                    (tenant_id, product_id)
                )
                product_row = cursor.fetchone()
            
            if not product_row:
                flash('Product not found', 'error')
                return redirect(url_for('products', tenant_id=tenant_id))
            
            product_id_db, product_name, implementation_config = product_row
            
            # Get network code from adapter config
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT gam_network_code FROM adapter_config WHERE tenant_id = %s",
                    (tenant_id,)
                )
                adapter_row = cursor.fetchone()
                network_code = adapter_row[0] if adapter_row else 'XXXXX'
            
            if request.method == 'POST':
                try:
                    # Build config from form data
                    config = {
                        'order_name_template': request.form.get('order_name_template'),
                        'applied_team_ids': [int(x.strip()) for x in request.form.get('applied_team_ids', '').split(',') if x.strip()],
                        'line_item_type': request.form.get('line_item_type'),
                        'priority': int(request.form.get('priority', 8)),
                        'cost_type': request.form.get('cost_type'),
                        'creative_rotation_type': request.form.get('creative_rotation_type'),
                        'delivery_rate_type': request.form.get('delivery_rate_type'),
                        'primary_goal_type': request.form.get('primary_goal_type'),
                        'primary_goal_unit_type': request.form.get('primary_goal_unit_type'),
                        'include_descendants': 'include_descendants' in request.form,
                        'environment_type': request.form.get('environment_type'),
                        'allow_overbook': 'allow_overbook' in request.form,
                        'skip_inventory_check': 'skip_inventory_check' in request.form,
                        'disable_viewability_avg_revenue_optimization': 'disable_viewability_avg_revenue_optimization' in request.form,
                    }
                    
                    # Process creative placeholders
                    widths = request.form.getlist('placeholder_width[]')
                    heights = request.form.getlist('placeholder_height[]')
                    counts = request.form.getlist('placeholder_count[]')
                    is_natives = request.form.getlist('placeholder_is_native[]')
                    
                    creative_placeholders = []
                    for i in range(len(widths)):
                        if widths[i] and heights[i]:
                            creative_placeholders.append({
                                'width': int(widths[i]),
                                'height': int(heights[i]),
                                'expected_creative_count': int(counts[i]) if i < len(counts) else 1,
                                'is_native': f'placeholder_is_native_{i}' in request.form
                            })
                    config['creative_placeholders'] = creative_placeholders
                    
                    # Process frequency caps
                    cap_impressions = request.form.getlist('cap_max_impressions[]')
                    cap_units = request.form.getlist('cap_time_unit[]')
                    cap_ranges = request.form.getlist('cap_time_range[]')
                    
                    frequency_caps = []
                    for i in range(len(cap_impressions)):
                        if cap_impressions[i]:
                            frequency_caps.append({
                                'max_impressions': int(cap_impressions[i]),
                                'time_unit': cap_units[i] if i < len(cap_units) else 'DAY',
                                'time_range': int(cap_ranges[i]) if i < len(cap_ranges) else 1
                            })
                    config['frequency_caps'] = frequency_caps
                    
                    # Process targeting
                    config['targeted_ad_unit_ids'] = [x.strip() for x in request.form.get('targeted_ad_unit_ids', '').split('\n') if x.strip()]
                    config['targeted_placement_ids'] = [x.strip() for x in request.form.get('targeted_placement_ids', '').split('\n') if x.strip()]
                    config['competitive_exclusion_labels'] = [x.strip() for x in request.form.get('competitive_exclusion_labels', '').split(',') if x.strip()]
                    
                    # Process discount
                    if request.form.get('discount_type'):
                        config['discount_type'] = request.form.get('discount_type')
                        config['discount_value'] = float(request.form.get('discount_value', 0))
                    
                    # Process video settings
                    if config['environment_type'] == 'VIDEO_PLAYER':
                        if request.form.get('companion_delivery_option'):
                            config['companion_delivery_option'] = request.form.get('companion_delivery_option')
                        if request.form.get('video_max_duration'):
                            config['video_max_duration'] = int(request.form.get('video_max_duration')) * 1000  # Convert to milliseconds
                        if request.form.get('skip_offset'):
                            config['skip_offset'] = int(request.form.get('skip_offset')) * 1000  # Convert to milliseconds
                    
                    # Process custom targeting
                    custom_targeting = request.form.get('custom_targeting_keys', '{}')
                    try:
                        config['custom_targeting_keys'] = json.loads(custom_targeting) if custom_targeting else {}
                    except json.JSONDecodeError:
                        config['custom_targeting_keys'] = {}
                    
                    # Native style ID
                    if request.form.get('native_style_id'):
                        config['native_style_id'] = request.form.get('native_style_id')
                    
                    # Validate the configuration
                    validation_result = self.validate_product_config(config)
                    if validation_result[0]:
                        # Save to database
                        with get_db_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE products SET implementation_config = %s WHERE tenant_id = %s AND product_id = %s",
                                (config, tenant_id, product_id)
                            )
                            conn.connection.commit()
                        flash('GAM configuration saved successfully', 'success')
                        return redirect(url_for('edit_product', tenant_id=tenant_id, product_id=product_id))
                    else:
                        flash(f'Validation error: {validation_result[1]}', 'error')
                
                except Exception as e:
                    flash(f'Error saving configuration: {str(e)}', 'error')
            
            # Load existing config or defaults
            config = implementation_config or {}
            
            return render_template('adapters/gam_product_config.html',
                                 tenant_id=tenant_id,
                                 product={'product_id': product_id_db, 'name': product_name},
                                 config=config,
                                 network_code=network_code)
    
    def validate_product_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate GAM-specific product configuration."""
        try:
            # Use Pydantic model for validation
            gam_config = GAMImplementationConfig(**config)
            
            # Additional custom validation
            if not gam_config.creative_placeholders:
                return False, "At least one creative placeholder is required"
            
            # Validate team IDs are positive integers
            for team_id in gam_config.applied_team_ids:
                if team_id <= 0:
                    return False, f"Invalid team ID: {team_id}"
            
            # Validate frequency caps
            for cap in gam_config.frequency_caps:
                if cap.max_impressions <= 0:
                    return False, "Frequency cap impressions must be positive"
                if cap.time_range <= 0:
                    return False, "Frequency cap time range must be positive"
            
            return True, None
            
        except Exception as e:
            return False, str(e)
