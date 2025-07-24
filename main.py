import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import google.generativeai as genai
from pydantic import BaseModel, Field

from database import init_db
from fastmcp import FastMCP

# --- Database and Model Initialization ---
init_db()
# IMPORTANT: In a real application, load the API key from a secure source
genai.configure(api_key="AIzaSyBgMWI7SpBfuClTz32wZ-mZg-dPBA9Dbgc")
model = genai.GenerativeModel('gemini-2.5-flash')

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

class UpdateMediaBuyResponse(BaseModel):
    status: str
    implementation_date: Optional[str] = None
    notes: Optional[str] = None
    reason: Optional[str] = None

# --- MCP Server ---

mcp = FastMCP(name="AdCPSalesAgent")

@mcp.tool
def get_proposal(
    brief: str,
    provided_signals: Optional[List[ProvidedSignal]] = None,
    proposal_id: Optional[str] = None,
    requested_changes: Optional[List[RequestedChange]] = None,
) -> Proposal:
    """Request a proposal from the publisher by intelligently selecting inventory."""
    
    conn = sqlite3.connect('adcp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM placements")
    placements = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM audiences")
    audiences = [dict(row) for row in cursor.fetchall()]
    
    inventory_json = json.dumps({"placements": placements, "audiences": audiences}, indent=2)

    prompt = f"""
    You are an expert media planner. Your task is to select the best media placements for a client based on their brief and our available inventory.

    **Client Brief:**
    "{brief}"

    **Available Inventory (Placements and Audiences):**
    {inventory_json}

    **Your Task:**
    1.  Analyze the client's brief to understand their goals and target audience.
    2.  From the "placements" list, select the IDs of the most relevant placements.
    3.  Determine an appropriate budget allocation for each selected placement ID.
    4.  Your response **MUST** be a JSON object with a single key: "selected_placements".
    5.  The value of "selected_placements" should be a list of dictionaries, where each dictionary has two keys: "placement_id" (integer) and "budget" (integer).
    6.  If no placements are suitable, return an empty list for "selected_placements".

    **Example Response:**
    {{
      "selected_placements": [
        {{ "placement_id": 1, "budget": 75000 }},
        {{ "placement_id": 2, "budget": 75000 }}
      ]
    }}

    Return only the JSON object.
    """

    try:
        response = model.generate_content(prompt)
        clean_json_str = response.text.strip().replace("```json", "").replace("```", "").strip()
        ai_decision = json.loads(clean_json_str)
        selected_placements = ai_decision.get("selected_placements", [])

        if not selected_placements:
            return Proposal(
                proposal_id=f"no_match_{int(datetime.now().timestamp())}",
                notes="Could not find any matching inventory for the provided brief.",
                media_packages=[], creative_formats=[], total_budget=0, currency="USD",
                start_time=datetime.now().isoformat(), end_time=(datetime.now() + timedelta(days=30)).isoformat()
            )

        # 4. Build the full Proposal object from the AI's decision
        media_packages = []
        creative_formats_dict = {}
        total_budget = 0

        for selection in selected_placements:
            cursor.execute("SELECT p.*, prop.name as property_name FROM placements p JOIN properties prop ON p.property_id = prop.id WHERE p.id = ?", (selection['placement_id'],))
            placement_details = cursor.fetchone()
            
            # Find associated formats and audiences
            cursor.execute("SELECT cf.* FROM placement_formats pf JOIN creative_formats cf ON pf.format_id = cf.id WHERE pf.placement_id = ?", (placement_details['id'],))
            formats = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT a.* FROM placement_audiences pa JOIN audiences a ON pa.audience_id = a.id WHERE pa.placement_id = ?", (placement_details['id'],))
            targeted_audiences = [dict(row) for row in cursor.fetchall()]

            package = MediaPackage(
                package_id=f"pkg_{placement_details['id']}",
                name=f"{placement_details['property_name']} - {placement_details['name']}",
                description=f"Targeting {', '.join([a['name'] for a in targeted_audiences])} on {placement_details['property_name']}",
                delivery_restrictions="US", # Placeholder
                provided_signals=ProvidedSignalsInPackage(included_ids=[a['name'] for a in targeted_audiences]),
                cpm=placement_details['base_cpm'],
                budget=selection['budget'],
                budget_capacity=100000, # Placeholder
                creative_formats=", ".join([f['name'] for f in formats])
            )
            media_packages.append(package)
            total_budget += selection['budget']

            for f in formats:
                if f['name'] not in creative_formats_dict:
                    spec = json.loads(f['spec'])
                    creative_formats_dict[f['name']] = CreativeFormat(name=f['name'], assets=spec['assets'], description=spec['description'])

        conn.close()

        return Proposal(
            proposal_id=f"proposal_{int(datetime.now().timestamp())}",
            total_budget=total_budget,
            currency="USD",
            start_time=datetime.now().isoformat(),
            end_time=(datetime.now() + timedelta(days=30)).isoformat(),
            notes="Proposal generated by AI media planner.",
            creative_formats=list(creative_formats_dict.values()),
            media_packages=media_packages
        )

    except (Exception, json.JSONDecodeError) as e:
        print(f"Error processing AI proposal: {e}")
        raise ValueError("Failed to generate or process the AI's proposal selection.")


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
    return UpdateMediaBuyResponse(
        status="accepted",
        implementation_date="2025-07-16T00:00:00Z",
        notes="Changes will take effect at midnight Pacific.",
    )

if __name__ == "__main__":
    mcp.run()
