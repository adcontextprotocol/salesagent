from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Pydantic Models ---

class ProvidedSignal(BaseModel):
    id: str
    must_not_be_present: Optional[bool] = None
    targeting_direction: Optional[str] = None
    description: Optional[str] = None
    required_aee_fields: Optional[str] = None

class RequestedChange(BaseModel):
    package_id: str
    field: str
    notes: str

class VideoResolution(BaseModel):
    width: int
    height: int
    label: str

class VideoAssets(BaseModel):
    formats: List[str]
    resolutions: List[VideoResolution]
    max_file_size_mb: int
    duration_options: List[int]

class CompanionAssets(BaseModel):
    logo: Dict[str, Any]
    overlay_image: Dict[str, Any]

class CreativeAssets(BaseModel):
    video: Optional[VideoAssets] = None
    companion: Optional[CompanionAssets] = None
    image: Optional[Dict[str, Any]] = None

class CreativeFormat(BaseModel):
    name: str
    assets: CreativeAssets
    description: str

class ProvidedSignalsInPackage(BaseModel):
    included_ids: Optional[List[str]] = None
    excluded_ids: Optional[List[str]] = None

class MediaPackage(BaseModel):
    package_id: str
    name: str
    description: str
    delivery_restrictions: str
    provided_signals: ProvidedSignalsInPackage
    cpm: float
    budget: int
    budget_capacity: int
    creative_formats: str

class Proposal(BaseModel):
    proposal_id: str
    expiration_date: Optional[str] = None
    total_budget: int
    currency: str
    start_time: str
    end_time: str
    notes: Optional[str] = None
    creative_formats: List[CreativeFormat]
    media_packages: List[MediaPackage]

class AcceptProposalResponse(BaseModel):
    media_buy_id: str
    status: str
    creative_deadline: str

class CreativeAsset(BaseModel):
    creative_id: str
    format: str
    name: str
    video_url: str
    companion_assets: Dict[str, str]
    click_url: str
    package_assignments: List[str]

class AssetStatus(BaseModel):
    creative_id: str
    status: str
    estimated_approval_time: str

class AddCreativeAssetsResponse(BaseModel):
    status: str
    assets: List[AssetStatus]

class FlightProgress(BaseModel):
    days_elapsed: int
    days_remaining: int
    percentage_complete: int

class Delivery(BaseModel):
    impressions: int
    spend: int
    pacing: str

class PackageStatus(BaseModel):
    package_id: str
    status: str
    spend: int
    pacing: str

class CheckMediaBuyStatusResponse(BaseModel):
    media_buy_id: str
    status: str
    flight_progress: Optional[FlightProgress] = None
    delivery: Optional[Delivery] = None
    packages: Optional[List[PackageStatus]] = None
    issues: Optional[List[str]] = None
    last_updated: Optional[str] = None

class ReportingPeriod(BaseModel):
    start: str
    end: str

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
    implementation_date: Optional[str] = None
    notes: Optional[str] = None
    reason: Optional[str] = None
