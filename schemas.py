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

class TargetingCapability(BaseModel):
    """Defines targeting dimension capabilities and restrictions."""
    dimension: str  # e.g., "geo_country", "key_value"
    access: Literal["overlay", "managed_only", "both"] = "overlay"
    description: Optional[str] = None
    allowed_values: Optional[List[str]] = None  # For restricted value sets
    aee_signal: Optional[bool] = False  # Whether this is an AEE signal dimension

class Targeting(BaseModel):
    """Comprehensive targeting options for media buys.
    
    All fields are optional and can be combined for precise audience targeting.
    Platform adapters will map these to their specific targeting capabilities.
    Uses any_of/none_of pattern for consistent include/exclude across all dimensions.
    
    Note: Some targeting dimensions are managed-only and cannot be set via overlay.
    These are typically used for AEE signal integration.
    """
    # Geographic targeting - aligned with OpenRTB (overlay access)
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
    
    # Key-value targeting (managed-only for AEE signals)
    # These are not exposed in overlay - only set by orchestrator/AEE
    key_value_pairs: Optional[Dict[str, str]] = None  # e.g., {"aee_segment": "high_value", "aee_score": "0.85"}

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
    implementation_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Ad server-specific configuration for implementing this product (placements, line item settings, etc.)"
    )

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
class CreativeGroup(BaseModel):
    """Groups creatives for organizational and management purposes."""
    group_id: str
    principal_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    tags: Optional[List[str]] = []

class Creative(BaseModel):
    """Individual creative asset in the creative library."""
    creative_id: str
    principal_id: str
    group_id: Optional[str] = None  # Optional group membership
    format_id: str
    content_uri: str
    name: str
    click_through_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}  # Platform-specific metadata
    created_at: datetime
    updated_at: datetime

class CreativeStatus(BaseModel):
    creative_id: str
    status: Literal["pending_review", "approved", "rejected", "adaptation_required"]
    detail: str
    estimated_approval_time: Optional[datetime] = None

class CreativeAssignment(BaseModel):
    """Maps creatives to packages with distribution control."""
    assignment_id: str
    media_buy_id: str
    package_id: str
    creative_id: str
    
    # Distribution control
    weight: Optional[int] = 100  # Relative weight for rotation
    percentage_goal: Optional[float] = None  # Percentage of impressions
    rotation_type: Optional[Literal["weighted", "sequential", "even"]] = "weighted"
    
    # Override settings (platform-specific)
    override_click_url: Optional[str] = None
    override_start_date: Optional[datetime] = None
    override_end_date: Optional[datetime] = None
    
    # Targeting override (creative-specific targeting)
    targeting_overlay: Optional[Targeting] = None
    
    is_active: bool = True

class SubmitCreativesRequest(BaseModel):
    media_buy_id: str
    creatives: List[Creative]

class SubmitCreativesResponse(BaseModel):
    statuses: List[CreativeStatus]

class CheckCreativeStatusRequest(BaseModel):
    creative_ids: List[str]

class CheckCreativeStatusResponse(BaseModel):
    statuses: List[CreativeStatus]

# New creative management endpoints
class CreateCreativeGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = []

class CreateCreativeGroupResponse(BaseModel):
    group: CreativeGroup

class CreateCreativeRequest(BaseModel):
    """Create a creative in the library (not tied to a media buy)."""
    group_id: Optional[str] = None
    format_id: str
    content_uri: str
    name: str
    click_through_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}

class CreateCreativeResponse(BaseModel):
    creative: Creative
    status: CreativeStatus

class AssignCreativeRequest(BaseModel):
    """Assign a creative from the library to a package."""
    media_buy_id: str
    package_id: str
    creative_id: str
    weight: Optional[int] = 100
    percentage_goal: Optional[float] = None
    rotation_type: Optional[Literal["weighted", "sequential", "even"]] = "weighted"
    override_click_url: Optional[str] = None
    override_start_date: Optional[datetime] = None
    override_end_date: Optional[datetime] = None
    targeting_overlay: Optional[Targeting] = None

class AssignCreativeResponse(BaseModel):
    assignment: CreativeAssignment

