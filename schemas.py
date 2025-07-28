from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, date

# --- V2.3 Pydantic Models (Bearer Auth, Restored & Complete) ---

# --- Core Models ---
class DeliveryOptions(BaseModel):
    hosted: Optional[Dict[str, Any]] = None
    vast: Optional[Dict[str, Any]] = None

class Format(BaseModel):
    format_id: str
    name: str
    type: Literal["video", "audio", "display", "native", "dooh"]
    description: str
    specs: Dict[str, Any]
    delivery_options: DeliveryOptions

class DaypartSchedule(BaseModel):
    """Time-based targeting schedule."""
    days: List[int] = Field(..., description="Days of week (0=Sunday, 6=Saturday)")
    start_hour: int = Field(..., ge=0, le=23, description="Start hour (0-23)")
    end_hour: int = Field(..., ge=0, le=23, description="End hour (0-23)")
    timezone: Optional[str] = Field("UTC", description="Timezone for schedule")

class Dayparting(BaseModel):
    """Dayparting configuration for time-based targeting."""
    timezone: str = Field("UTC", description="Default timezone for all schedules")
    schedules: List[DaypartSchedule] = Field(..., description="List of time windows")
    # Special presets for audio
    presets: Optional[List[str]] = Field(None, description="Named presets like 'drive_time_morning'")

class FrequencyCap(BaseModel):
    """Simple frequency capping configuration.
    
    Provides basic impression suppression at the media buy or package level.
    More sophisticated frequency management is handled by the AEE layer.
    """
    suppress_minutes: int = Field(..., gt=0, description="Suppress impressions for this many minutes after serving")
    scope: Literal["media_buy", "package"] = Field("media_buy", description="Apply at media buy or package level")

class Targeting(BaseModel):
    """Comprehensive targeting options for media buys.
    
    All fields are optional and can be combined for precise audience targeting.
    Platform adapters will map these to their specific targeting capabilities.
    Uses any_of/none_of pattern for consistent include/exclude across all dimensions.
    """
    # Geographic targeting - aligned with OpenRTB
    geo_country_any_of: Optional[List[str]] = None  # ISO country codes: ["US", "CA", "GB"]
    geo_country_none_of: Optional[List[str]] = None
    
    geo_region_any_of: Optional[List[str]] = None  # Region codes: ["NY", "CA", "ON"]
    geo_region_none_of: Optional[List[str]] = None
    
    geo_metro_any_of: Optional[List[str]] = None  # Metro/DMA codes: ["501", "803"]
    geo_metro_none_of: Optional[List[str]] = None
    
    geo_city_any_of: Optional[List[str]] = None  # City names: ["New York", "Los Angeles"]
    geo_city_none_of: Optional[List[str]] = None
    
    geo_zip_any_of: Optional[List[str]] = None  # Postal codes: ["10001", "90210"]
    geo_zip_none_of: Optional[List[str]] = None
    
    # Device and platform targeting
    device_type_any_of: Optional[List[str]] = None  # ["mobile", "desktop", "tablet", "ctv", "audio", "dooh"]
    device_type_none_of: Optional[List[str]] = None
    
    os_any_of: Optional[List[str]] = None  # Operating systems: ["iOS", "Android", "Windows"]
    os_none_of: Optional[List[str]] = None
    
    browser_any_of: Optional[List[str]] = None  # Browsers: ["Chrome", "Safari", "Firefox"]
    browser_none_of: Optional[List[str]] = None
    
    # Content and contextual targeting
    content_cat_any_of: Optional[List[str]] = None  # IAB content categories
    content_cat_none_of: Optional[List[str]] = None
    
    keywords_any_of: Optional[List[str]] = None  # Keyword targeting
    keywords_none_of: Optional[List[str]] = None
    
    # Audience targeting
    audiences_any_of: Optional[List[str]] = None  # Audience segments
    audiences_none_of: Optional[List[str]] = None
    
    # Media type targeting
    media_type_any_of: Optional[List[str]] = None  # ["video", "audio", "display", "native"]
    media_type_none_of: Optional[List[str]] = None
    
    # Time-based targeting
    dayparting: Optional[Dayparting] = None  # Schedule by day of week and hour
    
    # Frequency control
    frequency_cap: Optional[FrequencyCap] = None  # Impression limits per user/period
    
    # Connection type targeting
    connection_type_any_of: Optional[List[int]] = None  # OpenRTB connection types
    connection_type_none_of: Optional[List[int]] = None
    
    # Platform-specific custom targeting
    custom: Optional[Dict[str, Any]] = None  # Platform-specific targeting options

