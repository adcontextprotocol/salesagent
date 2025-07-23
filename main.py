from fastmcp import FastMCP
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# Pydantic Models for get_proposal
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
    video: VideoAssets
    companion: CompanionAssets

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

# Pydantic Models for accept_proposal
class AcceptProposalResponse(BaseModel):
    media_buy_id: str
    status: str
    creative_deadline: str

# Pydantic Models for add_creative_assets
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

# Pydantic Models for check_media_buy_status
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

# Pydantic Models for update_media_buy_performance_index
class ReportingPeriod(BaseModel):
    start: str
    end: str

class PackagePerformance(BaseModel):
    package_id: str
    performance_index: int
    sufficient_data: Optional[bool] = True

class UpdateMediaBuyPerformanceIndexResponse(BaseModel):
    acknowledged: bool

# Pydantic Models for get_media_buy_delivery
class DateRange(BaseModel):
    start: str
    end: str

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

# Pydantic Models for update_media_buy
class UpdateMediaBuyResponse(BaseModel):
    status: str
    implementation_date: Optional[str] = None
    notes: Optional[str] = None
    reason: Optional[str] = None


mcp = FastMCP(name="AdCPSalesAgent")

@mcp.tool
def get_proposal(
    brief: str,
    provided_signals: Optional[List[ProvidedSignal]] = None,
    proposal_id: Optional[str] = None,
    requested_changes: Optional[List[RequestedChange]] = None,
) -> Proposal:
    """Request a proposal from the publisher"""
    return Proposal(
        proposal_id="july_sports_v1",
        expiration_date="2025-06-15 18:00:00 PST",
        total_budget=150000,
        currency="USD",
        start_time="2025-07-01 00:00:00 PST",
        end_time="2025-07-31 00:00:00 PST",
        notes="The brief was unclear about age, gender, or geographic preferences. Please provide more detail if available.",
        creative_formats=[
            CreativeFormat(
                name="E2E mobile video",
                assets=CreativeAssets(
                    video=VideoAssets(
                        formats=["mp4", "webm"],
                        resolutions=[
                            VideoResolution(width=1080, height=1080, label="square"),
                            VideoResolution(width=1920, height=1080, label="horizontal"),
                        ],
                        max_file_size_mb=50,
                        duration_options=[6, 15],
                    ),
                    companion=CompanionAssets(
                        logo={"size": "300x300", "format": "png"},
                        overlay_image={"size": "1080x1080", "format": "jpg", "optional": True},
                    ),
                ),
                description="An immersive mobile video that scrolls in-feed",
            )
        ],
        media_packages=[
            MediaPackage(
                package_id="abcd1",
                name="Remarketing with lookalikes",
                description="Run of site package using the provided audience to create lookalike users to ensure sufficient reach for measurement",
                delivery_restrictions="US only. Restricted to top 50 DMAs to ensure measurement reach.",
                provided_signals=ProvidedSignalsInPackage(
                    included_ids=["recent-site-visitor"],
                    excluded_ids=["brand-safety-us-sports"],
                ),
                cpm=22.00,
                budget=25000,
                budget_capacity=150000,
                creative_formats="E2E mobile video",
            )
        ],
    )

@mcp.tool
def accept_proposal(
    proposal_id: str,
    accepted_packages: List[str],
    billing_entity: str,
    po_number: str,
) -> AcceptProposalResponse:
    """Accept a proposal and convert it into a media buy."""
    return AcceptProposalResponse(
        media_buy_id="buy_nike_sports_2025_07",
        status="pending_creative",
        creative_deadline="2025-06-25T00:00:00Z",
    )

@mcp.tool
def add_creative_assets(
    media_buy_id: str,
    packages: List[str],
    assets: List[CreativeAsset],
) -> AddCreativeAssetsResponse:
    """Add creative assets to a media buy."""
    return AddCreativeAssetsResponse(
        status="received",
        assets=[
            AssetStatus(
                creative_id=asset.creative_id,
                status="pending_review",
                estimated_approval_time="2025-06-26T18:00:00Z",
            )
            for asset in assets
        ],
    )

@mcp.tool
def check_media_buy_status(media_buy_id: str) -> CheckMediaBuyStatusResponse:
    """Check the status of a media buy."""
    return CheckMediaBuyStatusResponse(
        media_buy_id=media_buy_id,
        status="live",
        flight_progress=FlightProgress(
            days_elapsed=14,
            days_remaining=17,
            percentage_complete=45,
        ),
        delivery=Delivery(
            impressions=3409091,
            spend=75000,
            pacing="on_track",
        ),
        packages=[
            PackageStatus(package_id="abcd1", status="delivering", spend=12500, pacing="on_track"),
            PackageStatus(package_id="abcd2", status="delivering", spend=32500, pacing="slightly_behind"),
        ],
        issues=[],
        last_updated="2025-07-15T12:00:00Z",
    )

@mcp.tool
def update_media_buy_performance_index(
    media_buy_id: str,
    reporting_period: ReportingPeriod,
    package_performance: List[PackagePerformance],
) -> UpdateMediaBuyPerformanceIndexResponse:
    """Update the performance index for a media buy."""
    return UpdateMediaBuyPerformanceIndexResponse(acknowledged=True)

@mcp.tool
def get_media_buy_delivery(
    media_buy_id: str,
    date_range: DateRange,
) -> GetMediaBuyDeliveryResponse:
    """Get the delivery data for a media buy."""
    return GetMediaBuyDeliveryResponse(
        media_buy_id=media_buy_id,
        reporting_period=ReportingPeriod(start=date_range.start, end=date_range.end),
        totals=DeliveryTotals(
            impressions=3409091,
            spend=75000.00,
            clicks=40909,
            video_completions=2236364,
        ),
        by_package=[
            PackageDelivery(package_id="abcd1", impressions=568182, spend=12500.00),
            PackageDelivery(package_id="abcd2", impressions=1805556, spend=32500.00),
        ],
        currency="USD",
    )

@mcp.tool
def update_media_buy(
    media_buy_id: str,
    action: str,
    creative_id: Optional[str] = None,
    package_id: Optional[str] = None,
    budget: Optional[int] = None,
    reason: Optional[str] = None,
) -> UpdateMediaBuyResponse:
    """Update a media buy with various actions."""
    # In a real implementation, you would handle the different actions.
    return UpdateMediaBuyResponse(
        status="accepted",
        implementation_date="2025-07-16T00:00:00Z",
        notes="Changes will take effect at midnight Pacific.",
    )


if __name__ == "__main__":
    mcp.run()