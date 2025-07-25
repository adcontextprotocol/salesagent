import json
from datetime import datetime, date, timedelta
import uuid
import sqlite3

from fastmcp import FastMCP
from rich.console import Console

from database import init_db
from mock_ad_server import MockAdServer
from adapters.mock_creative_engine import MockCreativeEngine
from schemas import *

# --- Configuration and Initialization ---
config = {"gemini_api_key": None, "creative_engine": {}}
init_db()
mcp = FastMCP(name="AdCPBuySideV2_3_Final")
console = Console()
creative_engine = MockCreativeEngine(config.get("creative_engine", {}))

# --- In-Memory State ---
media_buys: Dict[str, CreateMediaBuyRequest] = {}
creative_assignments: Dict[str, Dict[str, List[str]]] = {}
creative_statuses: Dict[str, CreativeStatus] = {}
product_catalog: List[Product] = []
custom_products: Dict[str, Product] = {}

# --- Helper Functions ---
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

# --- MCP Tools (V2.3 Final Lifecycle) ---

@mcp.tool
def list_products(req: ListProductsRequest) -> ListProductsResponse:
    console.print(f"\n[green]Received list_products for principal '{req.principal_id}'[/green]")
    catalog = get_product_catalog()
    # In a real system, this would involve an LLM call to select products.
    # For simulation, we return a mix of guaranteed and non-guaranteed.
    return ListProductsResponse(products=catalog)

@mcp.tool
def create_media_buy(req: CreateMediaBuyRequest) -> CreateMediaBuyResponse:
    console.print(f"\n[green]Received create_media_buy for PO# {req.po_number or 'N/A'} with '{req.pacing}' pacing.[/green]")
    media_buy_id = f"mb_{uuid.uuid4().hex[:8]}"
    media_buys[media_buy_id] = req
    
    if req.creatives:
        statuses = creative_engine.process_creatives(req.creatives)
        for status in statuses:
            creative_statuses[status.creative_id] = status
        console.print(f"Submitted {len(req.creatives)} initial creatives for processing.")
        
    return CreateMediaBuyResponse(media_buy_id=media_buy_id, status="created", detail="Media buy created.")

@mcp.tool
def submit_creatives(req: SubmitCreativesRequest) -> SubmitCreativesResponse:
    console.print(f"\n[green]Received submit_creatives for buy {req.media_buy_id}[/green]")
    if req.media_buy_id not in media_buys:
        raise ValueError("Media buy not found.")
    
    statuses = creative_engine.process_creatives(req.creatives)
    for status in statuses:
        creative_statuses[status.creative_id] = status
        
    return SubmitCreativesResponse(statuses=statuses)

@mcp.tool
def check_creative_status(req: CheckCreativeStatusRequest) -> CheckCreativeStatusResponse:
    console.print(f"\n[green]Checking status for creatives: {req.creative_ids}[/green]")
    statuses = [creative_statuses.get(cid) for cid in req.creative_ids if cid in creative_statuses]
    return CheckCreativeStatusResponse(statuses=statuses)

@mcp.tool
def adapt_creative(req: AdaptCreativeRequest) -> CreativeStatus:
    console.print(f"\n[green]Adapting creative {req.original_creative_id} to format {req.target_format_id}[/green]")
    status = creative_engine.adapt_creative(req)
    creative_statuses[req.new_creative_id] = status
    return status

@mcp.tool
def update_media_buy(req: UpdateMediaBuyRequest):
    console.print(f"\n[green]Updating media buy {req.media_buy_id}[/green]")
    buy = media_buys.get(req.media_buy_id)
    if not buy:
        raise ValueError("Media buy not found.")
    
    if req.new_total_budget:
        console.print(f"Budget updated to ${req.new_total_budget}")
        buy.total_budget = req.new_total_budget
    if req.new_targeting_overlay:
        console.print(f"Targeting overlay updated.")
        buy.targeting_overlay = req.new_targeting_overlay
    if req.creative_assignments:
        console.print(f"Creative assignments updated for {len(req.creative_assignments)} products.")
        creative_assignments[req.media_buy_id] = req.creative_assignments
        
    return {"status": "success", "detail": "Media buy updated."}

@mcp.tool
def get_media_buy_delivery(media_buy_id: str, today: date) -> GetMediaBuyDeliveryResponse:
    buy = media_buys.get(media_buy_id)
    if not buy:
        raise ValueError("Media buy not found.")
    
    catalog = get_product_catalog()
    products_in_buy = [p for p in catalog if p.product_id in buy.product_ids]
    
    ad_server = MockAdServer(buy, products_in_buy)
    delivery = ad_server.get_delivery_status(today)
    
    return GetMediaBuyDeliveryResponse(media_buy_id=media_buy_id, **delivery)

if __name__ == "__main__":
    get_product_catalog()
    mcp.run()
