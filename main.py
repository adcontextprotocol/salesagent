import sqlite3
import json
import importlib
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import google.generativeai as genai
from fastmcp import FastMCP
from rich.console import Console
from rich.pretty import Pretty

from database import init_db
from schemas import *
from adapters.base import AdServerAdapter

# --- Configuration and Initialization ---

def load_config():
    """Loads the application configuration from config.json."""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: config.json not found. Please create it.")
        exit(1)
    except json.JSONDecodeError:
        print("Error: Could not decode config.json. Please check its format.")
        exit(1)

def initialize_services(config: Dict[str, Any]):
    """Initializes and configures all external services."""
    # Configure Gemini AI
    api_key = config.get("gemini_api_key")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("Error: Gemini API key not found in config.json. Please add it.")
        exit(1)
    genai.configure(api_key=api_key)

    # Initialize the database
    init_db()

def load_ad_server_adapter(config: Dict[str, Any]) -> AdServerAdapter:
    """Dynamically loads and instantiates the ad server adapter."""
    adapter_name = config.get("ad_server", {}).get("adapter")
    if not adapter_name:
        print("Error: Ad server adapter not specified in config.json.")
        exit(1)
    
    try:
        module = importlib.import_module(f"adapters.{adapter_name}")
        # Assumes the class name is the CamelCase version of the module name
        class_name = ''.join(word.capitalize() for word in adapter_name.split('_'))
        adapter_class = getattr(module, class_name)
        return adapter_class(config.get("ad_server", {}))
    except (ImportError, AttributeError) as e:
        print(f"Error loading ad server adapter '{adapter_name}': {e}")
        exit(1)

# --- Main Application Setup ---
config = load_config()
initialize_services(config)
ad_server = load_ad_server_adapter(config)

model = genai.GenerativeModel('gemini-2.5-flash')
mcp = FastMCP(name="AdCPSalesAgent")
console = Console()

# --- In-Memory Proposal Cache (Temporary) ---
proposals_cache: Dict[str, Proposal] = {}

# --- MCP Tools ---

@mcp.tool
def get_proposal(
    brief: str,
    provided_signals: Optional[List[ProvidedSignal]] = None,
    proposal_id: Optional[str] = None,
    requested_changes: Optional[List[RequestedChange]] = None,
    today: Optional[datetime] = None,
) -> Proposal:
    """Request a proposal from the publisher by intelligently selecting inventory."""
    today = today or datetime.now().astimezone()
    conn = sqlite3.connect('adcp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM placements")
    placements = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM audiences")
    audiences = [dict(row) for row in cursor.fetchall()]
    
    inventory_json = json.dumps({"placements": placements, "audiences": audiences}, indent=2)
    provided_signals_dict = [signal.model_dump() for signal in provided_signals] if provided_signals else []
    provided_signals_json = json.dumps(provided_signals_dict, indent=2) if provided_signals_dict else "None"

    prompt = f"""
    You are an expert media planner. Your task is to create a media proposal based on a client brief and available inventory.
    Client Brief: "{brief}"
    Provided Signals: {provided_signals_json}
    Available Inventory: {inventory_json}
    Today's Date: {today.strftime('%Y-%m-%d')}
    Your task is to select the most relevant placements and allocate a budget for each.
    Your response MUST be a JSON object with "start_time", "end_time", and "selected_placements" keys.
    Example: {{ "start_time": "2025-07-25T00:00:00Z", "end_time": "2025-08-25T23:59:59Z", "selected_placements": [{{ "placement_id": 1, "budget": 50000 }}] }}
    Return only the JSON object.
    """

    try:
        response = model.generate_content(prompt)
        clean_json_str = response.text.strip().replace("```json", "").replace("```", "").strip()
        ai_decision = json.loads(clean_json_str)
        
        selected_placements = ai_decision.get("selected_placements", [])
        start_time_str = ai_decision.get("start_time")
        end_time_str = ai_decision.get("end_time")

        if not all([selected_placements, start_time_str, end_time_str]):
            raise ValueError("AI response missing required fields.")

        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)

        media_packages = []
        creative_formats_dict = {}
        total_budget = 0

        for selection in selected_placements:
            cursor.execute("SELECT p.*, prop.name as property_name FROM placements p JOIN properties prop ON p.property_id = prop.id WHERE p.id = ?", (selection['placement_id'],))
            placement_details = cursor.fetchone()
            
            # ... (rest of the package creation logic is the same)
            package = MediaPackage(
                package_id=f"pkg_{placement_details['id']}",
                name=f"{placement_details['property_name']} - {placement_details['name']}",
                description=f"Targeting on {placement_details['property_name']}",
                delivery_restrictions="US",
                provided_signals=ProvidedSignalsInPackage(included_ids=[], excluded_ids=[]),
                cpm=placement_details['base_cpm'],
                budget=selection['budget'],
                budget_capacity=100000,
                creative_formats=str(placement_details['id']) # Simplified
            )
            media_packages.append(package)
            total_budget += selection['budget']

        conn.close()

        proposal = Proposal(
            proposal_id=f"proposal_{int(datetime.now().timestamp())}",
            total_budget=total_budget,
            currency="USD",
            start_time=start_time,
            end_time=end_time,
            notes="Proposal generated by AI media planner.",
            creative_formats=[], # Simplified for now
            media_packages=media_packages
        )
        proposals_cache[proposal.proposal_id] = proposal
        return proposal

    except (Exception, json.JSONDecodeError, ValueError) as e:
        print(f"Error processing AI proposal: {e}")
        raise ValueError("Failed to generate or process the AI's proposal selection.")

