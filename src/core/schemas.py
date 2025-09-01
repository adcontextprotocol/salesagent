import uuid
from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# --- V2.3 Pydantic Models (Bearer Auth, Restored & Complete) ---


# --- Core Models ---
class AssetRequirement(BaseModel):
    """Asset requirement specification per AdCP spec."""

    asset_type: str = Field(..., description="Type of asset required")
    quantity: int = Field(1, minimum=1, description="Number of assets of this type required")
    requirements: dict[str, Any] | None = Field(None, description="Specific requirements for this asset type")


class Format(BaseModel):
    format_id: str
    name: str
    type: Literal["video", "audio", "display", "native", "dooh"]  # Extended beyond spec
    is_standard: bool | None = Field(None, description="Whether this follows IAB standards")
    iab_specification: str | None = Field(None, description="Name of the IAB specification (if applicable)")
    requirements: dict[str, Any] | None = Field(
        None, description="Format-specific requirements (varies by format type)"
    )
    assets_required: list[AssetRequirement] | None = Field(
        None, description="Array of required assets for composite formats"
    )


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
    description: str | None = None
    allowed_values: list[str] | None = None  # For restricted value sets
    aee_signal: bool | None = False  # Whether this is an AEE signal dimension


class Targeting(BaseModel):
    """Comprehensive targeting options for media buys.

    All fields are optional and can be combined for precise audience targeting.
    Platform adapters will map these to their specific targeting capabilities.
    Uses any_of/none_of pattern for consistent include/exclude across all dimensions.

    Note: Some targeting dimensions are managed-only and cannot be set via overlay.
    These are typically used for AEE signal integration.
    """

    # Geographic targeting - aligned with OpenRTB (overlay access)
    geo_country_any_of: list[str] | None = None  # ISO country codes: ["US", "CA", "GB"]
    geo_country_none_of: list[str] | None = None

    geo_region_any_of: list[str] | None = None  # Region codes: ["NY", "CA", "ON"]
    geo_region_none_of: list[str] | None = None

    geo_metro_any_of: list[str] | None = None  # Metro/DMA codes: ["501", "803"]
    geo_metro_none_of: list[str] | None = None

    geo_city_any_of: list[str] | None = None  # City names: ["New York", "Los Angeles"]
    geo_city_none_of: list[str] | None = None

    geo_zip_any_of: list[str] | None = None  # Postal codes: ["10001", "90210"]
    geo_zip_none_of: list[str] | None = None

    # Device and platform targeting
    device_type_any_of: list[str] | None = None  # ["mobile", "desktop", "tablet", "ctv", "audio", "dooh"]
    device_type_none_of: list[str] | None = None

    os_any_of: list[str] | None = None  # Operating systems: ["iOS", "Android", "Windows"]
    os_none_of: list[str] | None = None

    browser_any_of: list[str] | None = None  # Browsers: ["Chrome", "Safari", "Firefox"]
    browser_none_of: list[str] | None = None

    # Content and contextual targeting
    content_cat_any_of: list[str] | None = None  # IAB content categories
    content_cat_none_of: list[str] | None = None

    keywords_any_of: list[str] | None = None  # Keyword targeting
    keywords_none_of: list[str] | None = None

    # Audience targeting
    audiences_any_of: list[str] | None = None  # Audience segments
    audiences_none_of: list[str] | None = None

    # Signal targeting - can use signal IDs from get_signals endpoint
    signals: list[str] | None = None  # Signal IDs like ["auto_intenders_q1_2025", "sports_content"]

    # Media type targeting
    media_type_any_of: list[str] | None = None  # ["video", "audio", "display", "native"]
    media_type_none_of: list[str] | None = None

    # Frequency control
    frequency_cap: FrequencyCap | None = None  # Impression limits per user/period

    # Connection type targeting
    connection_type_any_of: list[int] | None = None  # OpenRTB connection types
    connection_type_none_of: list[int] | None = None

    # Platform-specific custom targeting
    custom: dict[str, Any] | None = None  # Platform-specific targeting options

    # Key-value targeting (managed-only for AEE signals)
    # These are not exposed in overlay - only set by orchestrator/AEE
    key_value_pairs: dict[str, str] | None = None  # e.g., {"aee_segment": "high_value", "aee_score": "0.85"}

    def model_dump(self, **kwargs):
        """Override model_dump to always exclude key_value_pairs from client responses."""
        kwargs["exclude"] = kwargs.get("exclude", set())
        if isinstance(kwargs["exclude"], set):
            kwargs["exclude"].add("key_value_pairs")
        return super().model_dump(**kwargs)

    def dict(self, **kwargs):
        """Override dict to always exclude key_value_pairs (for backward compat)."""
        kwargs["exclude"] = kwargs.get("exclude", set())
        if isinstance(kwargs["exclude"], set):
            kwargs["exclude"].add("key_value_pairs")
        return super().dict(**kwargs)