class PriceGuidance(BaseModel):
    floor: float
    p25: Optional[float] = None
    p50: Optional[float] = None
    p75: Optional[float] = None
    p90: Optional[float] = None

class Product(BaseModel):
    product_id: str
    name: str
    description: str
    formats: List[Format]
    targeting_template: Targeting
    delivery_type: Literal["guaranteed", "non_guaranteed"]
    is_fixed_price: bool
    cpm: Optional[float] = None
    price_guidance: Optional[PriceGuidance] = None
    is_custom: bool = Field(default=False)
    expires_at: Optional[datetime] = None

# --- Admin Tool Schemas ---
class PrincipalSummary(BaseModel):
    principal_id: str
    name: str
    platform_mappings: Dict[str, Any]
    live_media_buys: int
    total_spend: float

class GetPrincipalSummaryResponse(BaseModel):
    principals: List[PrincipalSummary]

class Principal(BaseModel):
    """Principal object containing authentication and adapter mapping information."""
    principal_id: str
    name: str
    platform_mappings: Dict[str, Any]
    
    def get_adapter_id(self, adapter_name: str) -> Optional[str]:
        """Get the adapter-specific ID for this principal."""
        adapter_field_map = {
            "gam": "gam_advertiser_id",
            "kevel": "kevel_advertiser_id", 
            "triton": "triton_advertiser_id",
            "mock": "mock_advertiser_id"
        }
        field_name = adapter_field_map.get(adapter_name)
        if field_name and field_name in self.platform_mappings:
            return str(self.platform_mappings[field_name]) if self.platform_mappings[field_name] else None
        return None

# --- Performance Index ---
class ProductPerformance(BaseModel):
    product_id: str
    performance_index: float  # 1.0 = baseline, 1.2 = 20% better, 0.8 = 20% worse
    confidence_score: Optional[float] = None  # 0.0 to 1.0

class UpdatePerformanceIndexRequest(BaseModel):
    media_buy_id: str
    performance_data: List[ProductPerformance]

class UpdatePerformanceIndexResponse(BaseModel):
    status: str
    detail: str

# --- Discovery ---
class ListProductsRequest(BaseModel):
    brief: str

class ListProductsResponse(BaseModel):
    products: List[Product]

# --- Creative Lifecycle ---
class Creative(BaseModel):
    creative_id: str
    format_id: str
    content_uri: str

class CreativeStatus(BaseModel):
    creative_id: str
    status: Literal["pending_review", "approved", "rejected", "adaptation_required"]
    detail: str
    estimated_approval_time: Optional[datetime] = None

class SubmitCreativesRequest(BaseModel):
    media_buy_id: str
    creatives: List[Creative]

class SubmitCreativesResponse(BaseModel):
    statuses: List[CreativeStatus]

class CheckCreativeStatusRequest(BaseModel):
    creative_ids: List[str]

class CheckCreativeStatusResponse(BaseModel):
    statuses: List[CreativeStatus]

class AdaptCreativeRequest(BaseModel):
    media_buy_id: str
    original_creative_id: str
    target_format_id: str
    new_creative_id: str
    instructions: Optional[str] = None

# --- Media Buy Lifecycle ---
class CreateMediaBuyRequest(BaseModel):
    product_ids: List[str]
    flight_start_date: date
    flight_end_date: date
    total_budget: float
    targeting_overlay: Targeting
    po_number: Optional[str] = None
    pacing: Literal["even", "asap", "daily_budget"] = "even"
    daily_budget: Optional[float] = None
    creatives: Optional[List[Creative]] = None

class CreateMediaBuyResponse(BaseModel):
    media_buy_id: str
    status: str
    detail: str
    creative_deadline: Optional[datetime] = None

class LegacyUpdateMediaBuyRequest(BaseModel):
    """Legacy update request - kept for backward compatibility."""
    media_buy_id: str
    new_total_budget: Optional[float] = None
    new_targeting_overlay: Optional[Targeting] = None
    creative_assignments: Optional[Dict[str, List[str]]] = None

class GetMediaBuyDeliveryRequest(BaseModel):
    media_buy_id: str
    today: date

class GetMediaBuyDeliveryResponse(BaseModel):
    media_buy_id: str
    status: str
    spend: float
    impressions: int
    pacing: str
    days_elapsed: int
    total_days: int