@mcp.tool
def accept_proposal(
    proposal_id: str,
    accepted_packages: List[str],
    billing_entity: str,
    po_number: str,
    today: Optional[datetime] = None,
) -> AcceptProposalResponse:
    """Accept a proposal and convert it into a media buy."""
    today = today or datetime.now().astimezone()
    if proposal_id not in proposals_cache:
        raise ValueError(f"Proposal with ID '{proposal_id}' not found or expired.")
    
    proposal = proposals_cache[proposal_id]
    
    # Delegate to the ad server adapter
    response = ad_server.accept_proposal(proposal, accepted_packages, billing_entity, po_number, today)
    
    # Clean up the cache
    del proposals_cache[proposal_id]
    
    console.print(f"[bold cyan]Ad Server Response:[/bold cyan] {response}")
    return response

@mcp.tool
def add_creative_assets(
    media_buy_id: str,
    assets: List[CreativeAsset],
    today: Optional[datetime] = None,
) -> AddCreativeAssetsResponse:
    """Add creative assets to a media buy."""
    today = today or datetime.now().astimezone()
    asset_dicts = [asset.model_dump() for asset in assets]
    
    # Delegate to the ad server adapter
    updated_assets = ad_server.add_creative_assets(media_buy_id, asset_dicts, today)
    
    return AddCreativeAssetsResponse(status="received", assets=updated_assets)

@mcp.tool
def check_media_buy_status(
    media_buy_id: str, 
    today: Optional[datetime] = None
) -> CheckMediaBuyStatusResponse:
    """Check the status of a media buy."""
    today = today or datetime.now().astimezone()
    return ad_server.check_media_buy_status(media_buy_id, today)

@mcp.tool
def get_media_buy_delivery(
    media_buy_id: str,
    date_range: ReportingPeriod,
    today: Optional[datetime] = None,
) -> GetMediaBuyDeliveryResponse:
    """Get the delivery data for a media buy."""
    today = today or datetime.now().astimezone()
    return ad_server.get_media_buy_delivery(media_buy_id, date_range, today)

@mcp.tool
def update_media_buy_performance_index(
    media_buy_id: str,
    package_performance: List[PackagePerformance],
    today: Optional[datetime] = None,
) -> UpdateMediaBuyPerformanceIndexResponse:
    """Update the performance index for a media buy."""
    acknowledged = ad_server.update_media_buy_performance_index(media_buy_id, package_performance)
    return UpdateMediaBuyPerformanceIndexResponse(acknowledged=acknowledged)

@mcp.tool
def update_media_buy(
    media_buy_id: str,
    action: str,
    package_id: Optional[str] = None,
    budget: Optional[int] = None,
    today: Optional[datetime] = None,
) -> UpdateMediaBuyResponse:
    """Update a media buy with various actions."""
    today = today or datetime.now().astimezone()
    return ad_server.update_media_buy(media_buy_id, action, package_id, budget, today)

if __name__ == "__main__":
    mcp.run()