class Budget(BaseModel):
    """Budget object with multi-currency support."""

    total: float = Field(..., description="Total budget amount")
    currency: str = Field(..., description="ISO 4217 currency code (e.g., 'USD', 'EUR')")
    daily_cap: float | None = Field(None, description="Optional daily spending limit")
    pacing: Literal["even", "asap", "daily_budget"] = Field("even", description="Budget pacing strategy")


class Product(BaseModel):
    product_id: str
    name: str
    description: str
    formats: list[Format]
    delivery_type: Literal["guaranteed", "non_guaranteed"]
    is_fixed_price: bool
    cpm: float | None = None
    is_custom: bool = Field(default=False)
    expires_at: datetime | None = None
    implementation_config: dict[str, Any] | None = Field(
        default=None,
        description="Ad server-specific configuration for implementing this product (placements, line item settings, etc.)",
    )

    def model_dump(self, **kwargs):
        """Override model_dump to always exclude implementation_config."""
        kwargs["exclude"] = kwargs.get("exclude", set())
        if isinstance(kwargs["exclude"], set):
            kwargs["exclude"].add("implementation_config")
        return super().model_dump(**kwargs)

    def dict(self, **kwargs):
        """Override dict to always exclude implementation_config (for backward compat)."""
        kwargs["exclude"] = kwargs.get("exclude", set())
        if isinstance(kwargs["exclude"], set):
            kwargs["exclude"].add("implementation_config")
        return super().dict(**kwargs)


# --- Core Schemas ---


class Principal(BaseModel):
    """Principal object containing authentication and adapter mapping information."""

    principal_id: str
    name: str
    platform_mappings: dict[str, Any]

    def get_adapter_id(self, adapter_name: str) -> str | None:
        """Get the adapter-specific ID for this principal."""
        # Map adapter short names to platform keys
        adapter_platform_map = {
            "gam": "google_ad_manager",
            "google_ad_manager": "google_ad_manager",
            "kevel": "kevel",
            "triton": "triton",
            "mock": "mock",
        }

        platform_key = adapter_platform_map.get(adapter_name)
        if not platform_key:
            return None

        platform_data = self.platform_mappings.get(platform_key, {})
        if isinstance(platform_data, dict):
            # Try common field names for advertiser ID
            for field in ["advertiser_id", "id", "company_id"]:
                if field in platform_data:
                    return str(platform_data[field]) if platform_data[field] else None

        # Fallback to old format for backwards compatibility
        old_field_map = {
            "gam": "gam_advertiser_id",
            "kevel": "kevel_advertiser_id",
            "triton": "triton_advertiser_id",
            "mock": "mock_advertiser_id",
        }
        old_field = old_field_map.get(adapter_name)
        if old_field and old_field in self.platform_mappings:
            return str(self.platform_mappings[old_field]) if self.platform_mappings[old_field] else None

        return None


# --- Performance Index ---
class ProductPerformance(BaseModel):
    product_id: str
    performance_index: float  # 1.0 = baseline, 1.2 = 20% better, 0.8 = 20% worse
    confidence_score: float | None = None  # 0.0 to 1.0


class UpdatePerformanceIndexRequest(BaseModel):
    media_buy_id: str
    performance_data: list[ProductPerformance]


class UpdatePerformanceIndexResponse(BaseModel):
    status: str
    detail: str


