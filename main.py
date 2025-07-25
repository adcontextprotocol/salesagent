import sqlite3
import json
import importlib
from datetime import datetime
from typing import List, Dict, Any

from fastmcp import FastMCP
from rich.console import Console

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
        print("Error: config.json not found. Please create it by copying config.json.sample.")
        exit(1)
    except json.JSONDecodeError:
        print("Error: Could not decode config.json. Please check its format.")
        exit(1)

def initialize_services():
    """Initializes the database."""
    init_db()

def load_adapter(adapter_type: str, config: Dict[str, Any], **kwargs) -> Any:
    """Dynamically loads and instantiates a specified adapter."""
    adapter_config = config.get(adapter_type, {})
    adapter_name = adapter_config.get("adapter")
    if not adapter_name:
        print(f"Error: {adapter_type} adapter not specified in config.json.")
        exit(1)
    
    try:
        module = importlib.import_module(f"adapters.{adapter_name}")
        class_name = ''.join(word.capitalize() for word in adapter_name.split('_'))
        adapter_class = getattr(module, class_name)
        return adapter_class(adapter_config, **kwargs)
    except (ImportError, AttributeError) as e:
        print(f"Error loading {adapter_type} adapter '{adapter_name}': {e}")
        exit(1)

# --- Main Application Setup ---
config = load_config()
initialize_services()

# For V2, we assume a single ad server is configured for the buy-side agent
ad_server: AdServerAdapter = load_adapter("ad_server", config)

mcp = FastMCP(name="AdCPBuySideV2")
console = Console()

# --- In-Memory Cache (Temporary) ---
# Caches the packages returned from a get_packages call to be used in create_media_buy
packages_cache: Dict[str, List[MediaPackage]] = {}

# --- MCP Tools (V2) ---

def _check_creative_compatibility(creative: CreativeAsset, placement_formats: List[Dict[str, Any]]) -> CreativeCompatibility:
    """Checks if a creative is compatible with the formats supported by a placement."""
    for format_spec in placement_formats:
        spec = json.loads(format_spec['spec'])
        # This is a simplified compatibility check. A real implementation would be more robust.
        if (creative.media_type == spec.get('media_type') and
            creative.w == spec.get('w') and
            creative.h == spec.get('h')):
            return CreativeCompatibility(compatible=True, requires_approval=True) # Defaulting to requires_approval
    
    return CreativeCompatibility(
        compatible=False, 
        requires_approval=False,
        reason=f"Creative dimensions ({creative.w}x{creative.h}) or type do not match any supported format."
    )

@mcp.tool
def get_packages(request: GetPackagesRequest) -> GetPackagesResponse:
    """Discover all available packages based on media buy criteria."""
    conn = sqlite3.connect('adcp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # For now, we return all catalog packages. A real implementation would filter based on request.
    cursor.execute("SELECT * FROM placements WHERE type = 'catalog'")
    placements = [dict(row) for row in cursor.fetchall()]
    
    media_packages = []
    for placement in placements:
        # Get the creative formats supported by this placement
        cursor.execute("""
            SELECT cf.spec FROM creative_formats cf
            JOIN placement_formats pf ON cf.id = pf.format_id
            WHERE pf.placement_id = ?
        """, (placement['id'],))
        supported_formats = [dict(row) for row in cursor.fetchall()]

        # Check compatibility for each creative provided in the request
        compatibility_map = {}
        for creative in request.creatives:
            compatibility_map[creative.id] = _check_creative_compatibility(creative, supported_formats)

        package_data = {
            "package_id": f"pkg_{placement['id']}",
            "name": placement['name'],
            "description": f"A {placement['delivery_type']} package.",
            "type": placement['type'],
            "delivery_type": placement['delivery_type'],
            "creative_compatibility": compatibility_map,
        }

        if placement['delivery_type'] == 'guaranteed':
            package_data['cpm'] = placement['base_cpm']
        else:
            package_data['pricing'] = json.loads(placement['pricing_guidance'])

        media_packages.append(MediaPackage(**package_data))

    conn.close()
    
    # Cache the packages for the create_media_buy step
    query_id = f"query_{int(datetime.now().timestamp())}"
    packages_cache[query_id] = media_packages
    
    # We need a way to return the query_id to the client.
    # For now, we'll print it and assume the client can use it.
    console.print(f"[bold yellow]Generated Query ID for this package set:[/bold yellow] {query_id}")

    return GetPackagesResponse(packages=media_packages)

@mcp.tool
def create_media_buy(request: CreateMediaBuyRequest, query_id: str) -> CreateMediaBuyResponse:
    """Create a media buy from a set of selected packages."""
    if query_id not in packages_cache:
        raise ValueError(f"Query ID '{query_id}' not found or expired.")
    
    available_packages = {p.package_id: p for p in packages_cache[query_id]}
    
    # This would be passed to the ad server adapter in a real implementation
    selected_packages_full = []
    for selected in request.selected_packages:
        if selected.package_id not in available_packages:
            raise ValueError(f"Package ID '{selected.package_id}' not found in the original query.")
        
        full_package = available_packages[selected.package_id]
        # Here you would combine the full package data with the user's bid (max_cpm)
        # and pass it to a new ad_server.create_media_buy method.
        selected_packages_full.append(full_package)

    # For this simulation, we'll just return a success response.
    # The ad_server.create_media_buy call would happen here.
    
    media_buy_id = f"mb_{int(datetime.now().timestamp())}"
    console.print(f"Simulating media buy creation for PO: {request.po_number}. Media Buy ID: {media_buy_id}")
    
    del packages_cache[query_id] # Clean up cache

    return CreateMediaBuyResponse(
        media_buy_id=media_buy_id,
        status="pending_activation", # A more complex status would be determined by the adapter
        creative_deadline=datetime.now() + timedelta(days=2)
    )

# --- Other Tools (to be updated or removed) ---

@mcp.tool
def add_creative_assets(media_buy_id: str, assets: List[CreativeAsset]) -> AddCreativeAssetsResponse:
    """Submits creative assets to the ad server for processing."""
    asset_dicts = [asset.model_dump() for asset in assets]
    submitted_assets = ad_server.add_creative_assets(media_buy_id, asset_dicts, datetime.now())
    return AddCreativeAssetsResponse(status="submitted", assets=submitted_assets)

@mcp.tool
def check_media_buy_status(media_buy_id: str) -> CheckMediaBuyStatusResponse:
    """Check the status of a media buy."""
    return ad_server.check_media_buy_status(media_buy_id, datetime.now())

if __name__ == "__main__":
    mcp.run()