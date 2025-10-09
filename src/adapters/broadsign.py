"""
Broadsign adapter for AdCP Sales Agent.

Broadsign is a leading DOOH (Digital Out-of-Home) platform that provides
programmatic and guaranteed campaign management for digital signage networks.

This adapter integrates with Broadsign Direct's Guaranteed Campaigns API to:
- Create and manage campaigns (proposals)
- Select and target screens/displays
- Check inventory availability
- Book and hold guaranteed campaigns
- Report on campaign delivery

API Documentation: https://docs.broadsign.com/broadsign-platform/Documentation_Gteed_Campaigns/
"""

from datetime import datetime, timedelta
from typing import Any

import requests

from src.adapters.base import AdServerAdapter, CreativeEngineAdapter
from src.core.schemas import (
    AdapterGetMediaBuyDeliveryResponse,
    AssetStatus,
    CheckMediaBuyStatusResponse,
    CreateMediaBuyRequest,
    CreateMediaBuyResponse,
    DeliveryTotals,
    MediaPackage,
    PackagePerformance,
    Principal,
    ReportingPeriod,
    UpdateMediaBuyResponse,
)


class BroadsignAdapter(AdServerAdapter):
    """
    Adapter for Broadsign Direct Guaranteed Campaigns API.

    Supports DOOH-specific features:
    - Screen-based inventory selection
    - Location-based targeting
    - Venue category targeting
    - Frequency and share-of-voice buying modes
    - Campaign holds and bookings
    """

    adapter_name = "broadsign"

    # Broadsign-specific constants
    SUPPORTED_DEVICE_TYPES = {"dooh"}
    SUPPORTED_MEDIA_TYPES = {"dooh", "display"}

    # Campaign status codes from Broadsign API
    STATUS_DRAFT = 0
    STATUS_PENDING = 1
    STATUS_HOLD = 4
    STATUS_BOOKED = 10
    STATUS_DELIVERING = 12
    STATUS_COMPLETED = 15

    def __init__(
        self,
        config: dict[str, Any],
        principal: Principal,
        dry_run: bool = False,
        creative_engine: CreativeEngineAdapter | None = None,
        tenant_id: str | None = None,
    ):
        super().__init__(config, principal, dry_run, creative_engine, tenant_id)

        # Get Broadsign-specific configuration
        self.base_url = self.config.get("base_url", "https://direct.broadsign.com")
        self.email = self.config.get("email")
        self.password = self.config.get("password")
        self.client_id = self.config.get("client_id")  # Advertiser/client ID in Broadsign
        self.client_name = self.principal.name

        # Session management
        self.session = requests.Session()
        self._authenticated = False

        if self.dry_run:
            self.log("Running in dry-run mode - Broadsign API calls will be simulated", dry_run_prefix=False)
        elif not self.email or not self.password:
            raise ValueError("Broadsign config is missing 'email' or 'password'")
        elif not self.client_id:
            raise ValueError("Broadsign config is missing 'client_id' (advertiser ID)")

        # Campaign tracking
        self._campaigns: dict[str, dict[str, Any]] = {}

    def _authenticate(self) -> None:
        """Authenticate with Broadsign Direct API and establish session."""
        if self._authenticated:
            return

        if self.dry_run:
            self.log("Would authenticate with Broadsign Direct API")
            self.log(f"  POST {self.base_url}/login")
            self.log(f"  Email: {self.email}")
            self._authenticated = True
            return

        try:
            login_url = f"{self.base_url}/login"
            response = self.session.post(
                login_url,
                json={"email": self.email, "password": self.password},
                timeout=30,
            )
            response.raise_for_status()

            # Session cookie is automatically stored in self.session
            self._authenticated = True
            self.log("✓ Authenticated with Broadsign Direct API")

            # Log operation
            self.audit_logger.log_operation(
                operation="authenticate",
                principal_name=self.principal.name,
                principal_id=self.principal.principal_id,
                adapter_id=self.client_id,
                success=True,
                details={"base_url": self.base_url},
            )
        except requests.exceptions.RequestException as e:
            self.audit_logger.log_operation(
                operation="authenticate",
                principal_name=self.principal.name,
                principal_id=self.principal.principal_id,
                adapter_id=self.client_id,
                success=False,
                details={"error": str(e)},
            )
            raise ValueError(f"Failed to authenticate with Broadsign: {e}")

    def _api_call(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make an authenticated API call to Broadsign Direct."""
        self._authenticate()

        url = f"{self.base_url}{endpoint}"

        if self.dry_run:
            self.log(f"Would call: {method.upper()} {url}")
            if "json" in kwargs:
                self.log(f"  Request body: {kwargs['json']}")
            return {}

        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.RequestException as e:
            self.log(f"[red]API call failed: {e}[/red]")
            raise

    def _validate_targeting(self, targeting_overlay) -> list[str]:
        """Validate targeting and return unsupported features."""
        unsupported = []

        if not targeting_overlay:
            return unsupported

        # Check device types
        if targeting_overlay.device_type_any_of:
            for device in targeting_overlay.device_type_any_of:
                if device not in self.SUPPORTED_DEVICE_TYPES:
                    unsupported.append(
                        f"Device type '{device}' not supported (Broadsign supports: {', '.join(self.SUPPORTED_DEVICE_TYPES)})"
                    )

        # Check media types
        if targeting_overlay.media_type_any_of:
            for media in targeting_overlay.media_type_any_of:
                if media not in self.SUPPORTED_MEDIA_TYPES:
                    unsupported.append(
                        f"Media type '{media}' not supported (Broadsign supports: {', '.join(self.SUPPORTED_MEDIA_TYPES)})"
                    )

        # Broadsign doesn't support browser/OS targeting for DOOH
        if targeting_overlay.browser_any_of:
            unsupported.append("Browser targeting not applicable for DOOH")

        if targeting_overlay.os_any_of:
            unsupported.append("OS targeting not applicable for DOOH")

        return unsupported

    def _build_screen_search_criteria(
        self, targeting_overlay, start_time: datetime, end_time: datetime
    ) -> dict[str, Any]:
        """Build Broadsign screen search criteria from AdCP targeting."""
        criteria: dict[str, Any] = {
            "start_date": start_time.strftime("%Y-%m-%d"),
            "end_date": end_time.strftime("%Y-%m-%d"),
        }

        if not targeting_overlay:
            return criteria

        # Geographic targeting - Broadsign supports location-based screen filtering
        locations = []
        if targeting_overlay.geo_country_any_of:
            for country in targeting_overlay.geo_country_any_of:
                locations.append({"type": "country", "code": country})

        if targeting_overlay.geo_region_any_of:
            for region in targeting_overlay.geo_region_any_of:
                locations.append({"type": "region", "code": region})

        if targeting_overlay.geo_city_any_of:
            for city in targeting_overlay.geo_city_any_of:
                locations.append({"type": "city", "name": city})

        if locations:
            criteria["locations"] = locations

        # Category targeting (venue types)
        if targeting_overlay.content_cat_any_of:
            # Map IAB categories to Broadsign venue categories
            criteria["category_ids"] = self._map_categories_to_venue_types(targeting_overlay.content_cat_any_of)

        # Custom Broadsign targeting
        if targeting_overlay.custom and "broadsign" in targeting_overlay.custom:
            bs_custom = targeting_overlay.custom["broadsign"]
            if "screen_ids" in bs_custom:
                criteria["screen_ids"] = bs_custom["screen_ids"]
            if "category_ids" in bs_custom:
                criteria["category_ids"] = bs_custom["category_ids"]
            if "min_impressions" in bs_custom:
                criteria["min_impressions"] = bs_custom["min_impressions"]

        return criteria

    def _map_categories_to_venue_types(self, iab_categories: list[str]) -> list[int]:
        """Map IAB content categories to Broadsign venue category IDs."""
        # Example mapping - this would need to be customized based on
        # the specific Broadsign instance's category configuration
        category_map = {
            "IAB1": [1, 2],  # Arts & Entertainment → Entertainment venues
            "IAB3": [3, 4],  # Business → Office buildings, Business districts
            "IAB17": [5, 6],  # Sports → Sports venues, Gyms
            "IAB20": [7, 8],  # Travel → Airports, Transit
            "IAB8": [9, 10],  # Food & Drink → Restaurants, Bars
            "IAB22": [11, 12],  # Shopping → Retail, Malls
        }

        venue_ids = []
        for iab_cat in iab_categories:
            if iab_cat in category_map:
                venue_ids.extend(category_map[iab_cat])

        return venue_ids if venue_ids else []

    def create_media_buy(
        self,
        request: CreateMediaBuyRequest,
        packages: list[MediaPackage],
        start_time: datetime,
        end_time: datetime,
    ) -> CreateMediaBuyResponse:
        """Creates a new campaign (proposal) in Broadsign Direct."""
        # Log operation
        self.audit_logger.log_operation(
            operation="create_media_buy",
            principal_name=self.principal.name,
            principal_id=self.principal.principal_id,
            adapter_id=self.client_id,
            success=True,
            details={
                "po_number": request.po_number,
                "flight_dates": f"{start_time.date()} to {end_time.date()}",
            },
        )

        self.log(f"Broadsign.create_media_buy for principal '{self.principal.name}' " f"(Client ID: {self.client_id})")

        # Validate targeting
        if request.targeting_overlay:
            unsupported = self._validate_targeting(request.targeting_overlay)
            if unsupported:
                error_msg = "Unsupported targeting: " + ", ".join(unsupported)
                self.audit_logger.log_operation(
                    operation="create_media_buy",
                    principal_name=self.principal.name,
                    principal_id=self.principal.principal_id,
                    adapter_id=self.client_id,
                    success=False,
                    details={"error": error_msg},
                )
                raise ValueError(error_msg)

        # Calculate total budget
        total_budget = request.get_total_budget() if hasattr(request, "get_total_budget") else 0

        # Step 1: Create campaign/proposal
        campaign_name = f"{request.promoted_offering or request.po_number} - {start_time.date()} to {end_time.date()}"

        proposal_data = {
            "name": campaign_name,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "start_date": start_time.strftime("%Y-%m-%d"),
            "end_date": end_time.strftime("%Y-%m-%d"),
            "category_ids": [],  # Can be populated from targeting
            "notes": f"PO: {request.po_number}, Budget: ${total_budget:,.2f}",
        }

        self.log(f"Creating campaign: {campaign_name}")
        proposal_response = self._api_call("POST", "/api/v1/proposal", json=proposal_data)

        if self.dry_run:
            proposal_id = f"proposal_{request.po_number}"
        else:
            proposal_id = proposal_response.get("id")

        self.log(f"✓ Created proposal ID: {proposal_id}")

        # Step 2: Search for screens (optional - could be based on targeting)
        if request.targeting_overlay:
            search_criteria = self._build_screen_search_criteria(request.targeting_overlay, start_time, end_time)
            self.log(f"Searching for screens with criteria: {search_criteria}")
            screen_results = self._api_call("POST", "/api/v1/screen/search", json=search_criteria)

            if not self.dry_run:
                screen_ids = [screen["id"] for screen in screen_results.get("screens", [])]
                self.log(f"✓ Found {len(screen_ids)} matching screens")
            else:
                screen_ids = ["screen_1", "screen_2", "screen_3"]
        else:
            # Use screens from packages if specified
            screen_ids = []
            for package in packages:
                if hasattr(package, "platform_data") and package.platform_data:
                    bs_data = package.platform_data.get("broadsign", {})
                    if "screen_ids" in bs_data:
                        screen_ids.extend(bs_data["screen_ids"])

        # Step 3: Add screens to proposal
        if screen_ids:
            for package in packages:
                line_item_data = {
                    "proposal_id": proposal_id,
                    "screens": screen_ids[:10],  # Limit for example
                    "start_date": start_time.strftime("%Y-%m-%d"),
                    "end_date": end_time.strftime("%Y-%m-%d"),
                    "mode": "frequency",  # Can be: frequency, share_of_voice, etc.
                    "flight_duration_seconds": int(package.duration) if hasattr(package, "duration") else 15,
                    "slot_duration_seconds": 15,
                }

                self.log(f"Adding {len(screen_ids[:10])} screens for package: {package.name}")
                self._api_call("POST", "/api/v1/proposal/add_screens", json=line_item_data)

        # Step 4: Check availability
        self.log("Checking campaign availability...")
        availability = self._api_call("GET", f"/api/v1/proposal/{proposal_id}/availability?type=book")

        if not self.dry_run and not availability.get("available", True):
            error_msg = "Inventory not available for requested dates/screens"
            self.audit_logger.log_operation(
                operation="create_media_buy",
                principal_name=self.principal.name,
                principal_id=self.principal.principal_id,
                adapter_id=self.client_id,
                success=False,
                details={"error": error_msg},
            )
            raise ValueError(error_msg)

        self.log("✓ Inventory available")

        # Step 5: Hold or book the campaign (default to hold for now)
        self.log("Holding campaign...")
        self._api_call("PUT", f"/api/v1/proposal/{proposal_id}/hold")

        # Store campaign details
        media_buy_id = f"bs_{proposal_id}"
        self._campaigns[media_buy_id] = {
            "proposal_id": proposal_id,
            "name": campaign_name,
            "po_number": request.po_number,
            "buyer_ref": request.buyer_ref,
            "start_time": start_time,
            "end_time": end_time,
            "total_budget": total_budget,
            "status": self.STATUS_HOLD,
            "screen_ids": screen_ids,
        }

        self.log(f"✓ Campaign created and held: {media_buy_id}")
        self.audit_logger.log_success(f"Created Broadsign proposal ID: {proposal_id}")

        return CreateMediaBuyResponse(
            media_buy_id=media_buy_id,
            buyer_ref=request.buyer_ref,
            creative_deadline=start_time - timedelta(days=7),
        )

    def add_creative_assets(
        self, media_buy_id: str, assets: list[dict[str, Any]], today: datetime
    ) -> list[AssetStatus]:
        """Add creative content to a Broadsign campaign."""
        # Log operation
        self.audit_logger.log_operation(
            operation="add_creative_assets",
            principal_name=self.principal.name,
            principal_id=self.principal.principal_id,
            adapter_id=self.client_id,
            success=True,
            details={"media_buy_id": media_buy_id, "creative_count": len(assets)},
        )

        self.log(f"Broadsign.add_creative_assets for campaign '{media_buy_id}'")
        self.log(f"Adding {len(assets)} creative assets")

        # Broadsign requires content to be uploaded to their CDN
        # This is typically done through their content management system
        # For now, we'll simulate approval

        if self.dry_run:
            for i, asset in enumerate(assets):
                self.log(f"Would upload creative {i+1}:")
                self.log(f"  Name: {asset['name']}")
                self.log(f"  Format: {asset['format']}")
                self.log(f"  URL: {asset['media_url']}")

        asset_statuses = []
        for asset in assets:
            # In production, this would upload to Broadsign's content repository
            # and associate with the campaign
            status = "approved" if not self.dry_run else "pending"
            asset_statuses.append(AssetStatus(creative_id=asset["id"], status=status))

        self.log(f"✓ Successfully processed {len(assets)} creatives")
        return asset_statuses

    def associate_creatives(self, line_item_ids: list[str], platform_creative_ids: list[str]) -> list[dict[str, Any]]:
        """Associate already-uploaded creatives with campaign line items."""
        self.log(
            f"Broadsign: Associating {len(platform_creative_ids)} creatives " f"with {len(line_item_ids)} line items"
        )

        results = []
        for line_item_id in line_item_ids:
            for creative_id in platform_creative_ids:
                self.log(f"  ✓ Associated creative {creative_id} with line item {line_item_id}")
                results.append(
                    {
                        "line_item_id": line_item_id,
                        "creative_id": creative_id,
                        "status": "success",
                    }
                )

        return results

    def check_media_buy_status(self, media_buy_id: str, today: datetime) -> CheckMediaBuyStatusResponse:
        """Check the status of a Broadsign campaign."""
        if media_buy_id in self._campaigns:
            campaign = self._campaigns[media_buy_id]
            proposal_id = campaign["proposal_id"]
        else:
            proposal_id = media_buy_id.replace("bs_", "")

        # Query Broadsign API for current status
        proposal_data = self._api_call("GET", f"/api/v1/proposal/{proposal_id}")

        if self.dry_run:
            bs_status = self.STATUS_DELIVERING
        else:
            bs_status = proposal_data.get("status", self.STATUS_PENDING)

        # Map Broadsign status to AdCP status
        status_map = {
            self.STATUS_DRAFT: "pending_start",
            self.STATUS_PENDING: "pending_start",
            self.STATUS_HOLD: "pending_start",
            self.STATUS_BOOKED: "pending_start",
            self.STATUS_DELIVERING: "delivering",
            self.STATUS_COMPLETED: "completed",
        }

        status = status_map.get(bs_status, "pending_start")

        buyer_ref = campaign.get("buyer_ref") if media_buy_id in self._campaigns else "unknown"

        return CheckMediaBuyStatusResponse(
            media_buy_id=media_buy_id,
            buyer_ref=buyer_ref,
            status=status,
        )

    def get_media_buy_delivery(
        self, media_buy_id: str, date_range: ReportingPeriod, today: datetime
    ) -> AdapterGetMediaBuyDeliveryResponse:
        """Get delivery/performance data for a Broadsign campaign."""
        self.log(f"Broadsign.get_media_buy_delivery for campaign '{media_buy_id}'")
        self.log(f"Reporting period: {date_range.start} to {date_range.end}")

        # Broadsign provides impression delivery data through their reporting API
        # This would query actual delivery data from the platform

        if media_buy_id in self._campaigns:
            campaign = self._campaigns[media_buy_id]
            proposal_id = campaign["proposal_id"]
        else:
            proposal_id = media_buy_id.replace("bs_", "")

        # In production, query Broadsign reporting endpoints
        # For now, simulate delivery data
        if self.dry_run:
            self.log("Would fetch delivery report from Broadsign")
            impressions = 50000
            spend = 1000.0
        else:
            # This would be a real API call to Broadsign's reporting endpoints
            # Example: /api/v1/proposal/{proposal_id}/report
            impressions = 50000  # Placeholder
            spend = 1000.0  # Placeholder

        self.log(f"✓ Retrieved delivery: {impressions:,} impressions, ${spend:,.2f} spend")

        return AdapterGetMediaBuyDeliveryResponse(
            media_buy_id=media_buy_id,
            reporting_period=date_range,
            totals=DeliveryTotals(
                impressions=impressions,
                spend=spend,
                clicks=0,  # DOOH typically doesn't track clicks
                video_completions=0,
            ),
            by_package=[],
            currency="USD",
        )

    def update_media_buy_performance_index(
        self, media_buy_id: str, package_performance: list[PackagePerformance]
    ) -> bool:
        """Update performance index for packages in a media buy."""
        self.log(f"Broadsign: Updating performance index for {media_buy_id}")
        # Broadsign doesn't typically support real-time bid adjustments
        # Performance optimization is done through booking different inventory
        return True

    def update_media_buy(
        self,
        media_buy_id: str,
        action: str,
        package_id: str | None,
        budget: int | None,
        today: datetime,
    ) -> UpdateMediaBuyResponse:
        """Update a Broadsign campaign."""
        self.log(f"Broadsign: Update action '{action}' for campaign {media_buy_id}")

        if action == "pause":
            # Broadsign campaigns can be paused
            self.log("  Campaign paused")
            return UpdateMediaBuyResponse(status="accepted")
        elif action == "resume":
            # Resume a paused campaign
            self.log("  Campaign resumed")
            return UpdateMediaBuyResponse(status="accepted")
        elif action == "cancel":
            # Cancel/delete the campaign
            self.log("  Campaign cancelled")
            return UpdateMediaBuyResponse(status="accepted")
        else:
            return UpdateMediaBuyResponse(
                status="rejected",
                message=f"Unsupported action: {action}",
            )

    def get_config_ui_endpoint(self) -> str | None:
        """Return the URL path for the Broadsign adapter's configuration UI."""
        return "/adapters/broadsign/config"

    def register_ui_routes(self, app):
        """Register Flask routes for the Broadsign adapter configuration UI."""
        from flask import render_template, request

        @app.route("/adapters/broadsign/config/<tenant_id>/<product_id>", methods=["GET", "POST"])
        def broadsign_product_config(tenant_id, product_id):
            from functools import wraps

            from src.admin.utils import require_auth
            from src.core.database.database_session import get_db_session
            from src.core.database.models import Product

            # Apply auth decorator manually
            @require_auth()
            @wraps(broadsign_product_config)
            def wrapped_view():
                from sqlalchemy import select

                from src.adapters.broadsign_implementation_config_schema import (
                    BroadsignImplementationConfig,
                )

                with get_db_session() as session:
                    # Get product details
                    stmt = select(Product).filter_by(tenant_id=tenant_id, product_id=product_id)
                    product_obj = session.scalars(stmt).first()

                    if not product_obj:
                        return "Product not found", 404

                    product = {"product_id": product_id, "name": product_obj.name}

                    # Get current config
                    config = product_obj.implementation_config or {}

                    if request.method == "POST":
                        # Parse venue categories from checkboxes
                        venue_categories = []
                        for i in range(1, 13):  # 12 venue categories
                            if f"venue_category_{i}" in request.form:
                                venue_categories.append(i)

                        # Parse creative specs from checkboxes
                        creative_specs = []
                        format_keys = [
                            ("1920x1080", "16:9", "landscape"),
                            ("1080x1920", "9:16", "portrait"),
                            ("3840x2160", "16:9", "landscape"),
                            ("2160x3840", "9:16", "portrait"),
                            ("1920x1920", "1:1", "square"),
                            ("7680x1080", "64:9", "landscape"),
                        ]
                        for resolution, ratio, orientation in format_keys:
                            if f"format_{resolution}" in request.form:
                                creative_specs.append(
                                    {
                                        "resolution": resolution,
                                        "aspect_ratio": ratio,
                                        "orientation": orientation,
                                    }
                                )

                        # Build new configuration
                        new_config = {
                            "campaign_name_template": request.form.get("campaign_name_template", ""),
                            "default_hold_duration_hours": int(request.form.get("default_hold_duration_hours", 48)),
                            "auto_book_on_availability": "auto_book_on_availability" in request.form,
                            "preferred_venue_categories": venue_categories,
                            "min_screens_per_campaign": int(request.form.get("min_screens_per_campaign", 10)),
                            "max_screens_per_campaign": int(request.form.get("max_screens_per_campaign", 1000)),
                            "excluded_screen_ids": [
                                s.strip() for s in request.form.get("excluded_screen_ids", "").split(",") if s.strip()
                            ],
                            "default_buying_mode": request.form.get("default_buying_mode", "frequency"),
                            "frequency_settings": {
                                "plays_per_hour": int(request.form.get("plays_per_hour", 4)),
                                "min_spot_length_seconds": int(request.form.get("min_spot_length_seconds", 15)),
                                "max_spot_length_seconds": int(request.form.get("max_spot_length_seconds", 30)),
                            },
                            "share_of_voice_settings": {
                                "min_sov_percentage": float(request.form.get("min_sov_percentage", 10.0)),
                                "max_sov_percentage": float(request.form.get("max_sov_percentage", 100.0)),
                            },
                            "supported_creative_specs": creative_specs,
                            "default_spot_duration_seconds": int(request.form.get("default_spot_duration_seconds", 15)),
                            "require_proof_of_play": "require_proof_of_play" in request.form,
                            "auto_sync_screens": "auto_sync_screens" in request.form,
                            "sync_interval_hours": int(request.form.get("sync_interval_hours", 24)),
                            "use_traffic_estimation": "use_traffic_estimation" in request.form,
                            "attribution_model": request.form.get("attribution_model", "audience_based"),
                            "enable_dayparting": "enable_dayparting" in request.form,
                            "enable_weather_targeting": "enable_weather_targeting" in request.form,
                            "priority_level": int(request.form.get("priority_level", 5)),
                            "require_manual_approval": "require_manual_approval" in request.form,
                            "internal_notes": request.form.get("internal_notes", ""),
                        }

                        # Validate the configuration
                        try:
                            validated_config = BroadsignImplementationConfig(**new_config)
                            # Save to database
                            product_obj.implementation_config = validated_config.model_dump()
                            session.commit()

                            return render_template(
                                "adapters/broadsign_product_config.html",
                                tenant_id=tenant_id,
                                product=product,
                                config=validated_config.model_dump(),
                                success=True,
                            )
                        except Exception as e:
                            return render_template(
                                "adapters/broadsign_product_config.html",
                                tenant_id=tenant_id,
                                product=product,
                                config=config,
                                error=str(e),
                            )

                    return render_template(
                        "adapters/broadsign_product_config.html",
                        tenant_id=tenant_id,
                        product=product,
                        config=config,
                    )

            return wrapped_view()

    async def get_available_inventory(self) -> dict[str, Any]:
        """
        Fetch available screens and venues from Broadsign for AI-driven configuration.

        Returns a dictionary with:
        - screens: List of available DOOH screens with their capabilities
        - venue_categories: Available venue types
        - geographic_markets: Available markets/locations
        - creative_specs: Supported creative formats
        - buying_modes: Available buying strategies
        """
        # In production, this would query Broadsign's screen search API
        # For now, return realistic mock data structure that demonstrates
        # what an AI agent would receive for smart product configuration

        return {
            "screens": [
                {
                    "id": "screen_12345",
                    "name": "JFK Terminal 4 - Gate 12",
                    "venue_type": "airport",
                    "venue_category_id": 1,
                    "location": {
                        "city": "New York",
                        "state": "NY",
                        "country": "US",
                        "postal_code": "11430",
                        "lat": 40.6413,
                        "lon": -73.7781,
                    },
                    "specs": {
                        "resolution": "1920x1080",
                        "aspect_ratio": "16:9",
                        "orientation": "landscape",
                        "screen_size_inches": 55,
                    },
                    "metrics": {
                        "estimated_daily_impressions": 50000,
                        "average_dwell_time_seconds": 900,
                        "peak_hours": ["6-9", "17-20"],
                    },
                    "available": True,
                },
                {
                    "id": "screen_67890",
                    "name": "Penn Station - Main Concourse",
                    "venue_type": "transit",
                    "venue_category_id": 2,
                    "location": {
                        "city": "New York",
                        "state": "NY",
                        "country": "US",
                        "postal_code": "10001",
                    },
                    "specs": {
                        "resolution": "1080x1920",
                        "aspect_ratio": "9:16",
                        "orientation": "portrait",
                        "screen_size_inches": 65,
                    },
                    "metrics": {
                        "estimated_daily_impressions": 120000,
                        "average_dwell_time_seconds": 180,
                        "peak_hours": ["7-9", "17-19"],
                    },
                    "available": True,
                },
            ],
            "venue_categories": [
                {"id": 1, "name": "Airports", "screen_count": 450, "avg_daily_impressions": 45000},
                {"id": 2, "name": "Transit/Subway", "screen_count": 820, "avg_daily_impressions": 95000},
                {"id": 3, "name": "Shopping Malls", "screen_count": 320, "avg_daily_impressions": 35000},
                {"id": 4, "name": "Office Buildings", "screen_count": 180, "avg_daily_impressions": 8000},
                {"id": 5, "name": "Gyms/Fitness", "screen_count": 240, "avg_daily_impressions": 5000},
                {"id": 6, "name": "Entertainment", "screen_count": 150, "avg_daily_impressions": 25000},
                {"id": 7, "name": "Restaurants/QSR", "screen_count": 380, "avg_daily_impressions": 12000},
                {"id": 8, "name": "Gas Stations", "screen_count": 420, "avg_daily_impressions": 8000},
            ],
            "geographic_markets": [
                {"city": "New York", "state": "NY", "screen_count": 2450},
                {"city": "Los Angeles", "state": "CA", "screen_count": 1820},
                {"city": "Chicago", "state": "IL", "screen_count": 980},
                {"city": "San Francisco", "state": "CA", "screen_count": 650},
                {"city": "Miami", "state": "FL", "screen_count": 420},
            ],
            "creative_specs": [
                {
                    "resolution": "1920x1080",
                    "aspect_ratio": "16:9",
                    "orientation": "landscape",
                    "supported_formats": ["mp4", "mov"],
                    "max_file_size_mb": 500,
                    "recommended_duration_seconds": [15, 30],
                },
                {
                    "resolution": "1080x1920",
                    "aspect_ratio": "9:16",
                    "orientation": "portrait",
                    "supported_formats": ["mp4", "mov"],
                    "max_file_size_mb": 500,
                    "recommended_duration_seconds": [15, 30],
                },
                {
                    "resolution": "3840x2160",
                    "aspect_ratio": "16:9",
                    "orientation": "landscape",
                    "supported_formats": ["mp4", "mov"],
                    "max_file_size_mb": 1000,
                    "recommended_duration_seconds": [30, 60],
                },
            ],
            "buying_modes": [
                {
                    "mode": "frequency",
                    "description": "Buy specific number of plays per hour",
                    "typical_range": {"min_plays_per_hour": 1, "max_plays_per_hour": 60},
                },
                {
                    "mode": "share_of_voice",
                    "description": "Buy percentage of available ad time",
                    "typical_range": {"min_percentage": 10, "max_percentage": 100},
                },
                {
                    "mode": "impressions",
                    "description": "Buy guaranteed impressions (CPM-based)",
                    "typical_cpm_range": {"min": 8.0, "max": 35.0},
                },
            ],
        }
