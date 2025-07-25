import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import google.generativeai as genai
from fastmcp import FastMCP

from database import init_db
# --- Database and Model Initialization ---
init_db()
# IMPORTANT: In a real application, load the API key from a secure source
genai.configure(api_key="AIzaSyBgMWI7SpBfuClTz32wZ-mZg-dPBA9Dbgc")
model = genai.GenerativeModel('gemini-2.5-flash')

from rich.console import Console
from rich.pretty import Pretty

from schemas import *
from mock_ad_server import MockAdServer

# --- In-Memory State ---
proposals_cache: Dict[str, Proposal] = {}
media_buys: Dict[str, Any] = {}
console = Console()


# --- MCP Server ---
mcp = FastMCP(name="AdCPSalesAgent")

def _get_proposal_logic(
    brief: str,
    provided_signals: Optional[List[ProvidedSignal]] = None,
    proposal_id: Optional[str] = None,
    requested_changes: Optional[List[RequestedChange]] = None,
) -> Proposal:
    """The core logic for generating a proposal."""
    conn = sqlite3.connect('adcp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM placements")
    placements = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM audiences")
    audiences = [dict(row) for row in cursor.fetchall()]
    
    inventory_json = json.dumps({"placements": placements, "audiences": audiences}, indent=2)
    # Convert Pydantic objects to dicts for JSON serialization
    provided_signals_dict = [signal.model_dump() for signal in provided_signals] if provided_signals else []
    provided_signals_json = json.dumps(provided_signals_dict, indent=2) if provided_signals_dict else "None"

    prompt = f"""
    You are an expert media planner. Your task is to select the best media placements for a client based on their brief and our available inventory.

    **Client Brief:**
    "{brief}"

    **Client-Provided Signals (for targeting and exclusion):**
    {provided_signals_json}

    **Available Inventory (Placements and Audiences):**
    {inventory_json}

    **Your Task:**
    1.  Analyze the client's brief and provided signals.
    2.  From the "placements" list, select the IDs of the most relevant placements.
    3.  If the client provided an inclusion signal (e.g., "purina_purchasers_q1"), you **must** include it in at least one of the selected placements. You can mention that lookalikes can be used to expand this audience.
    4.  If the client provided an exclusion signal (e.g., "competitor_purchasers"), you **must** ensure it is excluded from all selected placements.
    5.  Determine an appropriate budget allocation for each selected placement ID.
    6.  Your response **MUST** be a JSON object with a single key: "selected_placements".
    7.  The value of "selected_placements" should be a list of dictionaries, where each dictionary has two keys: "placement_id" (integer) and "budget" (integer).
    8.  If no placements are suitable, return an empty list for "selected_placements".
    9.  **Crucially, you must use the flight dates from the brief when generating the proposal.**

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

        media_packages = []
        creative_formats_dict = {}
        total_budget = 0

        for selection in selected_placements:
            cursor.execute("SELECT p.*, prop.name as property_name FROM placements p JOIN properties prop ON p.property_id = prop.id WHERE p.id = ?", (selection['placement_id'],))
            placement_details = cursor.fetchone()
            
            cursor.execute("SELECT cf.* FROM placement_formats pf JOIN creative_formats cf ON pf.format_id = cf.id WHERE pf.placement_id = ?", (placement_details['id'],))
            formats = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT a.* FROM placement_audiences pa JOIN audiences a ON pa.audience_id = a.id WHERE pa.placement_id = ?", (placement_details['id'],))
            targeted_audiences = [dict(row) for row in cursor.fetchall()]
            
            included_ids = [a['name'] for a in targeted_audiences]
            excluded_ids = []
            if provided_signals:
                for signal in provided_signals:
                    if signal.must_not_be_present:
                        excluded_ids.append(signal.id)
                    elif signal.targeting_direction == 'include':
                        if signal.id not in included_ids:
                            included_ids.append(signal.id)

            package = MediaPackage(
                package_id=f"pkg_{placement_details['id']}",
                name=f"{placement_details['property_name']} - {placement_details['name']}",
                description=f"Targeting {', '.join(included_ids)} on {placement_details['property_name']}",
                delivery_restrictions="US",
                provided_signals=ProvidedSignalsInPackage(
                    included_ids=included_ids,
                    excluded_ids=excluded_ids if excluded_ids else None
                ),
                cpm=placement_details['base_cpm'],
                budget=selection['budget'],
                budget_capacity=100000,
                creative_formats=", ".join([f['name'] for f in formats])
            )
            media_packages.append(package)
            total_budget += selection['budget']

            for f in formats:
                if f['name'] not in creative_formats_dict:
                    spec = json.loads(f['spec'])
                    creative_formats_dict[f['name']] = CreativeFormat(name=f['name'], assets=spec, description=spec.get('description', ''))

        conn.close()

        # Extract dates from the brief to use in the proposal
        today = datetime.now()
        prompt_for_dates = f"""
        Today's date is {today.strftime('%Y-%m-%d')}.
        Analyze the following brief and extract the start and end dates for the campaign.
        Return a JSON object with "start_date" and "end_date" in ISO format (YYYY-MM-DD).
        Brief: "{brief}"
        """
        try:
            date_response = model.generate_content(prompt_for_dates)
            clean_date_str = date_response.text.strip().replace("```json", "").replace("```", "").strip()
            dates = json.loads(clean_date_str)
            start_time = dates.get("start_date", today.isoformat())
            end_time = dates.get("end_date", (today + timedelta(days=30)).isoformat())
        except (Exception, json.JSONDecodeError):
            start_time = today.isoformat()
            end_time = (today + timedelta(days=30)).isoformat()


        proposal = Proposal(
            proposal_id=f"proposal_{int(datetime.now().timestamp())}",
            total_budget=total_budget,
            currency="USD",
            start_time=start_time,
            end_time=end_time,
            notes="Proposal generated by AI media planner.",
            creative_formats=list(creative_formats_dict.values()),
            media_packages=media_packages
        )
        proposals_cache[proposal.proposal_id] = proposal
        return proposal

    except (Exception, json.JSONDecodeError, ValueError) as e:
        print(f"Error processing AI proposal: {e}")
        raise ValueError("Failed to generate or process the AI's proposal selection.")

@mcp.tool
def get_proposal(
    brief: str,
    provided_signals: Optional[List[ProvidedSignal]] = None,
    proposal_id: Optional[str] = None,
    requested_changes: Optional[List[RequestedChange]] = None,
) -> Proposal:
    """Request a proposal from the publisher by intelligently selecting inventory."""
    return _get_proposal_logic(brief, provided_signals, proposal_id, requested_changes)


@mcp.tool
def accept_proposal(
    proposal_id: str,
    accepted_packages: List[str],
    billing_entity: str,
    po_number: str,
    today: Optional[str] = None,
) -> AcceptProposalResponse:
    """Accept a proposal and convert it into a media buy."""
    
    proposal_to_accept = proposals_cache.get(proposal_id)
    if not proposal_to_accept:
        raise ValueError(f"Proposal with ID '{proposal_id}' not found or expired.")

    media_buy_id = f"buy_{po_number.lower().replace(' ', '_')}"
    
    # Filter to only include the accepted packages
    final_packages = [pkg for pkg in proposal_to_accept.media_packages if pkg.package_id in accepted_packages]

    # Extract dates from the brief to use in the media buy
    prompt_for_dates = f"""
    Today's date is {today.strftime('%Y-%m-%d')}.
    Analyze the following brief and extract the start and end dates for the campaign.
    Return a JSON object with "start_date" and "end_date" in ISO format (YYYY-MM-DD).
    Brief: "{proposal_to_accept.notes}"
    """
    try:
        date_response = model.generate_content(prompt_for_dates)
        clean_date_str = date_response.text.strip().replace("```json", "").replace("```", "").strip()
        dates = json.loads(clean_date_str)
        start_time = dates.get("start_date", today.isoformat())
        end_time = dates.get("end_date", (today + timedelta(days=30)).isoformat())
    except (Exception, json.JSONDecodeError):
        start_time = today.isoformat()
        end_time = (today + timedelta(days=30)).isoformat()

    media_buys[media_buy_id] = {
        "media_buy_id": media_buy_id,
        "status": "pending_creative",
        "billing_entity": billing_entity,
        "po_number": po_number,
        "accepted_packages": accepted_packages,
        "creatives": [],
        "start_time": start_time,
        "end_time": end_time,
        "total_budget": sum(pkg.budget for pkg in final_packages),
        "media_packages": [pkg.model_dump() for pkg in final_packages]
    }
    
    # Clean up the cache
    del proposals_cache[proposal_id]

    return AcceptProposalResponse(
        media_buy_id=media_buy_id,
        status="pending_creative",
        creative_deadline=(datetime.fromisoformat(start_time) - timedelta(days=5)).isoformat(),
    )


@mcp.tool
def add_creative_assets(
    media_buy_id: str,
    assets: List[CreativeAsset],
    today: Optional[str] = None,
) -> AddCreativeAssetsResponse:
    """Add creative assets to a media buy."""
    if media_buy_id not in media_buys:
        raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")
    
    media_buy = media_buys[media_buy_id]
    today_dt = datetime.fromisoformat(today) if today else datetime.now()
    
    response_assets = []
    for asset in assets:
        media_buy["creatives"].append(asset.model_dump())
        # Simulate a 2-day approval time
        approval_date = today_dt + timedelta(days=2)
        response_assets.append(
            AssetStatus(
                creative_id=asset.creative_id,
                status="pending_review",
                estimated_approval_time=approval_date.isoformat()
            )
        )
    
    media_buy["status"] = "pending_approval"
    return AddCreativeAssetsResponse(status="received", assets=response_assets)

@mcp.tool
def check_media_buy_status(
    media_buy_id: str, 
    today: Optional[str] = None
) -> CheckMediaBuyStatusResponse:
    """Check the status of a media buy."""
    if media_buy_id not in media_buys:
        raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")

    media_buy = media_buys[media_buy_id]
    today_dt = datetime.fromisoformat(today) if today else datetime.now()
    start_dt = datetime.fromisoformat(media_buy['start_time'])

    # Check creative approval status
    # This is a simple check; a real system would be more complex
    if media_buy["status"] == "pending_approval":
         # Let's assume creatives are approved 2 days after submission
        if today_dt >= (start_dt - timedelta(days=3)): # Simplified logic
             media_buy["status"] = "ready"
        else:
            return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status="pending_approval")

    if today_dt < start_dt:
        return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status="ready")

    # If campaign is live, get data from mock server
    ad_server = MockAdServer(media_buy)
    delivery_data = ad_server.get_status(today_dt)
    
    return CheckMediaBuyStatusResponse(
        media_buy_id=media_buy_id,
        status=delivery_data['status'],
        delivery=Delivery(**delivery_data),
        last_updated=today_dt.isoformat()
    )

@mcp.tool
def get_media_buy_delivery(
    media_buy_id: str,
    date_range: ReportingPeriod,
    today: Optional[str] = None,
) -> GetMediaBuyDeliveryResponse:
    """Get the delivery data for a media buy."""
    if media_buy_id not in media_buys:
        raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")
    
    media_buy = media_buys[media_buy_id]
    today_dt = datetime.fromisoformat(today) if today else datetime.now()
    
    ad_server = MockAdServer(media_buy)
    package_delivery = ad_server.get_package_delivery(today_dt)
    total_spend = sum(p['spend'] for p in package_delivery)
    total_impressions = sum(p['impressions'] for p in package_delivery)

    return GetMediaBuyDeliveryResponse(
        media_buy_id=media_buy_id,
        reporting_period=date_range,
        totals=DeliveryTotals(
            impressions=total_impressions,
            spend=total_spend,
            clicks=int(total_impressions * 0.01), # Assume 1% CTR
            video_completions=int(total_impressions * 0.7) # Assume 70% VCR
        ),
        by_package=package_delivery,
        currency="USD"
    )

@mcp.tool
def update_media_buy_performance_index(
    media_buy_id: str,
    package_performance: List[PackagePerformance],
    today: Optional[str] = None,
) -> UpdateMediaBuyPerformanceIndexResponse:
    """Update the performance index for a media buy."""
    if media_buy_id not in media_buys:
        raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")
    
    media_buy = media_buys[media_buy_id]
    for perf in package_performance:
        for pkg in media_buy["media_packages"]:
            if pkg["package_id"] == perf.package_id:
                pkg["performance_index"] = perf.performance_index
                break
                
    return UpdateMediaBuyPerformanceIndexResponse(acknowledged=True)

@mcp.tool
def update_media_buy(
    media_buy_id: str,
    action: str,
    package_id: Optional[str] = None,
    budget: Optional[int] = None,
    today: Optional[str] = None,
) -> UpdateMediaBuyResponse:
    """Update a media buy with various actions."""
    if media_buy_id not in media_buys:
        raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")
    
    media_buy = media_buys[media_buy_id]
    
    if action == "change_package_budget" and package_id and budget is not None:
        for pkg in media_buy["media_packages"]:
            if pkg["package_id"] == package_id:
                pkg["budget"] = budget
                break
        # Recalculate total budget
        media_buy["total_budget"] = sum(pkg["budget"] for pkg in media_buy["media_packages"])
    else:
        raise ValueError(f"Action '{action}' not supported by this mock server.")

    return UpdateMediaBuyResponse(
        status="accepted",
        implementation_date=(datetime.fromisoformat(today) + timedelta(days=1)).isoformat() if today else datetime.now().isoformat()
    )


if __name__ == "__main__":
    mcp.run()