class GetCreativesRequest(BaseModel):
    """Get creatives with optional filtering."""
    group_id: Optional[str] = None
    media_buy_id: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    include_assignments: bool = False

class GetCreativesResponse(BaseModel):
    creatives: List[Creative]
    assignments: Optional[List[CreativeAssignment]] = None

# Admin tools
class GetPendingCreativesRequest(BaseModel):
    """Admin-only: Get all pending creatives across all principals."""
    principal_id: Optional[str] = None  # Filter by principal if specified
    limit: Optional[int] = 100

class GetPendingCreativesResponse(BaseModel):
    pending_creatives: List[Dict[str, Any]]  # Includes creative + principal info

class ApproveCreativeRequest(BaseModel):
    """Admin-only: Approve or reject a creative."""
    creative_id: str
    action: Literal["approve", "reject"]
    reason: Optional[str] = None

class ApproveCreativeResponse(BaseModel):
    creative_id: str
    new_status: str
    detail: str

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


# --- Human-in-the-Loop Task Queue ---

class HumanTask(BaseModel):
    """Task requiring human intervention."""
    task_id: str
    task_type: str  # creative_approval, permission_exception, configuration_required, compliance_review, manual_approval
    principal_id: str
    adapter_name: Optional[str] = None
    status: str = "pending"  # pending, assigned, in_progress, completed, failed, escalated
    priority: str = "medium"  # low, medium, high, urgent
    
    # Context
    media_buy_id: Optional[str] = None
    creative_id: Optional[str] = None
    operation: Optional[str] = None
    error_detail: Optional[str] = None
    context_data: Optional[Dict[str, Any]] = None
    
    # Assignment
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    
    # Timing
    created_at: datetime
    updated_at: datetime
    due_by: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Resolution
    resolution: Optional[str] = None  # approved, rejected, completed, cannot_complete
    resolution_detail: Optional[str] = None
    resolved_by: Optional[str] = None


class CreateHumanTaskRequest(BaseModel):
    """Request to create a human task."""
    task_type: str
    priority: str = "medium"
    
    # Context
    media_buy_id: Optional[str] = None
    creative_id: Optional[str] = None
    operation: Optional[str] = None
    error_detail: Optional[str] = None
    context_data: Optional[Dict[str, Any]] = None
    
    # SLA
    due_in_hours: Optional[int] = None  # Hours until due


class CreateHumanTaskResponse(BaseModel):
    """Response from creating a human task."""
    task_id: str
    status: str
    due_by: Optional[datetime] = None
    
    
class GetPendingTasksRequest(BaseModel):
    """Request for pending human tasks."""
    principal_id: Optional[str] = None  # Filter by principal
    task_type: Optional[str] = None  # Filter by type
    priority: Optional[str] = None  # Filter by minimum priority
    assigned_to: Optional[str] = None  # Filter by assignee
    include_overdue: bool = True


class GetPendingTasksResponse(BaseModel):
    """Response with pending tasks."""
    tasks: List[HumanTask]
    total_count: int
    overdue_count: int


class AssignTaskRequest(BaseModel):
    """Request to assign a task."""
    task_id: str
    assigned_to: str
    
    
class CompleteTaskRequest(BaseModel):
    """Request to complete a task."""
    task_id: str
    resolution: str  # approved, rejected, completed, cannot_complete
    resolution_detail: Optional[str] = None
    resolved_by: str


class VerifyTaskRequest(BaseModel):
    """Request to verify if a task was completed correctly."""
    task_id: str
    expected_outcome: Optional[Dict[str, Any]] = None  # What the task should have accomplished
    

class VerifyTaskResponse(BaseModel):
    """Response from task verification."""
    task_id: str
    verified: bool
    actual_state: Dict[str, Any]
    expected_state: Optional[Dict[str, Any]] = None
    discrepancies: List[str] = []
    
    
class MarkTaskCompleteRequest(BaseModel):
    """Admin request to mark a task as complete with verification."""
    task_id: str
    override_verification: bool = False  # Force complete even if verification fails
    completed_by: str
