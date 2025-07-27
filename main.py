import json
import os
import sqlite3
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_http_request
from starlette.requests import Request
from rich.console import Console

from adapters.mock_creative_engine import MockCreativeEngine
from database import init_db
from mock_ad_server import MockAdServer
from schemas import *

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

# --- Initialization ---
init_db()
mcp = FastMCP(name="AdCPBuySideV2_3_CustomAuth_Final")
console = Console()
creative_engine = MockCreativeEngine({})

# --- In-Memory State ---
media_buys: Dict[str, Tuple[CreateMediaBuyRequest, str]] = {}
creative_assignments: Dict[str, Dict[str, List[str]]] = {}
creative_statuses: Dict[str, CreativeStatus] = {}
product_catalog: List[Product] = []

# --- Dry Run Mode ---
DRY_RUN_MODE = os.getenv("ADCP_DRY_RUN", "false").lower() == "true"
dry_run_logs: List[str] = []
if DRY_RUN_MODE:
    console.print("[bold yellow]🏃 DRY RUN MODE ENABLED - Adapter calls will be logged[/bold yellow]")

def log_dry_run(action: str, details: Dict[str, Any]):
    """Log actions that would be taken in dry run mode."""
    if DRY_RUN_MODE:
        log_entry = f"[DRY RUN] {action}: {json.dumps(details, default=str)}"
        dry_run_logs.append(log_entry)
        console.print(f"[dim]{log_entry}[/dim]")

# --- Security Helper ---
def _get_principal_id_from_context(context: Context) -> str:
    """Extracts the token from the header and returns a principal_id."""
    http_request: Request = get_http_request()
    token = http_request.headers.get("x-adcp-auth")
    if not token:
        raise ToolError("Missing x-adcp-auth header for authentication.")
    
    principal_id = get_principal_from_token(token)
    if not principal_id:
        raise PermissionError("Invalid token in x-adcp-auth header.")
    
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
    media_buy_id = f"mb_{uuid.uuid4().hex[:8]}"
    media_buys[media_buy_id] = (req, principal_id)
    
    # Log what adapter calls would be made
    log_dry_run("AdServerAdapter.create_campaign", {
        "adapter": "MockAdServer",
        "principal": principal_id,
        "products": req.product_ids,
        "budget": req.total_budget,
        "flight_dates": f"{req.flight_start_date} to {req.flight_end_date}",
        "targeting": req.targeting_overlay
    })
    
    if req.creatives:
        log_dry_run("CreativeEngine.submit_creatives", {
            "engine": "MockCreativeEngine",
            "creative_count": len(req.creatives),
            "creative_ids": [c.creative_id for c in req.creatives]
        })
        statuses = creative_engine.process_creatives(req.creatives)
        for status in statuses: creative_statuses[status.creative_id] = status
    
    return CreateMediaBuyResponse(media_buy_id=media_buy_id, status="created", detail="Media buy created.")

@mcp.tool
def submit_creatives(req: SubmitCreativesRequest, context: Context) -> SubmitCreativesResponse:
    _verify_principal(req.media_buy_id, context)
    
    log_dry_run("CreativeEngine.process_creatives", {
        "media_buy_id": req.media_buy_id,
        "creatives": [{"id": c.creative_id, "format": c.format_id} for c in req.creatives]
    })
    
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
    buy_request, _ = media_buys[req.media_buy_id]
    catalog = get_product_catalog()
    products_in_buy = [p for p in catalog if p.product_id in buy_request.product_ids]
    
    log_dry_run("AdServerAdapter.get_delivery_report", {
        "adapter": "MockAdServer",
        "media_buy_id": req.media_buy_id,
        "reporting_date": str(req.today),
        "products": buy_request.product_ids
    })
    
    ad_server = MockAdServer(buy_request, products_in_buy)
    delivery = ad_server.get_delivery_status(req.today)
    return GetMediaBuyDeliveryResponse(media_buy_id=req.media_buy_id, **delivery)

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
    
    # In a real implementation, this would send the performance data to the ad server
    # For simulation, we'll log it and acknowledge receipt
    buy_request, _ = media_buys[req.media_buy_id]
    
    console.print(f"[bold green]Performance Index Update for {req.media_buy_id}:[/bold green]")
    for perf in req.performance_data:
        status_emoji = "📈" if perf.performance_index > 1.0 else "📉" if perf.performance_index < 1.0 else "➡️"
        console.print(f"  {status_emoji} {perf.product_id}: {perf.performance_index:.2f} (confidence: {perf.confidence_score or 'N/A'})")
    
    # Simulate optimization based on performance
    if any(p.performance_index < 0.8 for p in req.performance_data):
        console.print("  [yellow]⚠️  Low performance detected - optimization recommended[/yellow]")
    
    return UpdatePerformanceIndexResponse(
        status="success", 
        detail=f"Performance index updated for {len(req.performance_data)} products"
    )

@mcp.tool  
def get_dry_run_logs(context: Context) -> Dict[str, List[str]]:
    """Retrieve dry run logs showing what adapter calls would have been made."""
    _get_principal_id_from_context(context)  # Authenticate
    return {"dry_run_logs": dry_run_logs}

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
    # Run the FastMCP server as HTTP server
    mcp.run(transport="http", host="127.0.0.1", port=8000)
