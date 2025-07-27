import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from rich.console import Console

from adapters.mock_creative_engine import MockCreativeEngine
from adapters.mock_ad_server import MockAdServer as MockAdServerAdapter
from adapters.google_ad_manager import GoogleAdManager
from database import init_db
from schemas import *
from config_loader import load_config

# --- Authentication ---
DB_FILE = "adcp.db"

def get_principal_from_token(token: str) -> Optional[str]:
    """Looks up a principal_id from the database using a token."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT principal_id FROM principals WHERE access_token = ?", (token,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_principal_from_context(context: Optional[Context]) -> Optional[str]:
    """Extract principal ID from the FastMCP context using x-adcp-auth header."""
    if not context:
        return None
    
    try:
        # Get the HTTP request from context
        request = context.get_http_request()
        if not request:
            return None
        
        # Get the x-adcp-auth header
        auth_token = request.headers.get('x-adcp-auth')
        if not auth_token:
            return None
        
        # Validate token and get principal
        return get_principal_from_token(auth_token)
    except Exception as e:
        print(f"Auth error: {e}")
        return None

def get_principal_adapter_mapping(principal_id: str) -> Dict[str, Any]:
    """Get the platform mappings for a principal."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT platform_mappings FROM principals WHERE principal_id = ?", (principal_id,))
    result = cursor.fetchone()
    conn.close()
    return json.loads(result[0]) if result else {}