# --- Discovery ---
class GetProductsRequest(BaseModel):
    brief: str
    promoted_offering: str = Field(
        ...,
        description="Description of the advertiser and the product or service being promoted (REQUIRED per AdCP spec)",
    )
    strategy_id: str | None = Field(
        None,
        description="Optional strategy ID for linking operations and enabling simulation/testing modes",
    )


class Error(BaseModel):
    """Standard error structure per AdCP spec."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(None, description="Additional error details")


class GetProductsResponse(BaseModel):
    """AdCP spec compliant response for get_products."""

    products: list[Product]
    message: str | None = Field(None, description="Human-readable summary of the response")
    context_id: str | None = Field(None, description="Session continuity identifier")
    clarification_needed: bool | None = Field(None, description="Whether clarification is needed")
    errors: list[Error] | None = Field(None, description="Non-fatal warnings")

    def model_dump(self, **kwargs):
        """Override to ensure products exclude implementation_config."""
        data = super().model_dump(**kwargs)
        # Ensure each product excludes implementation_config
        if "products" in data:
            for product in data["products"]:
                if "implementation_config" in product:
                    del product["implementation_config"]
        return data


class ListCreativeFormatsResponse(BaseModel):
    """Response for list_creative_formats (AdCP spec compliant)."""

    formats: list[Format]
    message: str | None = Field(None, description="Human-readable summary of available formats")
    context_id: str | None = Field(None, description="Session continuity identifier")


# --- Creative Lifecycle ---
class CreativeGroup(BaseModel):
    """Groups creatives for organizational and management purposes."""

    group_id: str
    principal_id: str
    name: str
    description: str | None = None
    created_at: datetime
    tags: list[str] | None = []


class Creative(BaseModel):
    """Individual creative asset in the creative library."""

    creative_id: str
    principal_id: str
    group_id: str | None = None  # Optional group membership

    # AdCP spec compliant fields (new names)
    format: str = Field(alias="format_id", description="Creative format type per AdCP spec")
    url: str = Field(alias="content_uri", description="URL of the creative content per AdCP spec")
    click_url: str | None = Field(None, alias="click_through_url", description="Landing page URL per AdCP spec")

    name: str
    metadata: dict[str, Any] | None = {}  # Platform-specific metadata
    created_at: datetime
    updated_at: datetime

    # Macro information
    has_macros: bool | None = False
    macro_validation: dict[str, Any] | None = None  # Validation result from creative_macros

    # Asset mapping - maps asset_id to uploaded content
    asset_mapping: dict[str, str] | None = Field(
        default_factory=dict, description="Maps asset_id from format definition to actual uploaded content URIs"
    )

    # Backward compatibility properties
    @property
    def format_id(self) -> str:
        """Backward compatibility for format_id."""
        return self.format

    @property
    def content_uri(self) -> str:
        """Backward compatibility for content_uri."""
        return self.url

    @property
    def click_through_url(self) -> str | None:
        """Backward compatibility for click_through_url."""
        return self.click_url

    def model_dump(self, **kwargs):
        """Override to support both field names based on context."""
        # For AdCP spec compliance, use new field names
        data = super().model_dump(**kwargs)
        # Remove aliases from output - clients will see spec-compliant names
        return data


class CreativeAdaptation(BaseModel):
    """Suggested adaptation or variant of a creative."""

    adaptation_id: str
    format_id: str
    name: str
    description: str
    preview_url: str | None = None
    changes_summary: list[str] = Field(default_factory=list)
    rationale: str | None = None
    estimated_performance_lift: float | None = None  # Percentage improvement expected


class CreativeStatus(BaseModel):
    creative_id: str
    status: Literal["pending_review", "approved", "rejected", "adaptation_required"]
    detail: str
    estimated_approval_time: datetime | None = None
    suggested_adaptations: list[CreativeAdaptation] = Field(default_factory=list)


class CreativeAssignment(BaseModel):
    """Maps creatives to packages with distribution control."""

    assignment_id: str
    media_buy_id: str
    package_id: str
    creative_id: str

    # Distribution control
    weight: int | None = 100  # Relative weight for rotation
    percentage_goal: float | None = None  # Percentage of impressions
    rotation_type: Literal["weighted", "sequential", "even"] | None = "weighted"

    # Override settings (platform-specific)
    override_click_url: str | None = None
    override_start_date: datetime | None = None
    override_end_date: datetime | None = None

    # Targeting override (creative-specific targeting)
    targeting_overlay: Targeting | None = None

    is_active: bool = True


class AddCreativeAssetsRequest(BaseModel):
    """Request to add creative assets to a media buy (AdCP spec compliant)."""

    media_buy_id: str | None = None
    buyer_ref: str | None = None
    assets: list[Creative]  # Renamed from 'creatives' to match spec

    def model_validate(cls, values):
        # Ensure at least one of media_buy_id or buyer_ref is provided
        if not values.get("media_buy_id") and not values.get("buyer_ref"):
            raise ValueError("Either media_buy_id or buyer_ref must be provided")
        return values

    # Backward compatibility
    @property
    def creatives(self) -> list[Creative]:
        """Backward compatibility for existing code."""
        return self.assets


class AddCreativeAssetsResponse(BaseModel):
    """Response from adding creative assets (AdCP spec compliant)."""

    statuses: list[CreativeStatus]


# Legacy aliases for backward compatibility (to be removed)
SubmitCreativesRequest = AddCreativeAssetsRequest
SubmitCreativesResponse = AddCreativeAssetsResponse


class CheckCreativeStatusRequest(BaseModel):
    creative_ids: list[str]


class CheckCreativeStatusResponse(BaseModel):
    statuses: list[CreativeStatus]


# New creative management endpoints
class CreateCreativeGroupRequest(BaseModel):
    name: str
    description: str | None = None
    tags: list[str] | None = []


class CreateCreativeGroupResponse(BaseModel):
    group: CreativeGroup


class CreateCreativeRequest(BaseModel):
    """Create a creative in the library (not tied to a media buy)."""

    group_id: str | None = None
    format_id: str
    content_uri: str
    name: str
    click_through_url: str | None = None
    metadata: dict[str, Any] | None = {}


class CreateCreativeResponse(BaseModel):
    creative: Creative
    status: CreativeStatus
    suggested_adaptations: list[CreativeAdaptation] = Field(default_factory=list)


class AssignCreativeRequest(BaseModel):
    """Assign a creative from the library to a package."""

    media_buy_id: str
    package_id: str
    creative_id: str
    weight: int | None = 100
    percentage_goal: float | None = None
    rotation_type: Literal["weighted", "sequential", "even"] | None = "weighted"
    override_click_url: str | None = None
    override_start_date: datetime | None = None
    override_end_date: datetime | None = None
    targeting_overlay: Targeting | None = None


class AssignCreativeResponse(BaseModel):
    assignment: CreativeAssignment


class GetCreativesRequest(BaseModel):
    """Get creatives with optional filtering."""

    group_id: str | None = None
    media_buy_id: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    include_assignments: bool = False


class GetCreativesResponse(BaseModel):
    creatives: list[Creative]
    assignments: list[CreativeAssignment] | None = None


# Admin tools
class GetPendingCreativesRequest(BaseModel):
    """Admin-only: Get all pending creatives across all principals."""

    principal_id: str | None = None  # Filter by principal if specified
    limit: int | None = 100


class GetPendingCreativesResponse(BaseModel):
    pending_creatives: list[dict[str, Any]]  # Includes creative + principal info


class ApproveCreativeRequest(BaseModel):
    """Admin-only: Approve or reject a creative."""

    creative_id: str
    action: Literal["approve", "reject"]
    reason: str | None = None


class ApproveCreativeResponse(BaseModel):
    creative_id: str
    new_status: str
    detail: str


class AdaptCreativeRequest(BaseModel):
    media_buy_id: str
    original_creative_id: str
    target_format_id: str
    new_creative_id: str
    instructions: str | None = None


class Package(BaseModel):
    """Package object with buyer reference and product arrays."""

    buyer_ref: str = Field(..., description="Buyer reference for tracking")
    products: list[str] = Field(..., description="Array of product IDs in this package")
    budget: Budget | None = Field(None, description="Optional package-specific budget")
    targeting_overlay: Targeting | None = Field(None, description="Package-specific targeting")


# --- Media Buy Lifecycle ---
class CreateMediaBuyRequest(BaseModel):
    # New AdCP v2.4 fields (optional for backward compatibility)
    buyer_ref: str | None = Field(None, description="Buyer reference for tracking")
    packages: list[Package] | None = Field(None, description="Array of packages with products and budgets")
    start_time: datetime | None = Field(None, description="Campaign start time (ISO 8601)")
    end_time: datetime | None = Field(None, description="Campaign end time (ISO 8601)")
    budget: Budget | None = Field(None, description="Overall campaign budget")

    # Legacy fields (for backward compatibility)
    product_ids: list[str] | None = Field(None, description="Legacy: Product IDs (converted to packages)")
    start_date: date | None = Field(None, description="Legacy: Start date (converted to start_time)")
    end_date: date | None = Field(None, description="Legacy: End date (converted to end_time)")
    total_budget: float | None = Field(None, description="Legacy: Total budget (converted to Budget object)")

    # Common fields
    targeting_overlay: Targeting | None = None
    po_number: str = Field(..., description="Purchase order number for tracking (REQUIRED per AdCP spec)")
    pacing: Literal["even", "asap", "daily_budget"] = "even"  # Legacy field
    daily_budget: float | None = None  # Legacy field
    creatives: list[Creative] | None = None
    # AEE signal requirements
    required_aee_signals: list[str] | None = None  # Required targeting signals
    enable_creative_macro: bool | None = False  # Enable AEE to provide creative_macro signal
    strategy_id: str | None = Field(
        None,
        description="Optional strategy ID for linking operations and enabling simulation/testing modes",
    )

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_format(cls, values):
        """Convert legacy format to new format."""
        if not isinstance(values, dict):
            return values

        # If using legacy format, convert to new format
        if "product_ids" in values and not values.get("packages"):
            # Generate buyer_ref if not provided
            if not values.get("buyer_ref"):
                values["buyer_ref"] = f"buy_{uuid.uuid4().hex[:8]}"

            # Convert product_ids to packages
            product_ids = values.get("product_ids", [])
            packages = []
            for i, pid in enumerate(product_ids):
                packages.append({"buyer_ref": f"pkg_{i}_{uuid.uuid4().hex[:6]}", "products": [pid]})
            values["packages"] = packages

        # Convert dates to datetimes
        if "start_date" in values and not values.get("start_time"):
            start_date = values["start_date"]
            if isinstance(start_date, str):
                start_date = date.fromisoformat(start_date)
            values["start_time"] = datetime.combine(start_date, time.min)

        if "end_date" in values and not values.get("end_time"):
            end_date = values["end_date"]
            if isinstance(end_date, str):
                end_date = date.fromisoformat(end_date)
            values["end_time"] = datetime.combine(end_date, time.max)

        # Convert total_budget to Budget object
        if "total_budget" in values and not values.get("budget"):
            total_budget = values["total_budget"]
            pacing = values.get("pacing", "even")
            daily_cap = values.get("daily_budget")

            values["budget"] = {
                "total": total_budget,
                "currency": "USD",  # Default currency
                "pacing": pacing,
                "daily_cap": daily_cap,
            }

        # Ensure required fields are present after conversion
        if not values.get("buyer_ref"):
            values["buyer_ref"] = f"buy_{uuid.uuid4().hex[:8]}"

        return values

    # Backward compatibility properties for old field names
    @property
    def flight_start_date(self) -> date:
        """Backward compatibility for old field name."""
        return self.start_time.date() if self.start_time else None

    @property
    def flight_end_date(self) -> date:
        """Backward compatibility for old field name."""
        return self.end_time.date() if self.end_time else None

    def get_total_budget(self) -> float:
        """Get total budget, handling both new and legacy formats."""
        if self.budget:
            return self.budget.total
        return self.total_budget or 0.0

    def get_product_ids(self) -> list[str]:
        """Extract all product IDs from packages for backward compatibility."""
        if self.packages:
            product_ids = []
            for package in self.packages:
                product_ids.extend(package.products)
            return product_ids
        return self.product_ids or []


class CreateMediaBuyResponse(BaseModel):
    media_buy_id: str
    buyer_ref: str
    packages: list[dict[str, Any]] = Field(default_factory=list, description="Created packages with IDs")
    creative_deadline: datetime | None = None


class CheckMediaBuyStatusRequest(BaseModel):
    media_buy_id: str | None = None
    buyer_ref: str | None = None
    strategy_id: str | None = Field(
        None,
        description="Optional strategy ID for consistent simulation/testing context",
    )

    def model_validate(cls, values):
        # Ensure at least one of media_buy_id or buyer_ref is provided
        if not values.get("media_buy_id") and not values.get("buyer_ref"):
            raise ValueError("Either media_buy_id or buyer_ref must be provided")
        return values


class CheckMediaBuyStatusResponse(BaseModel):
    media_buy_id: str
    buyer_ref: str
    status: str  # pending_creative, active, paused, completed, failed
    packages: list[dict[str, Any]] | None = None
    budget_spent: Budget | None = None
    budget_remaining: Budget | None = None
    creative_count: int = 0


class LegacyUpdateMediaBuyRequest(BaseModel):
    """Legacy update request - kept for backward compatibility."""

    media_buy_id: str
    new_budget: float | None = None
    new_targeting_overlay: Targeting | None = None
    creative_assignments: dict[str, list[str]] | None = None


class GetMediaBuyDeliveryRequest(BaseModel):
    """Request delivery data for one or more media buys.

    Examples:
    - Single buy: media_buy_ids=["buy_123"]
    - Multiple buys: buyer_refs=["ref_123", "ref_456"]
    - All active buys: status_filter="active"
    - All buys: status_filter="all"
    """

    media_buy_ids: list[str] | None = Field(
        None, description="Specific media buy IDs to fetch. If omitted, fetches based on status_filter."
    )
    buyer_refs: list[str] | None = Field(
        None, description="Alternative: specify buyer references instead of media buy IDs."
    )
    status_filter: str | None = Field(
        "active",
        description="Filter for which buys to fetch when IDs/refs not provided: 'active', 'all', 'completed'",
    )
    today: date = Field(..., description="Reference date for calculating delivery metrics")
    strategy_id: str | None = Field(
        None,
        description="Optional strategy ID for consistent simulation/testing context",
    )


class MediaBuyDeliveryData(BaseModel):
    """Delivery data for a single media buy."""

    media_buy_id: str
    buyer_ref: str
    status: str
    spend: Budget
    impressions: int
    pacing: str
    days_elapsed: int
    total_days: int


class GetMediaBuyDeliveryResponse(BaseModel):
    """Response containing delivery data for requested media buys.

    For single buy requests, 'deliveries' will contain one item.
    For multiple/all requests, it contains all matching buys.
    """

    deliveries: list[MediaBuyDeliveryData]
    total_spend: float
    total_impressions: int
    active_count: int
    summary_date: date


# Deprecated - kept for backward compatibility
class GetAllMediaBuyDeliveryRequest(BaseModel):
    """DEPRECATED: Use GetMediaBuyDeliveryRequest with filter='all' instead."""

    today: date
    media_buy_ids: list[str] | None = None


class GetAllMediaBuyDeliveryResponse(BaseModel):
    """DEPRECATED: Use GetMediaBuyDeliveryResponse instead."""

    deliveries: list[MediaBuyDeliveryData]
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
    format_ids: list[str]


class ReportingPeriod(BaseModel):
    start: datetime
    end: datetime
    start_date: date | None = None  # For compatibility
    end_date: date | None = None  # For compatibility


class DeliveryTotals(BaseModel):
    impressions: int
    spend: float
    clicks: int | None = 0
    video_completions: int | None = 0


class PackagePerformance(BaseModel):
    package_id: str
    performance_index: float


class AssetStatus(BaseModel):
    creative_id: str
    status: str


class UpdateMediaBuyResponse(BaseModel):
    status: str
    implementation_date: datetime | None = None
    reason: str | None = None
    detail: str | None = None


# Unified update models
class PackageUpdate(BaseModel):
    """Updates to apply to a specific package."""

    package_id: str
    active: bool | None = None  # True to activate, False to pause
    budget: float | None = None  # New budget in dollars
    impressions: int | None = None  # Direct impression goal (overrides budget calculation)
    cpm: float | None = None  # Update CPM rate
    daily_budget: float | None = None  # Daily spend cap
    daily_impressions: int | None = None  # Daily impression cap
    pacing: Literal["even", "asap", "front_loaded"] | None = None
    creative_ids: list[str] | None = None  # Update creative assignments
    targeting_overlay: Targeting | None = None  # Package-specific targeting refinements


class UpdatePackageRequest(BaseModel):
    """Update one or more packages within a media buy.

    Uses PATCH semantics: Only packages mentioned are affected.
    Omitted packages remain unchanged.
    To remove a package from delivery, set active=false.
    To add new packages, use create_media_buy or add_packages (future tool).
    """

    media_buy_id: str
    packages: list[PackageUpdate]  # List of package updates
    today: date | None = None  # For testing/simulation


class UpdateMediaBuyRequest(BaseModel):
    """Update a media buy - mirrors CreateMediaBuyRequest structure.

    Uses PATCH semantics: Only fields provided are updated.
    Package updates only affect packages explicitly mentioned.
    To pause all packages, set active=false at campaign level.
    To pause specific packages, include them in packages list with active=false.
    """

    media_buy_id: str
    # Campaign-level updates
    buyer_ref: str | None = None  # Update buyer reference
    active: bool | None = None  # True to activate, False to pause entire campaign
    flight_start_date: date | None = None  # Change start date (if not started)
    flight_end_date: date | None = None  # Extend or shorten campaign
    budget: Budget | float | None = None  # Update total budget (supports Budget object or float)
    currency: str | None = None  # Update currency (ISO 4217)
    targeting_overlay: Targeting | None = None  # Update global targeting
    start_time: datetime | None = None  # Update start datetime
    end_time: datetime | None = None  # Update end datetime
    pacing: Literal["even", "asap", "daily_budget"] | None = None
    daily_budget: float | None = None  # Daily spend cap across all packages
    # Package-level updates
    packages: list[PackageUpdate] | None = None  # Package-specific updates (only these are affected)
    # Creative updates
    creatives: list[Creative] | None = None  # Add new creatives

    # Backward compatibility properties
    @property
    def total_budget(self) -> float | None:
        """Backward compatibility for old field name."""
        return self.budget

    @property
    def start_date(self) -> date | None:
        """Alias for consistency with CreateMediaBuyRequest."""
        return self.flight_start_date

    @property
    def end_date(self) -> date | None:
        """Alias for consistency with CreateMediaBuyRequest."""
        return self.flight_end_date

    # Legacy fields
    creative_assignments: dict[str, list[str]] | None = None  # Update creative-to-package mapping
    today: date | None = None  # For testing/simulation
    strategy_id: str | None = Field(
        None,
        description="Optional strategy ID for consistent simulation/testing context",
    )


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
    by_package: list[PackageDelivery]
    currency: str


# --- Human-in-the-Loop Task Queue ---


class HumanTask(BaseModel):
    """Task requiring human intervention."""

    task_id: str
    task_type: (
        str  # creative_approval, permission_exception, configuration_required, compliance_review, manual_approval
    )
    principal_id: str
    adapter_name: str | None = None
    status: str = "pending"  # pending, assigned, in_progress, completed, failed, escalated
    priority: str = "medium"  # low, medium, high, urgent

    # Context
    media_buy_id: str | None = None
    creative_id: str | None = None
    operation: str | None = None
    error_detail: str | None = None
    context_data: dict[str, Any] | None = None

    # Assignment
    assigned_to: str | None = None
    assigned_at: datetime | None = None

    # Timing
    created_at: datetime
    updated_at: datetime
    due_by: datetime | None = None
    completed_at: datetime | None = None

    # Resolution
    resolution: str | None = None  # approved, rejected, completed, cannot_complete
    resolution_detail: str | None = None
    resolved_by: str | None = None


class CreateHumanTaskRequest(BaseModel):
    """Request to create a human task."""

    task_type: str
    priority: str = "medium"
    adapter_name: str | None = None  # Added to match HumanTask schema

    # Context
    media_buy_id: str | None = None
    creative_id: str | None = None
    operation: str | None = None
    error_detail: str | None = None
    context_data: dict[str, Any] | None = None

    # SLA
    due_in_hours: int | None = None  # Hours until due


class CreateHumanTaskResponse(BaseModel):
    """Response from creating a human task."""

    task_id: str
    status: str
    due_by: datetime | None = None


class GetPendingTasksRequest(BaseModel):
    """Request for pending human tasks."""

    principal_id: str | None = None  # Filter by principal
    task_type: str | None = None  # Filter by type
    priority: str | None = None  # Filter by minimum priority
    assigned_to: str | None = None  # Filter by assignee
    include_overdue: bool = True


class GetPendingTasksResponse(BaseModel):
    """Response with pending tasks."""

    tasks: list[HumanTask]
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
    resolution_detail: str | None = None
    resolved_by: str


class VerifyTaskRequest(BaseModel):
    """Request to verify if a task was completed correctly."""

    task_id: str
    expected_outcome: dict[str, Any] | None = None  # What the task should have accomplished


class VerifyTaskResponse(BaseModel):
    """Response from task verification."""

    task_id: str
    verified: bool
    actual_state: dict[str, Any]
    expected_state: dict[str, Any] | None = None
    discrepancies: list[str] = []


class MarkTaskCompleteRequest(BaseModel):
    """Admin request to mark a task as complete with verification."""

    task_id: str
    override_verification: bool = False  # Force complete even if verification fails
    completed_by: str


# Targeting capabilities
class GetTargetingCapabilitiesRequest(BaseModel):
    """Query targeting capabilities for channels."""

    channels: list[str] | None = None  # If None, return all channels
    include_aee_dimensions: bool = True


class TargetingDimensionInfo(BaseModel):
    """Information about a single targeting dimension."""

    key: str
    display_name: str
    description: str
    data_type: str
    required: bool = False
    values: list[str] | None = None


class ChannelTargetingCapabilities(BaseModel):
    """Targeting capabilities for a specific channel."""

    channel: str
    overlay_dimensions: list[TargetingDimensionInfo]
    aee_dimensions: list[TargetingDimensionInfo] | None = None


class GetTargetingCapabilitiesResponse(BaseModel):
    """Response with targeting capabilities."""

    capabilities: list[ChannelTargetingCapabilities]


class CheckAEERequirementsRequest(BaseModel):
    """Check if required AEE dimensions are supported."""

    channel: str
    required_dimensions: list[str]


class CheckAEERequirementsResponse(BaseModel):
    """Response for AEE requirements check."""

    supported: bool
    missing_dimensions: list[str]
    available_dimensions: list[str]


# Creative macro is now a simple string passed via AEE aee_signals


# --- Signal Discovery ---
class Signal(BaseModel):
    """Represents an available signal (audience, contextual, geographic, etc.)"""

    signal_id: str
    name: str
    description: str
    type: Literal["audience", "contextual", "geographic", "behavioral", "custom"]
    category: str | None = None  # e.g., "automotive", "finance", "sports"
    reach: float | None = None  # Estimated reach percentage
    cpm_uplift: float | None = None  # Expected CPM increase when using this signal
    metadata: dict[str, Any] | None = {}


class GetSignalsRequest(BaseModel):
    """Request to discover available signals."""

    query: str | None = None  # Natural language search query
    type: str | None = None  # Filter by signal type
    category: str | None = None  # Filter by category
    limit: int | None = 100


class GetSignalsResponse(BaseModel):
    """Response containing available signals."""

    signals: list[Signal]


# --- Simulation and Time Progression Control ---
class SimulationControlRequest(BaseModel):
    """Control simulation time progression and events."""

    strategy_id: str = Field(..., description="Strategy ID to control (must be simulation strategy with 'sim_' prefix)")
    action: Literal["jump_to", "reset", "set_scenario"] = Field(..., description="Action to perform on the simulation")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters")


class SimulationControlResponse(BaseModel):
    """Response from simulation control operations."""

    status: Literal["ok", "error"] = "ok"
    message: str | None = None
    current_state: dict[str, Any] | None = None
    simulation_time: datetime | None = None
