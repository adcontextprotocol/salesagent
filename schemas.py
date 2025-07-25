from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

# --- V2 Pydantic Models ---

# --- Creative Specifications (OpenRTB 2.6 Inspired) ---

class CompanionAd(BaseModel):
    w: int
    h: int

class CreativeAsset(BaseModel):
    id: str
    media_type: Literal["video", "audio", "display", "dooh"]
    mime: str
    w: Optional[int] = None
    h: Optional[int] = None
    dur: Optional[int] = None # Duration in seconds
    protocols: Optional[List[int]] = None # VAST versions
    api: Optional[List[int]] = None # OMID, etc.
    companionad: Optional[CompanionAd] = None
    # Audio specific
    feed: Optional[int] = None
    stitched: Optional[bool] = None
    nvol: Optional[int] = None
    # DOOH specific
    venuetype: Optional[int] = None
    pxratio: Optional[float] = None

# --- Package Discovery (get_packages) ---

class Targeting(BaseModel):
    provided_signals: List[Dict[str, Any]]

class GetPackagesRequest(BaseModel):
    budget: float
    currency: str
    start_time: datetime
    end_time: datetime
    creatives: List[CreativeAsset]
    targeting: Targeting

class CreativeCompatibility(BaseModel):
    compatible: bool
    requires_approval: bool
    reason: Optional[str] = None

class PricingGuidance(BaseModel):
    floor_cpm: Optional[float] = None
    suggested_cpm: float
    p25: float
    p50: float
    p75: float
    p90: float

class DeliveryEstimate(BaseModel):
    impressions: int
    win_rate: float

class MediaPackage(BaseModel):
    package_id: str
    name: str
    description: str
    type: Literal["custom", "catalog"]
    delivery_type: Literal["guaranteed", "non_guaranteed"]
    creative_compatibility: Dict[str, CreativeCompatibility]
    cpm: Optional[float] = None # For guaranteed
    budget: Optional[float] = None # For guaranteed
    pricing: Optional[PricingGuidance] = None # For non-guaranteed
    delivery_estimates: Optional[Dict[str, DeliveryEstimate]] = None # For non-guaranteed

class GetPackagesResponse(BaseModel):
    packages: List[MediaPackage]

# --- Media Buy Creation (create_media_buy) ---

class SelectedPackage(BaseModel):
    package_id: str
    max_cpm: Optional[float] = None # Required for non-guaranteed

class CreateMediaBuyRequest(BaseModel):
    selected_packages: List[SelectedPackage]
    billing_entity: str
    po_number: str

class CreateMediaBuyResponse(BaseModel):
    media_buy_id: str
    status: str
    creative_deadline: Optional[datetime] = None

# --- Status and Reporting ---

class AssetStatus(BaseModel):
    creative_id: str
    status: str
    estimated_approval_time: Optional[datetime] = None

class AddCreativeAssetsResponse(BaseModel):
    status: str
    assets: List[AssetStatus]

class FlightProgress(BaseModel):
    days_elapsed: int
    days_remaining: int
    percentage_complete: float

class Delivery(BaseModel):
    impressions: int
    spend: float
    pacing: str
    win_rate: Optional[float] = None # For non-guaranteed

class PackageStatus(BaseModel):
    package_id: str
    status: str
    spend: float
    pacing: str

class CheckMediaBuyStatusResponse(BaseModel):
    media_buy_id: str
    status: str
    flight_progress: Optional[FlightProgress] = None
    delivery: Optional[Delivery] = None
    packages: Optional[List[PackageStatus]] = None
    issues: Optional[List[str]] = None
    last_updated: Optional[datetime] = None

class ReportingPeriod(BaseModel):
    start: datetime
    end: datetime

class PackagePerformance(BaseModel):
    package_id: str
    performance_index: int
    sufficient_data: Optional[bool] = True

class UpdateMediaBuyPerformanceIndexResponse(BaseModel):
    acknowledged: bool

class DeliveryTotals(BaseModel):
    impressions: int
    spend: float
    clicks: int
    video_completions: int

class PackageDelivery(BaseModel):
    package_id: str
    impressions: int
    spend: float

class GetMediaBuyDeliveryResponse(BaseModel):
    media_buy_id: str
    reporting_period: ReportingPeriod
    totals: DeliveryTotals
    by_package: List[PackageDelivery]
    currency: str

class UpdateMediaBuyResponse(BaseModel):
    status: str
    implementation_date: Optional[datetime] = None
    notes: Optional[str] = None
    reason: Optional[str] = None