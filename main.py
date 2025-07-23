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

import sqlite3
import json
from datetime import datetime, timedelta
import google.generativeai as genai

# IMPORTANT: In a real application, load the API key from a secure source
# (e.g., environment variable or secret manager)
genai.configure(api_key="AIzaSyBgMWI7SpBfuClTz32wZ-mZg-dPBA9Dbgc")
model = genai.GenerativeModel('gemini-2.5-flash')

@mcp.tool
def get_proposal(
    brief: str,
    provided_signals: Optional[List[ProvidedSignal]] = None,
    proposal_id: Optional[str] = None,
    requested_changes: Optional[List[RequestedChange]] = None,
) -> Proposal:
    """Request a proposal from the publisher by intelligently parsing the brief."""
    
    prompt = f"""
    You are a media planning assistant. Your task is to parse a campaign brief 
    and extract key parameters into a structured JSON object.

    The JSON object should have the following keys:
    - "geography": A list of strings for targeting (e.g., ["US", "UK-London"]). Return an empty list if not specified.
    - "budget": A dictionary with "amount" (float) and "currency" (str), or null if not specified.
    - "dates": A dictionary with "start_date" and "end_date" (ISO format strings), or null if not specified.
    - "objectives": A list of strings describing campaign goals (e.g., ["brand awareness", "increase sales"]). Return an empty list if not specified.
    - "target_audience_keywords": A list of keywords describing the target audience (e.g., ["sports", "runners"]).
    - "min_cpm": The minimum acceptable CPM as a float, or null if not specified.
    - "max_cpm": The maximum acceptable CPM as a float, or null if not specified.

    Analyze the following brief and return only the JSON object.

    Brief:
    "{brief}"
    """
    
    try:
        response = model.generate_content(prompt)
        clean_json_str = response.text.strip().replace("```json", "").replace("```", "").strip()
        parsed_brief = json.loads(clean_json_str)
    except (Exception, json.JSONDecodeError) as e:
        print(f"Error parsing brief with Gemini: {e}")
        parsed_brief = {}

    # --- Validation Step ---
    missing_fields = []
    if not parsed_brief.get("geography"):
        missing_fields.append("geography")
    if not parsed_brief.get("budget"):
        missing_fields.append("budget")
    if not parsed_brief.get("dates"):
        missing_fields.append("dates")
    if not parsed_brief.get("objectives"):
        missing_fields.append("objectives")

    if missing_fields:
        notes = f"Brief is incomplete. Please provide the following missing information: {', '.join(missing_fields)}."
        return Proposal(
            proposal_id=f"invalid_proposal_{int(datetime.now().timestamp())}",
            total_budget=0,
            currency="USD",
            start_time=datetime.now().isoformat(),
            end_time=(datetime.now() + timedelta(days=1)).isoformat(),
            notes=notes,
            creative_formats=[],
            media_packages=[],
        )
    # --- End Validation ---

    conn = sqlite3.connect('adcp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            p.id as placement_id,
            p.name as placement_name,
            p.base_cpm,
            prop.name as property_name,
            cf.name as format_name,
            cf.spec as format_spec,
            aud.name as audience_name,
            aud.description as audience_description
        FROM placements p
        JOIN properties prop ON p.property_id = prop.id
        JOIN placement_formats pf ON p.id = pf.placement_id
        JOIN creative_formats cf ON pf.format_id = cf.id
        JOIN placement_audiences pa ON p.id = pa.placement_id
        JOIN audiences aud ON pa.audience_id = aud.id
        WHERE 1=1
    """
    params = []
    
    keywords = parsed_brief.get("target_audience_keywords", [])
    if keywords:
        audience_clauses = []
        for keyword in keywords:
            audience_clauses.append("aud.name LIKE ? OR aud.description LIKE ?")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        query += f" AND ({' OR '.join(audience_clauses)})"

    min_cpm = parsed_brief.get("min_cpm")
    max_cpm = parsed_brief.get("max_cpm")
    if min_cpm is not None:
        query += " AND p.base_cpm >= ?"
        params.append(min_cpm)
    if max_cpm is not None:
        query += " AND p.base_cpm <= ?"
        params.append(max_cpm)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    media_packages = []
    creative_formats_dict = {}
    notes = f"Proposal generated based on brief analysis. Found {len(rows)} potential placements."

    if not rows:
        notes = "Could not find any matching inventory for the provided brief. Please broaden your criteria."

    for row in rows:
        package_id = f"pkg_{row['placement_id']}_{row['audience_name'].replace(' ', '').lower()}"
        package = MediaPackage(
            package_id=package_id,
            name=f"{row['property_name']} - {row['placement_name']}",
            description=f"Targeting {row['audience_name']} on {row['property_name']}'s {row['placement_name']}.",
            delivery_restrictions=", ".join(parsed_brief.get("geography", ["US"])),
            provided_signals=ProvidedSignalsInPackage(included_ids=[row['audience_name']]),
            cpm=row['base_cpm'],
            budget=20000,
            budget_capacity=100000,
            creative_formats=row['format_name']
        )
        media_packages.append(package)

        if row['format_name'] not in creative_formats_dict:
            spec = json.loads(row['format_spec'])
            assets_data = {
                'video': spec['assets']['video'],
                'companion': spec['assets']['companion']
            }
            creative_formats_dict[row['format_name']] = CreativeFormat(
                name=row['format_name'],
                assets=CreativeAssets(**assets_data),
                description=spec['description']
            )
    
    new_proposal_id = f"proposal_{int(datetime.now().timestamp())}"
    budget_info = parsed_brief.get("budget", {"amount": sum(p.budget for p in media_packages), "currency": "USD"})
    dates_info = parsed_brief.get("dates", {"start_date": datetime.now().isoformat(), "end_date": (datetime.now() + timedelta(days=30)).isoformat()})

    return Proposal(
        proposal_id=new_proposal_id,
        expiration_date=(datetime.now() + timedelta(days=7)).isoformat(),
        total_budget=budget_info.get("amount"),
        currency=budget_info.get("currency"),
        start_time=dates_info.get("start_date"),
        end_time=dates_info.get("end_date"),
        notes=notes,
        creative_formats=list(creative_formats_dict.values()),
        media_packages=media_packages,
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


from database import init_db

if __name__ == "__main__":
    init_db()
    mcp.run()