def get_principal_object(principal_id: str) -> Optional[Principal]:
    """Get a Principal object for the given principal_id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT principal_id, name, platform_mappings FROM principals WHERE principal_id = ?", (principal_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return Principal(
            principal_id=result[0],
            name=result[1],
            platform_mappings=json.loads(result[2])
        )
    return None

def get_adapter_principal_id(principal_id: str, adapter: str) -> Optional[str]:
    """Get the adapter-specific ID for a principal."""
    mappings = get_principal_adapter_mapping(principal_id)
    
    # Map adapter names to their specific fields
    adapter_field_map = {
        "gam": "gam_advertiser_id",
        "kevel": "kevel_advertiser_id", 
        "triton": "triton_advertiser_id",
        "mock": "mock_advertiser_id"
    }
    
    field_name = adapter_field_map.get(adapter)
    if field_name:
        return str(mappings.get(field_name, "")) if mappings.get(field_name) else None
    return None

def get_adapter(principal: Principal, dry_run: bool = False):
    """Get the appropriate adapter instance for the selected adapter type."""
    # Get adapter config from global config
    adapter_config = config.get('ad_server', {})
    
    if SELECTED_ADAPTER == "mock":
        return MockAdServerAdapter(adapter_config, principal, dry_run)
    elif SELECTED_ADAPTER == "gam":
        # Get GAM-specific config
        gam_config = config.get('gam', {})
        adapter_config.update(gam_config)
        
        # Provide mock config for dry-run mode if needed
        if dry_run and not adapter_config.get('network_code'):
            adapter_config = {
                'network_code': '123456789',
                'service_account_key_file': '/path/to/service-account.json',
                'company_id': '987654321',
                'trafficker_id': '555555555'
            }
        return GoogleAdManager(adapter_config, principal, dry_run)
    elif SELECTED_ADAPTER in ["triton", "triton_digital"]:
        # Triton uses the base ad_server config
        return MockAdServerAdapter(adapter_config, principal, dry_run)  # Replace with TritonAdapter when ready
    else:
        # Default to mock for unsupported adapters
        return MockAdServerAdapter(adapter_config, principal, dry_run)

# --- Initialization ---
init_db()
config = load_config()
mcp = FastMCP(name="AdCPSalesAgent")
console = Console()
creative_engine = MockCreativeEngine({})

# --- In-Memory State ---
media_buys: Dict[str, Tuple[CreateMediaBuyRequest, str]] = {}
creative_assignments: Dict[str, Dict[str, List[str]]] = {}
creative_statuses: Dict[str, CreativeStatus] = {}
product_catalog: List[Product] = []

# --- Adapter Configuration ---
# Get adapter from config, fallback to mock
SELECTED_ADAPTER = config.get('ad_server', {}).get('adapter', 'mock').lower()
AVAILABLE_ADAPTERS = ["mock", "gam", "kevel", "triton", "triton_digital"]

# --- Dry Run Mode ---
DRY_RUN_MODE = config.get('dry_run', False)
if DRY_RUN_MODE:
    console.print("[bold yellow]🏃 DRY RUN MODE ENABLED - Adapter calls will be logged[/bold yellow]")

# Display selected adapter
if SELECTED_ADAPTER not in AVAILABLE_ADAPTERS:
    console.print(f"[bold red]❌ Invalid adapter '{SELECTED_ADAPTER}'. Using 'mock' instead.[/bold red]")
    SELECTED_ADAPTER = "mock"
console.print(f"[bold cyan]🔌 Using adapter: {SELECTED_ADAPTER.upper()}[/bold cyan]")

# --- Security Helper ---
def _get_principal_id_from_context(context: Context) -> str:
    """Extracts the token from the header and returns a principal_id."""
    principal_id = get_principal_from_context(context)
    if not principal_id:
        raise ToolError("Missing or invalid x-adcp-auth header for authentication.")
    
    console.print(f"[bold green]Authenticated principal '{principal_id}'[/bold green]")
    return principal_id

def _verify_principal(media_buy_id: str, context: Context):
    principal_id = _get_principal_id_from_context(context)
    if media_buy_id not in media_buys:
        raise ValueError(f"Media buy '{media_buy_id}' not found.")
    if media_buys[media_buy_id][1] != principal_id:
        raise PermissionError(f"Principal '{principal_id}' does not own media buy '{media_buy_id}'.")

# --- MCP Tools (Full Implementation) ---

@mcp.tool
def list_products(req: ListProductsRequest, context: Context) -> ListProductsResponse:
    _get_principal_id_from_context(context) # Authenticate
    return ListProductsResponse(products=get_product_catalog())

@mcp.tool
def create_media_buy(req: CreateMediaBuyRequest, context: Context) -> CreateMediaBuyResponse:
    principal_id = _get_principal_id_from_context(context)
    
    # Get the Principal object
    principal = get_principal_object(principal_id)
    if not principal:
        raise ToolError(f"Principal {principal_id} not found")
    
    # Get the appropriate adapter
    adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
    
    # Get products for the media buy
    catalog = get_product_catalog()
    products_in_buy = [p for p in catalog if p.product_id in req.product_ids]
    
    # Convert products to MediaPackages (simplified for now)
    packages = []
    for product in products_in_buy:
        # Use the first format for now
        format_info = product.formats[0] if product.formats else None
        packages.append(MediaPackage(
            package_id=product.product_id,
            name=product.name,
            delivery_type=product.delivery_type,
            cpm=product.cpm if product.cpm else 10.0,  # Default CPM
            impressions=int(req.total_budget / (product.cpm if product.cpm else 10.0) * 1000),
            format_ids=[format_info.format_id] if format_info else []
        ))
    
    # Create the media buy using the adapter
    start_time = datetime.combine(req.flight_start_date, datetime.min.time())
    end_time = datetime.combine(req.flight_end_date, datetime.max.time())
    response = adapter.create_media_buy(req, packages, start_time, end_time)
    
    # Store the media buy
    media_buys[response.media_buy_id] = (req, principal_id)
    
    # Handle creatives if provided
    if req.creatives:
        # Convert Creative to asset format expected by adapter
        assets = []
        for creative in req.creatives:
            assets.append({
                'id': creative.creative_id,
                'name': f"Creative {creative.creative_id}",
                'format': 'image',  # Simplified - would need to determine from format_id
                'media_url': creative.content_uri,
                'click_url': 'https://example.com',  # Placeholder
                'package_assignments': req.product_ids
            })
        statuses = adapter.add_creative_assets(response.media_buy_id, assets, datetime.now())
        for status in statuses:
            creative_statuses[status.creative_id] = CreativeStatus(
                creative_id=status.creative_id,
                status="approved" if status.status == "approved" else "pending_review",
                detail="Creative submitted to ad server"
            )
    
    return response

@mcp.tool
def submit_creatives(req: SubmitCreativesRequest, context: Context) -> SubmitCreativesResponse:
    _verify_principal(req.media_buy_id, context)
    
    # Process creatives through the creative engine
    statuses = creative_engine.process_creatives(req.creatives)
    for status in statuses: creative_statuses[status.creative_id] = status
    return SubmitCreativesResponse(statuses=statuses)

@mcp.tool
def check_creative_status(req: CheckCreativeStatusRequest, context: Context) -> CheckCreativeStatusResponse:
    statuses = [creative_statuses.get(cid) for cid in req.creative_ids if cid in creative_statuses]
    return CheckCreativeStatusResponse(statuses=statuses)

@mcp.tool
def adapt_creative(req: AdaptCreativeRequest, context: Context) -> CreativeStatus:
    _verify_principal(req.media_buy_id, context)
    status = creative_engine.adapt_creative(req)
    creative_statuses[req.new_creative_id] = status
    return status

@mcp.tool
def update_media_buy(req: UpdateMediaBuyRequest, context: Context):
    _verify_principal(req.media_buy_id, context)
    buy_request, _ = media_buys[req.media_buy_id]
    if req.new_total_budget: buy_request.total_budget = req.new_total_budget
    if req.new_targeting_overlay: buy_request.targeting_overlay = req.new_targeting_overlay
    if req.creative_assignments: creative_assignments[req.media_buy_id] = req.creative_assignments
    return {"status": "success"}

@mcp.tool
def get_media_buy_delivery(req: GetMediaBuyDeliveryRequest, context: Context) -> GetMediaBuyDeliveryResponse:
    _verify_principal(req.media_buy_id, context)
    buy_request, principal_id = media_buys[req.media_buy_id]
    
    # Get the Principal object
    principal = get_principal_object(principal_id)
    if not principal:
        raise ToolError(f"Principal {principal_id} not found")
    
    # Get the appropriate adapter
    adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
    
    # Create a ReportingPeriod for the adapter
    reporting_period = ReportingPeriod(
        start=datetime.combine(req.today - timedelta(days=1), datetime.min.time()),
        end=datetime.combine(req.today, datetime.min.time()),
        start_date=req.today - timedelta(days=1),
        end_date=req.today
    )
    
    # Get delivery data from the adapter
    # Use the requested date for simulation, not the current time
    simulation_datetime = datetime.combine(req.today, datetime.min.time())
    delivery_response = adapter.get_media_buy_delivery(req.media_buy_id, reporting_period, simulation_datetime)
    
    # Convert adapter response to expected format
    # Calculate totals from the adapter response
    total_spend = delivery_response.totals.spend if hasattr(delivery_response, 'totals') else 0
    total_impressions = delivery_response.totals.impressions if hasattr(delivery_response, 'totals') else 0
    
    # Calculate days elapsed
    days_elapsed = (req.today - buy_request.flight_start_date).days
    total_days = (buy_request.flight_end_date - buy_request.flight_start_date).days
    
    # Determine pacing
    expected_spend = (buy_request.total_budget / total_days) * days_elapsed if total_days > 0 else 0
    if total_spend > expected_spend * 1.1:
        pacing = "ahead"
    elif total_spend < expected_spend * 0.9:
        pacing = "behind"
    else:
        pacing = "on_track"
    
    # Determine status
    if req.today < buy_request.flight_start_date:
        status = "pending_start"
    elif req.today > buy_request.flight_end_date:
        status = "completed"
    else:
        status = "delivering"
    
    return GetMediaBuyDeliveryResponse(
        media_buy_id=req.media_buy_id,
        status=status,
        spend=total_spend,
        impressions=total_impressions,
        pacing=pacing,
        days_elapsed=days_elapsed,
        total_days=total_days
    )

@mcp.tool
def get_principal_summary(context: Context) -> GetPrincipalSummaryResponse:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT principal_id, name, platform_mappings FROM principals")
    rows = cursor.fetchall()
    conn.close()
    summaries = [PrincipalSummary(
        principal_id=row[0], name=row[1], platform_mappings=json.loads(row[2]),
        live_media_buys=sum(1 for _, pid in media_buys.values() if pid == row[0]),
        total_spend=sum(br.total_budget for br, pid in media_buys.values() if pid == row[0])
    ) for row in rows]
    return GetPrincipalSummaryResponse(principals=summaries)

@mcp.tool
def update_performance_index(req: UpdatePerformanceIndexRequest, context: Context) -> UpdatePerformanceIndexResponse:
    _verify_principal(req.media_buy_id, context)
    buy_request, principal_id = media_buys[req.media_buy_id]
    
    # Get the Principal object
    principal = get_principal_object(principal_id)
    if not principal:
        raise ToolError(f"Principal {principal_id} not found")
    
    # Get the appropriate adapter
    adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
    
    # Convert ProductPerformance to PackagePerformance for the adapter
    package_performance = [
        PackagePerformance(
            package_id=perf.product_id,
            performance_index=perf.performance_index
        )
        for perf in req.performance_data
    ]
    
    # Call the adapter's update method
    success = adapter.update_media_buy_performance_index(req.media_buy_id, package_performance)
    
    # Log the performance update
    console.print(f"[bold green]Performance Index Update for {req.media_buy_id}:[/bold green]")
    for perf in req.performance_data:
        status_emoji = "📈" if perf.performance_index > 1.0 else "📉" if perf.performance_index < 1.0 else "➡️"
        console.print(f"  {status_emoji} {perf.product_id}: {perf.performance_index:.2f} (confidence: {perf.confidence_score or 'N/A'})")
    
    # Simulate optimization based on performance
    if any(p.performance_index < 0.8 for p in req.performance_data):
        console.print("  [yellow]⚠️  Low performance detected - optimization recommended[/yellow]")
    
    return UpdatePerformanceIndexResponse(
        status="success" if success else "failed", 
        detail=f"Performance index updated for {len(req.performance_data)} products"
    )

# Dry run logs are now handled by the adapters themselves

def get_product_catalog() -> List[Product]:
    global product_catalog
    if not product_catalog:
        conn = sqlite3.connect('adcp.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products")
        rows = cursor.fetchall()
        conn.close()
        
        loaded_products = []
        for row in rows:
            product_data = dict(row)
            product_data['formats'] = json.loads(product_data['formats'])
            product_data['targeting_template'] = json.loads(product_data['targeting_template'])
            if product_data.get('price_guidance'):
                product_data['price_guidance'] = json.loads(product_data['price_guidance'])
            loaded_products.append(Product(**product_data))
        product_catalog = loaded_products
    return product_catalog

if __name__ == "__main__":
    init_db()
    get_product_catalog()
    # Server is now run via run_server.py script
