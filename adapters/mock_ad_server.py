from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import random

from adapters.base import AdServerAdapter
from schemas import *

class MockAdServer(AdServerAdapter):
    """
    A mock ad server that simulates the lifecycle of a media buy.
    It conforms to the AdServerAdapter interface.
    """
    adapter_name = "mock"
    _media_buys: Dict[str, Dict[str, Any]] = {}
    
    # Supported targeting dimensions (mock supports everything)
    SUPPORTED_DEVICE_TYPES = {"mobile", "desktop", "tablet", "ctv", "dooh", "audio"}
    SUPPORTED_MEDIA_TYPES = {"video", "display", "native", "audio", "dooh"}
    
    def _validate_targeting(self, targeting_overlay):
        """Mock adapter accepts all targeting."""
        return []  # No unsupported features

    def create_media_buy(self, request: CreateMediaBuyRequest, packages: List[MediaPackage], start_time: datetime, end_time: datetime) -> CreateMediaBuyResponse:
        """Simulates the creation of a media buy."""
        # Log operation start
        self.audit_logger.log_operation(
            operation="create_media_buy",
            principal_name=self.principal.name,
            principal_id=self.principal.principal_id,
            adapter_id=self.adapter_principal_id,
            success=True,
            details={
                "media_buy_id": f"buy_{request.po_number}",
                "po_number": request.po_number,
                "flight_dates": f"{start_time.date()} to {end_time.date()}"
            }
        )
        
        media_buy_id = f"buy_{request.po_number}"
        
        # Calculate total budget from packages (CPM * impressions / 1000)
        total_budget = sum((p.cpm * p.impressions / 1000) for p in packages if p.delivery_type == 'guaranteed')
        # Use the request's total_budget if available, otherwise use calculated
        total_budget = request.total_budget if request.total_budget else total_budget
        
        self.log(f"Creating media buy with ID: {media_buy_id}")
        self.log(f"Budget: ${total_budget:,.2f}")
        self.log(f"Flight dates: {start_time.date()} to {end_time.date()}")
        
        # Simulate API call details
        if self.dry_run:
            self.log(f"Would call: MockAdServer.createCampaign()")
            self.log(f"  API Request: {{")
            self.log(f"    'advertiser_id': '{self.adapter_principal_id}',")
            self.log(f"    'campaign_name': 'AdCP Campaign {media_buy_id}',")
            self.log(f"    'budget': {total_budget},")
            self.log(f"    'start_date': '{start_time.isoformat()}',")
            self.log(f"    'end_date': '{end_time.isoformat()}',")
            self.log(f"    'targeting': {{")
            if request.targeting_overlay:
                if request.targeting_overlay.geo_country_any_of:
                    self.log(f"      'countries': {request.targeting_overlay.geo_country_any_of},")
                if request.targeting_overlay.geo_region_any_of:
                    self.log(f"      'regions': {request.targeting_overlay.geo_region_any_of},")
                if request.targeting_overlay.device_type_any_of:
                    self.log(f"      'devices': {request.targeting_overlay.device_type_any_of},")
                if request.targeting_overlay.media_type_any_of:
                    self.log(f"      'media_types': {request.targeting_overlay.media_type_any_of},")
            self.log(f"    }}")
            self.log(f"  }}")
        
        if not self.dry_run:
            self._media_buys[media_buy_id] = {
                "id": media_buy_id,
                "po_number": request.po_number,
                "packages": [p.model_dump() for p in packages],
                "total_budget": total_budget,
                "start_time": start_time,
                "end_time": end_time,
                "creatives": []
            }
            self.log("✓ Media buy created successfully")
            self.log(f"  Campaign ID: {media_buy_id}")
            # Log successful creation
            self.audit_logger.log_success(f"Created Mock Order ID: {media_buy_id}")
        else:
            self.log(f"Would return: Campaign ID '{media_buy_id}' with status 'pending_creative'")
        
        return CreateMediaBuyResponse(
            media_buy_id=media_buy_id,
            status="pending_creative",
            detail="Media buy created successfully",
            creative_deadline=datetime.now() + timedelta(days=2)
        )

    def add_creative_assets(self, media_buy_id: str, assets: List[Dict[str, Any]], today: datetime) -> List[AssetStatus]:
        """Simulates adding creatives and returns an 'approved' status."""
        # Log operation
        self.audit_logger.log_operation(
            operation="add_creative_assets",
            principal_name=self.principal.name,
            principal_id=self.principal.principal_id,
            adapter_id=self.adapter_principal_id,
            success=True,
            details={
                "media_buy_id": media_buy_id,
                "creative_count": len(assets)
            }
        )
        
        self.log(f"[bold]MockAdServer.add_creative_assets[/bold] for campaign '{media_buy_id}'", dry_run_prefix=False)
        self.log(f"Adding {len(assets)} creative assets")
        
        if self.dry_run:
            for i, asset in enumerate(assets):
                self.log(f"Would call: MockAdServer.uploadCreative()")
                self.log(f"  Creative {i+1}:")
                self.log(f"    'creative_id': '{asset['id']}',")
                self.log(f"    'name': '{asset['name']}',")
                self.log(f"    'format': '{asset['format']}',")
                self.log(f"    'media_url': '{asset['media_url']}',")
                self.log(f"    'click_url': '{asset['click_url']}'")
            self.log(f"Would return: All {len(assets)} creatives with status 'approved'")
        else:
            if media_buy_id not in self._media_buys:
                raise ValueError(f"Media buy {media_buy_id} not found.")
            
            self._media_buys[media_buy_id]["creatives"].extend(assets)
            self.log(f"✓ Successfully uploaded {len(assets)} creatives")
        
        return [AssetStatus(creative_id=asset['id'], status="approved") for asset in assets]

    def check_media_buy_status(self, media_buy_id: str, today: datetime) -> CheckMediaBuyStatusResponse:
        """Simulates checking the status of a media buy."""
        if media_buy_id not in self._media_buys:
            raise ValueError(f"Media buy {media_buy_id} not found.")
        
        buy = self._media_buys[media_buy_id]
        start_date = buy['start_time']
        end_date = buy['end_time']

        if today < start_date:
            status = "pending_start"
        elif today > end_date:
            status = "completed"
        else:
            status = "delivering"
            
        return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status=status)

    def get_media_buy_delivery(self, media_buy_id: str, date_range: ReportingPeriod, today: datetime) -> AdapterGetMediaBuyDeliveryResponse:
        """Simulates getting delivery data for a media buy."""
        self.log(f"[bold]MockAdServer.get_media_buy_delivery[/bold] for principal '{self.principal.name}' and media buy '{media_buy_id}'", dry_run_prefix=False)
        self.log(f"Reporting date: {today}")
        
        # Simulate API call
        if self.dry_run:
            self.log(f"Would call: MockAdServer.getDeliveryReport()")
            self.log(f"  API Request: {{")
            self.log(f"    'advertiser_id': '{self.adapter_principal_id}',")
            self.log(f"    'campaign_id': '{media_buy_id}',")
            self.log(f"    'start_date': '{date_range.start.date()}',")
            self.log(f"    'end_date': '{date_range.end.date()}'")
            self.log(f"  }}")
        else:
            self.log(f"Retrieving delivery data for campaign {media_buy_id}")
        
        # Get the media buy details
        if media_buy_id in self._media_buys:
            buy = self._media_buys[media_buy_id]
            total_budget = buy['total_budget']
            start_time = buy['start_time']
            end_time = buy['end_time']
            
            # Calculate campaign progress
            campaign_duration = (end_time - start_time).total_seconds() / 86400  # days
            elapsed_duration = (today - start_time).total_seconds() / 86400  # days
            
            if elapsed_duration <= 0:
                # Campaign hasn't started
                impressions = 0
                spend = 0.0
            elif elapsed_duration >= campaign_duration:
                # Campaign completed - deliver full budget with some variance
                spend = total_budget * random.uniform(0.95, 1.05)
                impressions = int(spend / 0.01)  # $10 CPM
            else:
                # Campaign in progress - calculate based on pacing
                progress = elapsed_duration / campaign_duration
                daily_budget = total_budget / campaign_duration
                
                # Add some daily variance
                daily_variance = random.uniform(0.8, 1.2)
                spend = daily_budget * elapsed_duration * daily_variance
                
                # Cap at total budget
                spend = min(spend, total_budget)
                impressions = int(spend / 0.01)  # $10 CPM
        else:
            # Fallback for missing media buy
            impressions = random.randint(8000, 12000)
            spend = impressions * 0.01  # $10 CPM
        
        if not self.dry_run:
            self.log(f"✓ Retrieved delivery data: {impressions:,} impressions, ${spend:,.2f} spend")
        else:
            self.log(f"Would retrieve delivery data from ad server")
        
        return AdapterGetMediaBuyDeliveryResponse(
            media_buy_id=media_buy_id,
            reporting_period=date_range,
            totals=DeliveryTotals(impressions=impressions, spend=spend, clicks=100, video_completions=5000),
            by_package=[],
            currency="USD"
        )

    def update_media_buy_performance_index(self, media_buy_id: str, package_performance: List[PackagePerformance]) -> bool:
        return True

    def update_media_buy(self, media_buy_id: str, action: str, package_id: Optional[str], budget: Optional[int], today: datetime) -> UpdateMediaBuyResponse:
        return UpdateMediaBuyResponse(status="accepted")
    
    def get_config_ui_endpoint(self) -> Optional[str]:
        """Return the URL path for the mock adapter's configuration UI."""
        return "/adapters/mock/config"
    
    def register_ui_routes(self, app):
        """Register Flask routes for the mock adapter configuration UI."""
        from flask import render_template, request, redirect, url_for, flash
        import json
        
        @app.route('/adapters/mock/config/<tenant_id>/<product_id>', methods=['GET', 'POST'])
        def mock_product_config(tenant_id, product_id):
            # Import here to avoid circular imports
            from admin_ui import get_db_connection, require_auth
            from functools import wraps
            
            # Apply auth decorator manually
            @require_auth()
            @wraps(mock_product_config)
            def wrapped_view():
                conn = get_db_connection()
                
                # Get product details
                cursor = conn.execute(
                    "SELECT name, implementation_config FROM products WHERE tenant_id = ? AND product_id = ?",
                    (tenant_id, product_id)
                )
                product_row = cursor.fetchone()
                
                if not product_row:
                    conn.close()
                    return "Product not found", 404
                
                product = {
                    'product_id': product_id,
                    'name': product_row[0]
                }
                
                # Get current config
                implementation_config = product_row[1]
                if isinstance(implementation_config, str):
                    config = json.loads(implementation_config) if implementation_config else {}
                else:
                    config = implementation_config or {}
                
                if request.method == 'POST':
                    # Update configuration
                    new_config = {
                        'daily_impressions': int(request.form.get('daily_impressions', 100000)),
                        'fill_rate': float(request.form.get('fill_rate', 85)),
                        'ctr': float(request.form.get('ctr', 0.5)),
                        'viewability_rate': float(request.form.get('viewability_rate', 70)),
                        'latency_ms': int(request.form.get('latency_ms', 50)),
                        'error_rate': float(request.form.get('error_rate', 0.1)),
                        'test_mode': request.form.get('test_mode', 'normal'),
                        'price_variance': float(request.form.get('price_variance', 10)),
                        'seasonal_factor': float(request.form.get('seasonal_factor', 1.0)),
                        'verbose_logging': 'verbose_logging' in request.form,
                        'predictable_ids': 'predictable_ids' in request.form
                    }
                    
                    # Validate the configuration
                    validation_errors = self.validate_product_config(new_config)
                    if validation_errors:
                        conn.close()
                        return render_template('adapters/mock_product_config.html',
                                             tenant_id=tenant_id,
                                             product=product,
                                             config=config,
                                             error=validation_errors[0])
                    
                    # Save to database
                    conn.execute(
                        "UPDATE products SET implementation_config = ? WHERE tenant_id = ? AND product_id = ?",
                        (json.dumps(new_config), tenant_id, product_id)
                    )
                    conn.connection.commit()
                    conn.close()
                    
                    return render_template('adapters/mock_product_config.html',
                                         tenant_id=tenant_id,
                                         product=product,
                                         config=new_config,
                                         success=True)
                
                conn.close()
                return render_template('adapters/mock_product_config.html',
                                     tenant_id=tenant_id,
                                     product=product,
                                     config=config)
            
            return wrapped_view()
    
    def validate_product_config(self, config: dict) -> List[str]:
        """Validate mock adapter configuration."""
        errors = []
        
        # Validate ranges
        if config.get('fill_rate', 0) < 0 or config.get('fill_rate', 0) > 100:
            errors.append("Fill rate must be between 0 and 100")
        
        if config.get('error_rate', 0) < 0 or config.get('error_rate', 0) > 100:
            errors.append("Error rate must be between 0 and 100")
        
        if config.get('ctr', 0) < 0 or config.get('ctr', 0) > 100:
            errors.append("CTR must be between 0 and 100")
        
        if config.get('viewability_rate', 0) < 0 or config.get('viewability_rate', 0) > 100:
            errors.append("Viewability rate must be between 0 and 100")
        
        if config.get('daily_impressions', 0) < 1000:
            errors.append("Daily impressions must be at least 1000")
        
        if config.get('latency_ms', 0) < 0:
            errors.append("Latency cannot be negative")
        
        return errors
    
    async def get_available_inventory(self) -> Dict[str, Any]:
        """
        Return mock inventory that simulates a typical publisher's ad server.
        This helps demonstrate the AI configuration capabilities.
        """
        return {
            "placements": [
                {
                    "id": "homepage_top", 
                    "name": "Homepage Top Banner",
                    "path": "/",
                    "sizes": ["728x90", "970x250", "970x90"],
                    "position": "above_fold",
                    "typical_cpm": 15.0
                },
                {
                    "id": "homepage_sidebar",
                    "name": "Homepage Sidebar",
                    "path": "/", 
                    "sizes": ["300x250", "300x600"],
                    "position": "right_rail",
                    "typical_cpm": 8.0
                },
                {
                    "id": "article_inline",
                    "name": "Article Inline",
                    "path": "/article/*",
                    "sizes": ["300x250", "336x280", "728x90"],
                    "position": "in_content",
                    "typical_cpm": 5.0
                },
                {
                    "id": "article_sidebar_sticky",
                    "name": "Article Sidebar Sticky",
                    "path": "/article/*",
                    "sizes": ["300x250", "300x600"],
                    "position": "sticky_rail",
                    "typical_cpm": 10.0
                },
                {
                    "id": "category_top",
                    "name": "Category Page Banner",
                    "path": "/category/*",
                    "sizes": ["728x90", "970x90"],
                    "position": "above_fold",
                    "typical_cpm": 12.0
                },
                {
                    "id": "mobile_interstitial",
                    "name": "Mobile Interstitial",
                    "path": "/*",
                    "sizes": ["320x480", "300x250"],
                    "position": "interstitial",
                    "device": "mobile",
                    "typical_cpm": 20.0
                },
                {
                    "id": "video_preroll",
                    "name": "Video Pre-roll",
                    "path": "/video/*",
                    "sizes": ["640x360", "640x480"],
                    "position": "preroll",
                    "format": "video",
                    "typical_cpm": 25.0
                }
            ],
            "ad_units": [
                {"path": "/", "name": "Homepage", "placements": ["homepage_top", "homepage_sidebar"]},
                {"path": "/article/*", "name": "Article Pages", "placements": ["article_inline", "article_sidebar_sticky"]},
                {"path": "/category/*", "name": "Category Pages", "placements": ["category_top"]},
                {"path": "/video/*", "name": "Video Pages", "placements": ["video_preroll"]},
                {"path": "/sports", "name": "Sports Section", "placements": ["homepage_top", "article_inline"]},
                {"path": "/business", "name": "Business Section", "placements": ["homepage_top", "article_inline"]},
                {"path": "/technology", "name": "Tech Section", "placements": ["homepage_top", "article_inline", "article_sidebar_sticky"]}
            ],
            "targeting_options": {
                "geo": {
                    "countries": ["US", "CA", "GB", "AU", "DE", "FR", "IT", "ES", "NL", "SE", "JP", "BR", "MX"],
                    "us_states": ["CA", "NY", "TX", "FL", "IL", "WA", "MA", "PA", "OH", "GA"],
                    "us_dmas": ["New York", "Los Angeles", "Chicago", "Philadelphia", "Dallas-Ft. Worth", "San Francisco-Oakland-San Jose"]
                },
                "device": ["desktop", "mobile", "tablet"],
                "os": ["windows", "macos", "ios", "android", "linux"],
                "browser": ["chrome", "safari", "firefox", "edge", "samsung"],
                "categories": {
                    "iab": ["IAB1", "IAB2", "IAB3", "IAB4", "IAB5"],
                    "custom": ["sports", "business", "technology", "entertainment", "lifestyle", "politics"]
                },
                "audience": {
                    "demographics": ["18-24", "25-34", "35-44", "45-54", "55+"],
                    "interests": ["sports_enthusiast", "tech_savvy", "luxury_shopper", "travel_lover", "fitness_focused"],
                    "behavior": ["frequent_buyer", "early_adopter", "price_conscious"]
                }
            },
            "creative_specs": [
                {"type": "display", "sizes": ["300x250", "728x90", "970x250", "300x600", "320x50", "336x280", "970x90"]},
                {"type": "video", "durations": [15, 30, 60], "sizes": ["640x360", "640x480", "1920x1080"]},
                {"type": "native", "components": ["title", "description", "image", "cta_button"]},
                {"type": "audio", "durations": [15, 30], "formats": ["mp3", "ogg"]}
            ],
            "properties": {
                "monthly_impressions": 50000000,
                "unique_visitors": 10000000,
                "content_categories": ["news", "sports", "business", "technology", "entertainment"],
                "viewability_average": 0.65,
                "premium_inventory_percentage": 0.3
            }
        }