class GetAllMediaBuyDeliveryRequest(BaseModel):
    """Request delivery data for all active media buys owned by the principal."""
    today: date
    media_buy_ids: Optional[List[str]] = None  # If provided, only fetch these specific buys

class GetAllMediaBuyDeliveryResponse(BaseModel):
    """Bulk response containing delivery data for multiple media buys."""
    deliveries: List[GetMediaBuyDeliveryResponse]
    total_spend: float
    total_impressions: int
    active_count: int
    summary_date: date

# --- Additional Schema Classes ---
class MediaPackage(BaseModel):
    package_id: str
    name: str
    delivery_type: Literal["guaranteed", "non_guaranteed"]
    cpm: float
    impressions: int
    format_ids: List[str]

class ReportingPeriod(BaseModel):
    start: datetime
    end: datetime
    start_date: Optional[date] = None  # For compatibility
    end_date: Optional[date] = None  # For compatibility

class DeliveryTotals(BaseModel):
    impressions: int
    spend: float
    clicks: Optional[int] = 0
    video_completions: Optional[int] = 0

class PackagePerformance(BaseModel):
    package_id: str
    performance_index: float

class AssetStatus(BaseModel):
    creative_id: str
    status: str

class CheckMediaBuyStatusResponse(BaseModel):
    media_buy_id: str
    status: str
    last_updated: Optional[datetime] = None

class UpdateMediaBuyResponse(BaseModel):
    status: str
    implementation_date: Optional[datetime] = None
    reason: Optional[str] = None
    detail: Optional[str] = None

# Unified update models
class PackageUpdate(BaseModel):
    """Updates to apply to a specific package."""
    package_id: str
    active: Optional[bool] = None  # True to activate, False to pause
    budget: Optional[float] = None  # New budget in dollars
    impressions: Optional[int] = None  # Direct impression goal (overrides budget calculation)
    cpm: Optional[float] = None  # Update CPM rate
    daily_budget: Optional[float] = None  # Daily spend cap
    daily_impressions: Optional[int] = None  # Daily impression cap
    pacing: Optional[Literal["even", "asap", "front_loaded"]] = None
    creative_ids: Optional[List[str]] = None  # Update creative assignments
    targeting_overlay: Optional[Targeting] = None  # Package-specific targeting refinements
    
    
class UpdatePackageRequest(BaseModel):
    """Update one or more packages within a media buy.
    
    Uses PATCH semantics: Only packages mentioned are affected.
    Omitted packages remain unchanged.
    To remove a package from delivery, set active=false.
    To add new packages, use create_media_buy or add_packages (future tool).
    """
    media_buy_id: str
    packages: List[PackageUpdate]  # List of package updates
    today: Optional[date] = None  # For testing/simulation
    
class UpdateMediaBuyRequest(BaseModel):
    """Update a media buy - mirrors CreateMediaBuyRequest structure.
    
    Uses PATCH semantics: Only fields provided are updated.
    Package updates only affect packages explicitly mentioned.
    To pause all packages, set active=false at campaign level.
    To pause specific packages, include them in packages list with active=false.
    """
    media_buy_id: str
    # Campaign-level updates
    active: Optional[bool] = None  # True to activate, False to pause entire campaign
    flight_start_date: Optional[date] = None  # Change start date (if not started)
    flight_end_date: Optional[date] = None  # Extend or shorten campaign
    total_budget: Optional[float] = None  # Update total budget
    targeting_overlay: Optional[Targeting] = None  # Update global targeting
    pacing: Optional[Literal["even", "asap", "daily_budget"]] = None
    daily_budget: Optional[float] = None  # Daily spend cap across all packages
    # Package-level updates
    packages: Optional[List[PackageUpdate]] = None  # Package-specific updates (only these are affected)
    # Creative updates
    creatives: Optional[List[Creative]] = None  # Add new creatives
    creative_assignments: Optional[Dict[str, List[str]]] = None  # Update creative-to-package mapping
    today: Optional[date] = None  # For testing/simulation

# Adapter-specific response schemas
class PackageDelivery(BaseModel):
    package_id: str
    impressions: int
    spend: float

class AdapterGetMediaBuyDeliveryResponse(BaseModel):
    """Response from adapter's get_media_buy_delivery method"""
    media_buy_id: str
    reporting_period: ReportingPeriod
    totals: DeliveryTotals
    by_package: List[PackageDelivery]
    currency: str
