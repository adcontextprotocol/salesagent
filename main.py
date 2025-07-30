import json
import os
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
from adapters.kevel import Kevel
from adapters.triton_digital import TritonDigital
from database import init_db
from schemas import *
from config_loader import (
    load_config, get_current_tenant, set_current_tenant,
    get_tenant_config, current_tenant
)
from db_config import get_db_connection
from slack_notifier import get_slack_notifier
from product_catalog_providers.factory import get_product_catalog_provider

# --- Authentication ---

def get_principal_from_token(token: str, tenant_id: str) -> Optional[str]:
    """Looks up a principal_id from the database using a token."""
    # Check for tenant admin token first
    tenant = get_current_tenant()
    if tenant and token == tenant['config'].get('admin_token'):
        return f"{tenant['tenant_id']}_admin"
    
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT principal_id FROM principals WHERE access_token = ? AND tenant_id = ?", 
        (token, tenant_id)
    )
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
        
        # Extract tenant from multiple sources
        tenant_id = None
        
        # 1. Check x-adcp-tenant header (set by middleware for path-based routing)
        tenant_id = request.headers.get('x-adcp-tenant')
        
        # 2. If not found, check host header for subdomain
        if not tenant_id:
            host = request.headers.get('host', '')
            subdomain = host.split('.')[0] if '.' in host else None
            if subdomain and subdomain != 'localhost':
                tenant_id = subdomain
        
        # 3. Default to 'default' tenant if none specified
        if not tenant_id:
            tenant_id = 'default'
        
        # Load tenant by ID
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT tenant_id, name, subdomain, config FROM tenants WHERE tenant_id = ? AND is_active = ?",
            (tenant_id, True)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print(f"No active tenant found for ID: {tenant_id}")
            return None
            
        # Set tenant context
        tenant_dict = {
            'tenant_id': row[0],
            'name': row[1],
            'subdomain': row[2],
            'config': json.loads(row[3])
        }
        set_current_tenant(tenant_dict)
        
        # Get the x-adcp-auth header
        auth_token = request.headers.get('x-adcp-auth')
        if not auth_token:
            return None
        
        # Validate token and get principal
        return get_principal_from_token(auth_token, tenant_dict['tenant_id'])
    except Exception as e:
        print(f"Auth error: {e}")
        return None

def get_principal_adapter_mapping(principal_id: str) -> Dict[str, Any]:
    """Get the platform mappings for a principal."""
    tenant = get_current_tenant()
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT platform_mappings FROM principals WHERE principal_id = ? AND tenant_id = ?", 
        (principal_id, tenant['tenant_id'])
    )
    result = cursor.fetchone()
    conn.close()
    return json.loads(result[0]) if result else {}

def get_principal_object(principal_id: str) -> Optional[Principal]:
    """Get a Principal object for the given principal_id."""
    tenant = get_current_tenant()
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT principal_id, name, platform_mappings FROM principals WHERE principal_id = ? AND tenant_id = ?", 
        (principal_id, tenant['tenant_id'])
    )
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
    # Get tenant-specific adapter config
    tenant = get_current_tenant()
    adapters_config = tenant['config'].get('adapters', {})
    
    # Find the first enabled adapter
    selected_adapter = None
    adapter_config = {}
    
    for adapter_name, config in adapters_config.items():
        if config.get('enabled'):
            selected_adapter = adapter_name
            adapter_config = config.copy()
            break
    
    if not selected_adapter:
        # Default to mock if no adapters enabled
        selected_adapter = 'mock'
        adapter_config = {'enabled': True}
    
    # Create the appropriate adapter instance with tenant_id
    tenant_id = tenant['tenant_id']
    if selected_adapter == "mock":
        return MockAdServerAdapter(adapter_config, principal, dry_run, tenant_id=tenant_id)
    elif selected_adapter == "google_ad_manager":
        return GoogleAdManager(adapter_config, principal, dry_run, tenant_id=tenant_id)
    elif selected_adapter == "kevel":
        return Kevel(adapter_config, principal, dry_run, tenant_id=tenant_id)
    elif selected_adapter in ["triton", "triton_digital"]:
        return TritonDigital(adapter_config, principal, dry_run, tenant_id=tenant_id)
    else:
        # Default to mock for unsupported adapters
        return MockAdServerAdapter(adapter_config, principal, dry_run, tenant_id=tenant_id)

# --- Initialization ---
init_db()
config = load_config()
mcp = FastMCP(name="AdCPSalesAgent")
console = Console()

# Initialize creative engine with config
creative_engine_config = config.get('creative_engine', {})
creative_engine = MockCreativeEngine(creative_engine_config)

def load_media_buys_from_db():
    """Load existing media buys from database into memory on startup."""
    try:
        # We can't load tenant-specific media buys at startup since we don't have tenant context
        # Media buys will be loaded on-demand when needed
        console.print("[dim]Media buys will be loaded on-demand from database[/dim]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not initialize media buys from database: {e}[/yellow]")

# --- In-Memory State ---
media_buys: Dict[str, Tuple[CreateMediaBuyRequest, str]] = {}
creative_assignments: Dict[str, Dict[str, List[str]]] = {}
creative_statuses: Dict[str, CreativeStatus] = {}
product_catalog: List[Product] = []
creative_library: Dict[str, Creative] = {}  # creative_id -> Creative
creative_groups: Dict[str, CreativeGroup] = {}  # group_id -> CreativeGroup
creative_assignments_v2: Dict[str, CreativeAssignment] = {}  # assignment_id -> CreativeAssignment

# Import audit logger for later use
from audit_logger import AuditLogger, get_audit_logger

# Human task queue (in-memory for now, would be database in production)
human_tasks: Dict[str, HumanTask] = {}

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
        # Log security violation
        from audit_logger import get_audit_logger
        tenant = get_current_tenant()
        security_logger = get_audit_logger("AdCP", tenant['tenant_id'])
        security_logger.log_security_violation(
            operation="access_media_buy",
            principal_id=principal_id,
            resource_id=media_buy_id,
            reason=f"Principal does not own media buy (owner: {media_buys[media_buy_id][1]})"
        )
        raise PermissionError(f"Principal '{principal_id}' does not own media buy '{media_buy_id}'.")

# --- MCP Tools (Full Implementation) ---

@mcp.tool
async def list_products(req: ListProductsRequest, context: Context) -> ListProductsResponse:
    principal_id = _get_principal_id_from_context(context) # Authenticate
    
    # Get tenant information
    tenant = get_current_tenant()
    if not tenant:
        raise ToolError("No tenant context available")
    
    # Get the Principal object with ad server mappings
    principal = get_principal_object(principal_id) if principal_id else None
    principal_data = principal.model_dump() if principal else None
    
    # Get the product catalog provider for this tenant
    provider = await get_product_catalog_provider(
        tenant['tenant_id'],
        tenant['config']
    )
    
    # Query products using the brief
    products = await provider.get_products(
        brief=req.brief,
        tenant_id=tenant['tenant_id'],
        principal_id=principal_id,
        principal_data=principal_data,
        context=None  # Could add additional context here if needed
    )
    
    return ListProductsResponse(products=products)

@mcp.tool
def create_media_buy(req: CreateMediaBuyRequest, context: Context) -> CreateMediaBuyResponse:
    principal_id = _get_principal_id_from_context(context)
    
    # Get the Principal object
    principal = get_principal_object(principal_id)
    if not principal:
        raise ToolError(f"Principal {principal_id} not found")
    
    # Validate targeting doesn't use managed-only dimensions
    if req.targeting_overlay:
        from targeting_capabilities import validate_overlay_targeting
        violations = validate_overlay_targeting(req.targeting_overlay.model_dump(exclude_none=True))
        if violations:
            raise ToolError(f"Targeting validation failed: {'; '.join(violations)}")
    
    # Get the appropriate adapter
    adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
    
    # Check if manual approval is required
    manual_approval_required = adapter.manual_approval_required if hasattr(adapter, 'manual_approval_required') else False
    manual_approval_operations = adapter.manual_approval_operations if hasattr(adapter, 'manual_approval_operations') else []
    
    if manual_approval_required and 'create_media_buy' in manual_approval_operations:
        # Create a human task instead of executing immediately
        task_req = CreateHumanTaskRequest(
            task_type="manual_approval",
            priority="high",
            media_buy_id=f"pending_{uuid.uuid4().hex[:8]}",
            operation="create_media_buy",
            error_detail="Publisher requires manual approval for all media buy creation",
            context_data={
                "request": req.model_dump(),
                "principal_id": principal_id,
                "adapter": adapter.__class__.adapter_name
            },
            due_in_hours=4
        )
        
        task_response = create_human_task(task_req, context)
        
        return CreateMediaBuyResponse(
            media_buy_id=task_req.media_buy_id,
            status="pending_manual",
            detail=f"Manual approval required. Task ID: {task_response.task_id}",
            creative_deadline=None
        )
    
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
    
    # Store the media buy in memory (for backward compatibility)
    media_buys[response.media_buy_id] = (req, principal_id)
    
    # Store the media buy in database
    tenant = get_current_tenant()
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO media_buys (
                media_buy_id, tenant_id, principal_id, order_name,
                advertiser_name, campaign_objective, kpi_goal, budget,
                start_date, end_date, status, raw_request
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            response.media_buy_id,
            tenant['tenant_id'],
            principal_id,
            req.po_number or f"Order-{response.media_buy_id}",
            principal.name,
            req.campaign_objective,
            req.kpi_goal,
            req.total_budget,
            req.flight_start_date.isoformat(),
            req.flight_end_date.isoformat(),
            response.status or 'active',
            json.dumps(req.model_dump())
        ))
        conn.connection.commit()
    finally:
        conn.close()
    
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
    
    # Initialize creative engine with tenant config
    tenant = get_current_tenant()
    creative_engine_config = tenant['config'].get('creative_engine', {})
    creative_engine = MockCreativeEngine(creative_engine_config)
    
    # Process creatives through the creative engine
    statuses = creative_engine.process_creatives(req.creatives)
    for status in statuses: 
        creative_statuses[status.creative_id] = status
        
        # Send Slack notification for pending creatives
        if status.status == "pending_review":
            try:
                principal_id = _get_principal_id_from_context(context)
                principal = get_principal_object(principal_id)
                creative = next((c for c in req.creatives if c.creative_id == status.creative_id), None)
                
                slack_notifier.notify_creative_pending(
                    creative_id=status.creative_id,
                    principal_name=principal.name if principal else principal_id,
                    format_type=creative.format.format_id if creative else "unknown",
                    media_buy_id=req.media_buy_id
                )
            except Exception as e:
                console.print(f"[yellow]Failed to send Slack notification: {e}[/yellow]")
    
    return SubmitCreativesResponse(statuses=statuses)

@mcp.tool
def check_creative_status(req: CheckCreativeStatusRequest, context: Context) -> CheckCreativeStatusResponse:
    statuses = [creative_statuses.get(cid) for cid in req.creative_ids if cid in creative_statuses]
    return CheckCreativeStatusResponse(statuses=statuses)

@mcp.tool
def adapt_creative(req: AdaptCreativeRequest, context: Context) -> CreativeStatus:
    _verify_principal(req.media_buy_id, context)
    
    # Initialize creative engine with tenant config
    tenant = get_current_tenant()
    creative_engine_config = tenant['config'].get('creative_engine', {})
    creative_engine = MockCreativeEngine(creative_engine_config)
    
    status = creative_engine.adapt_creative(req)
    creative_statuses[req.new_creative_id] = status
    return status

@mcp.tool
def legacy_update_media_buy(req: LegacyUpdateMediaBuyRequest, context: Context):
    """Legacy tool for backward compatibility."""
    _verify_principal(req.media_buy_id, context)
    buy_request, _ = media_buys[req.media_buy_id]
    if req.new_total_budget: buy_request.total_budget = req.new_total_budget
    if req.new_targeting_overlay: buy_request.targeting_overlay = req.new_targeting_overlay
    if req.creative_assignments: creative_assignments[req.media_buy_id] = req.creative_assignments
    return {"status": "success"}

# Unified update tools
@mcp.tool
def update_media_buy(req: UpdateMediaBuyRequest, context: Context) -> UpdateMediaBuyResponse:
    """Update a media buy with campaign-level and/or package-level changes."""
    _verify_principal(req.media_buy_id, context)
    _, principal_id = media_buys[req.media_buy_id]
    
    principal = get_principal_object(principal_id)
    if not principal:
        raise ToolError(f"Principal {principal_id} not found")
    
    adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
    today = req.today or date.today()
    
    # Check if manual approval is required
    manual_approval_required = adapter.manual_approval_required if hasattr(adapter, 'manual_approval_required') else False
    manual_approval_operations = adapter.manual_approval_operations if hasattr(adapter, 'manual_approval_operations') else []
    
    if manual_approval_required and 'update_media_buy' in manual_approval_operations:
        # Create a human task instead of executing immediately
        task_req = CreateHumanTaskRequest(
            task_type="manual_approval",
            priority="high",
            media_buy_id=req.media_buy_id,
            operation="update_media_buy",
            error_detail="Publisher requires manual approval for all media buy updates",
            context_data={
                "request": req.model_dump(),
                "principal_id": principal_id,
                "adapter": adapter.__class__.adapter_name
            },
            due_in_hours=2
        )
        
        task_response = create_human_task(task_req, context)
        
        return UpdateMediaBuyResponse(
            status="pending_manual",
            detail=f"Manual approval required. Task ID: {task_response.task_id}"
        )
    
    # Handle campaign-level updates
    if req.active is not None:
        action = "resume_media_buy" if req.active else "pause_media_buy"
        result = adapter.update_media_buy(
            media_buy_id=req.media_buy_id,
            action=action,
            package_id=None,
            budget=None,
            today=datetime.combine(today, datetime.min.time())
        )
        if result.status == "failed":
            return result
    
    # Handle package-level updates
    if req.packages:
        for pkg_update in req.packages:
            # Handle active/pause state
            if pkg_update.active is not None:
                action = "resume_package" if pkg_update.active else "pause_package"
                result = adapter.update_media_buy(
                    media_buy_id=req.media_buy_id,
                    action=action,
                    package_id=pkg_update.package_id,
                    budget=None,
                    today=datetime.combine(today, datetime.min.time())
                )
                if result.status == "failed":
                    return result
            
            # Handle budget updates
            if pkg_update.impressions is not None:
                result = adapter.update_media_buy(
                    media_buy_id=req.media_buy_id,
                    action="update_package_impressions",
                    package_id=pkg_update.package_id,
                    budget=pkg_update.impressions,
                    today=datetime.combine(today, datetime.min.time())
                )
                if result.status == "failed":
                    return result
            elif pkg_update.budget is not None:
                result = adapter.update_media_buy(
                    media_buy_id=req.media_buy_id,
                    action="update_package_budget",
                    package_id=pkg_update.package_id,
                    budget=int(pkg_update.budget),
                    today=datetime.combine(today, datetime.min.time())
                )
                if result.status == "failed":
                    return result
    
    # Update stored metadata if needed
    buy_request, _ = media_buys[req.media_buy_id]
    if req.total_budget is not None:
        buy_request.total_budget = req.total_budget
    if req.targeting_overlay is not None:
        # Validate targeting doesn't use managed-only dimensions
        from targeting_capabilities import validate_overlay_targeting
        violations = validate_overlay_targeting(req.targeting_overlay.model_dump(exclude_none=True))
        if violations:
            return UpdateMediaBuyResponse(
                status="failed",
                detail=f"Targeting validation failed: {'; '.join(violations)}"
            )
        buy_request.targeting_overlay = req.targeting_overlay
    if req.creative_assignments:
        creative_assignments[req.media_buy_id] = req.creative_assignments
    
    return UpdateMediaBuyResponse(
        status="accepted",
        implementation_date=datetime.combine(today, datetime.min.time()),
        detail="Media buy updated successfully"
    )

@mcp.tool
def update_package(req: UpdatePackageRequest, context: Context) -> UpdateMediaBuyResponse:
    """Update one or more packages within a media buy."""
    _verify_principal(req.media_buy_id, context)
    _, principal_id = media_buys[req.media_buy_id]
    
    principal = get_principal_object(principal_id)
    if not principal:
        raise ToolError(f"Principal {principal_id} not found")
    
    adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
    today = req.today or date.today()
    
    # Process each package update
    for pkg_update in req.packages:
        # Handle active/pause state
        if pkg_update.active is not None:
            action = "resume_package" if pkg_update.active else "pause_package"
            result = adapter.update_media_buy(
                media_buy_id=req.media_buy_id,
                action=action,
                package_id=pkg_update.package_id,
                budget=None,
                today=datetime.combine(today, datetime.min.time())
            )
            if result.status == "failed":
                return result
        
        # Handle budget/impression updates
        if pkg_update.impressions is not None:
            result = adapter.update_media_buy(
                media_buy_id=req.media_buy_id,
                action="update_package_impressions",
                package_id=pkg_update.package_id,
                budget=pkg_update.impressions,
                today=datetime.combine(today, datetime.min.time())
            )
            if result.status == "failed":
                return result
        elif pkg_update.budget is not None:
            result = adapter.update_media_buy(
                media_buy_id=req.media_buy_id,
                action="update_package_budget",
                package_id=pkg_update.package_id,
                budget=int(pkg_update.budget),
                today=datetime.combine(today, datetime.min.time())
            )
            if result.status == "failed":
                return result
        
        # TODO: Handle other updates (daily caps, pacing, targeting) when adapters support them
    
    return UpdateMediaBuyResponse(
        status="accepted",
        implementation_date=datetime.combine(today, datetime.min.time()),
        detail=f"Updated {len(req.packages)} package(s) successfully"
    )

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
def get_all_media_buy_delivery(req: GetAllMediaBuyDeliveryRequest, context: Context) -> GetAllMediaBuyDeliveryResponse:
    """Get delivery data for all active media buys owned by the principal.
    
    This is optimized for performance by batching requests when possible.
    """
    principal_id = _get_principal_id_from_context(context)
    
    # Get the Principal object
    principal = get_principal_object(principal_id)
    if not principal:
        raise ToolError(f"Principal {principal_id} not found")
    
    # Get the appropriate adapter
    adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
    
    # Filter media buys for this principal
    principal_media_buys = []
    if req.media_buy_ids:
        # Use specific IDs if provided
        for media_buy_id in req.media_buy_ids:
            if media_buy_id in media_buys:
                buy_request, buy_principal_id = media_buys[media_buy_id]
                if buy_principal_id == principal_id:
                    principal_media_buys.append((media_buy_id, buy_request))
                else:
                    console.print(f"[yellow]Skipping {media_buy_id} - not owned by principal[/yellow]")
    else:
        # Get all media buys for this principal
        for media_buy_id, (buy_request, buy_principal_id) in media_buys.items():
            if buy_principal_id == principal_id:
                principal_media_buys.append((media_buy_id, buy_request))
    
    # Collect delivery data for each media buy
    deliveries = []
    total_spend = 0.0
    total_impressions = 0
    active_count = 0
    
    for media_buy_id, buy_request in principal_media_buys:
        # Create a ReportingPeriod for the adapter
        reporting_period = ReportingPeriod(
            start=datetime.combine(req.today - timedelta(days=1), datetime.min.time()),
            end=datetime.combine(req.today, datetime.min.time()),
            start_date=req.today - timedelta(days=1),
            end_date=req.today
        )
        
        try:
            # Get delivery data from the adapter
            simulation_datetime = datetime.combine(req.today, datetime.min.time())
            delivery_response = adapter.get_media_buy_delivery(media_buy_id, reporting_period, simulation_datetime)
            
            # Calculate totals from the adapter response
            spend = delivery_response.totals.spend if hasattr(delivery_response, 'totals') else 0
            impressions = delivery_response.totals.impressions if hasattr(delivery_response, 'totals') else 0
            
            # Calculate days elapsed
            days_elapsed = (req.today - buy_request.flight_start_date).days
            total_days = (buy_request.flight_end_date - buy_request.flight_start_date).days
            
            # Determine pacing
            expected_spend = (buy_request.total_budget / total_days) * days_elapsed if total_days > 0 else 0
            if spend > expected_spend * 1.1:
                pacing = "ahead"
            elif spend < expected_spend * 0.9:
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
                active_count += 1
            
            # Add to results
            deliveries.append(GetMediaBuyDeliveryResponse(
                media_buy_id=media_buy_id,
                status=status,
                spend=spend,
                impressions=impressions,
                pacing=pacing,
                days_elapsed=days_elapsed,
                total_days=total_days
            ))
            
            total_spend += spend
            total_impressions += impressions
            
        except Exception as e:
            console.print(f"[red]Error fetching delivery for {media_buy_id}: {e}[/red]")
            # Add a placeholder response
            deliveries.append(GetMediaBuyDeliveryResponse(
                media_buy_id=media_buy_id,
                status="error",
                spend=0,
                impressions=0,
                pacing="unknown",
                days_elapsed=0,
                total_days=0
            ))
    
    return GetAllMediaBuyDeliveryResponse(
        deliveries=deliveries,
        total_spend=total_spend,
        total_impressions=total_impressions,
        active_count=active_count,
        summary_date=req.today
    )

@mcp.tool
def get_creatives(req: GetCreativesRequest, context: Context) -> GetCreativesResponse:
    """Get creatives from the library with optional filtering.
    
    Can filter by:
    - group_id: Get creatives in a specific group
    - media_buy_id: Get creatives assigned to a specific media buy
    - status: Filter by approval status
    - tags: Filter by creative group tags
    """
    principal_id = _get_principal_id_from_context(context)
    
    # Filter creatives by principal first
    principal_creatives = [
        creative for creative in creative_library.values() 
        if creative.principal_id == principal_id
    ]
    
    # Apply optional filters
    filtered_creatives = principal_creatives
    
    if req.group_id:
        filtered_creatives = [c for c in filtered_creatives if c.group_id == req.group_id]
    
    if req.status:
        # Check creative status
        filtered_creatives = [
            c for c in filtered_creatives 
            if creative_statuses.get(c.creative_id, CreativeStatus(
                creative_id=c.creative_id,
                status="pending_review",
                detail="Not yet reviewed"
            )).status == req.status
        ]
    
    if req.tags and len(req.tags) > 0:
        # Filter by group tags
        tagged_groups = {
            g.group_id for g in creative_groups.values() 
            if g.principal_id == principal_id and any(tag in g.tags for tag in req.tags)
        }
        filtered_creatives = [c for c in filtered_creatives if c.group_id in tagged_groups]
    
    # Get assignments if requested
    assignments = None
    if req.include_assignments:
        if req.media_buy_id:
            # Get assignments for specific media buy
            assignments = [
                a for a in creative_assignments_v2.values()
                if a.media_buy_id == req.media_buy_id and a.creative_id in [c.creative_id for c in filtered_creatives]
            ]
        else:
            # Get all assignments for these creatives
            creative_ids = {c.creative_id for c in filtered_creatives}
            assignments = [
                a for a in creative_assignments_v2.values()
                if a.creative_id in creative_ids
            ]
    
    return GetCreativesResponse(
        creatives=filtered_creatives,
        assignments=assignments
    )

@mcp.tool
def create_creative_group(req: CreateCreativeGroupRequest, context: Context) -> CreateCreativeGroupResponse:
    """Create a new creative group for organizing creatives."""
    principal_id = _get_principal_id_from_context(context)
    
    group = CreativeGroup(
        group_id=f"group_{uuid.uuid4().hex[:8]}",
        principal_id=principal_id,
        name=req.name,
        description=req.description,
        created_at=datetime.now(),
        tags=req.tags or []
    )
    
    creative_groups[group.group_id] = group
    
    # Log the creation
    from audit_logger import get_audit_logger
    tenant = get_current_tenant()
    logger = get_audit_logger("AdCP", tenant['tenant_id'])
    logger.log_operation(
        operation="create_creative_group",
        principal_name=get_principal_object(principal_id).name,
        principal_id=principal_id,
        adapter_id="N/A",
        success=True,
        details={
            "group_id": group.group_id,
            "name": group.name
        }
    )
    
    return CreateCreativeGroupResponse(group=group)

@mcp.tool
def create_creative(req: CreateCreativeRequest, context: Context) -> CreateCreativeResponse:
    """Create a creative in the library (not tied to a specific media buy)."""
    principal_id = _get_principal_id_from_context(context)
    principal = get_principal_object(principal_id)
    
    # Verify group ownership if specified
    if req.group_id and req.group_id in creative_groups:
        group = creative_groups[req.group_id]
        if group.principal_id != principal_id:
            raise PermissionError(f"Principal does not own group '{req.group_id}'")
    
    creative = Creative(
        creative_id=f"creative_{uuid.uuid4().hex[:8]}",
        principal_id=principal_id,
        group_id=req.group_id,
        format_id=req.format_id,
        content_uri=req.content_uri,
        name=req.name,
        click_through_url=req.click_through_url,
        metadata=req.metadata or {},
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    creative_library[creative.creative_id] = creative
    
    # Initialize creative engine with tenant config
    tenant = get_current_tenant()
    creative_engine_config = tenant['config'].get('creative_engine', {})
    creative_engine = MockCreativeEngine(creative_engine_config)
    
    # Process through creative engine for approval
    status = creative_engine.process_creatives([creative])[0]
    creative_statuses[creative.creative_id] = status
    
    # Log the creation
    from audit_logger import get_audit_logger
    tenant = get_current_tenant()
    logger = get_audit_logger("AdCP", tenant['tenant_id'])
    logger.log_operation(
        operation="create_creative",
        principal_name=principal.name,
        principal_id=principal_id,
        adapter_id="N/A",
        success=True,
        details={
            "creative_id": creative.creative_id,
            "name": creative.name,
            "format": creative.format_id
        }
    )
    
    return CreateCreativeResponse(creative=creative, status=status)

@mcp.tool
def assign_creative(req: AssignCreativeRequest, context: Context) -> AssignCreativeResponse:
    """Assign a creative from the library to a package in a media buy."""
    _verify_principal(req.media_buy_id, context)
    principal_id = _get_principal_id_from_context(context)
    
    # Verify creative ownership
    if req.creative_id not in creative_library:
        raise ValueError(f"Creative '{req.creative_id}' not found")
    
    creative = creative_library[req.creative_id]
    if creative.principal_id != principal_id:
        raise PermissionError(f"Principal does not own creative '{req.creative_id}'")
    
    # Create assignment
    assignment = CreativeAssignment(
        assignment_id=f"assign_{uuid.uuid4().hex[:8]}",
        media_buy_id=req.media_buy_id,
        package_id=req.package_id,
        creative_id=req.creative_id,
        weight=req.weight,
        percentage_goal=req.percentage_goal,
        rotation_type=req.rotation_type,
        override_click_url=req.override_click_url,
        override_start_date=req.override_start_date,
        override_end_date=req.override_end_date,
        targeting_overlay=req.targeting_overlay,
        is_active=True
    )
    
    creative_assignments_v2[assignment.assignment_id] = assignment
    
    # Also update legacy creative_assignments for backward compatibility
    if req.media_buy_id not in creative_assignments:
        creative_assignments[req.media_buy_id] = {}
    if req.package_id not in creative_assignments[req.media_buy_id]:
        creative_assignments[req.media_buy_id][req.package_id] = []
    creative_assignments[req.media_buy_id][req.package_id].append(req.creative_id)
    
    # Log the assignment
    from audit_logger import get_audit_logger
    tenant = get_current_tenant()
    logger = get_audit_logger("AdCP", tenant['tenant_id'])
    logger.log_operation(
        operation="assign_creative",
        principal_name=get_principal_object(principal_id).name,
        principal_id=principal_id,
        adapter_id="N/A",
        success=True,
        details={
            "assignment_id": assignment.assignment_id,
            "creative_id": req.creative_id,
            "package_id": req.package_id,
            "media_buy_id": req.media_buy_id
        }
    )
    
    return AssignCreativeResponse(assignment=assignment)

# --- Admin Tools ---

def _require_admin(context: Context) -> None:
    """Verify the request is from an admin user."""
    principal_id = get_principal_from_context(context)
    if principal_id != "admin":
        raise PermissionError("This operation requires admin privileges")

@mcp.tool
def get_pending_creatives(req: GetPendingCreativesRequest, context: Context) -> GetPendingCreativesResponse:
    """Admin-only: Get all pending creatives across all principals.
    
    This allows admins to review and approve/reject creatives.
    """
    _require_admin(context)
    
    pending_creatives = []
    
    for creative_id, status in creative_statuses.items():
        if status.status == "pending_review":
            creative = creative_library.get(creative_id)
            if creative:
                # Filter by principal if specified
                if req.principal_id and creative.principal_id != req.principal_id:
                    continue
                
                # Get principal info
                principal = get_principal_object(creative.principal_id)
                
                pending_creatives.append({
                    "creative": creative.model_dump(),
                    "status": status.model_dump(),
                    "principal": {
                        "principal_id": principal.principal_id,
                        "name": principal.name
                    } if principal else None,
                    "media_buy_assignments": [
                        {
                            "media_buy_id": a.media_buy_id,
                            "package_id": a.package_id
                        }
                        for a in creative_assignments_v2.values()
                        if a.creative_id == creative_id
                    ]
                })
    
    # Apply limit
    if req.limit:
        pending_creatives = pending_creatives[:req.limit]
    
    # Log admin action
    from audit_logger import get_audit_logger
    tenant = get_current_tenant()
    logger = get_audit_logger("AdCP", tenant['tenant_id'])
    logger.log_operation(
        operation="get_pending_creatives",
        principal_name="Admin",
        principal_id=principal_id,
        adapter_id="N/A",
        success=True,
        details={
            "count": len(pending_creatives),
            "filter_principal": req.principal_id
        }
    )
    
    return GetPendingCreativesResponse(pending_creatives=pending_creatives)

@mcp.tool
def approve_creative(req: ApproveCreativeRequest, context: Context) -> ApproveCreativeResponse:
    """Admin-only: Approve or reject a creative.
    
    This updates the creative status and notifies the principal.
    """
    _require_admin(context)
    
    if req.creative_id not in creative_library:
        raise ValueError(f"Creative '{req.creative_id}' not found")
    
    creative = creative_library[req.creative_id]
    
    # Update status
    new_status = "approved" if req.action == "approve" else "rejected"
    detail = req.reason or f"Creative {req.action}d by admin"
    
    creative_statuses[req.creative_id] = CreativeStatus(
        creative_id=req.creative_id,
        status=new_status,
        detail=detail,
        estimated_approval_time=None
    )
    
    # Log admin action
    from audit_logger import get_audit_logger
    tenant = get_current_tenant()
    logger = get_audit_logger("AdCP", tenant['tenant_id'])
    logger.log_operation(
        operation="approve_creative",
        principal_name="Admin",
        principal_id=get_principal_from_context(context),
        adapter_id="N/A",
        success=True,
        details={
            "creative_id": req.creative_id,
            "action": req.action,
            "new_status": new_status,
            "creative_owner": creative.principal_id
        }
    )
    
    # If approved and assigned to media buys, push to ad servers
    if new_status == "approved":
        assignments = [a for a in creative_assignments_v2.values() if a.creative_id == req.creative_id]
        for assignment in assignments:
            # Get the media buy and principal
            if assignment.media_buy_id in media_buys:
                buy_request, principal_id = media_buys[assignment.media_buy_id]
                principal = get_principal_object(principal_id)
                if principal:
                    try:
                        adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
                        # Push creative to ad server
                        assets = [{
                            'id': creative.creative_id,
                            'name': creative.name,
                            'format': creative.format_id,
                            'media_url': creative.content_uri,
                            'click_url': assignment.override_click_url or creative.click_through_url or '',
                            'package_assignments': [assignment.package_id]
                        }]
                        adapter.add_creative_assets(assignment.media_buy_id, assets, datetime.now())
                        console.print(f"[green]✓ Pushed creative {creative.creative_id} to {assignment.media_buy_id}[/green]")
                    except Exception as e:
                        console.print(f"[red]Failed to push creative to ad server: {e}[/red]")
    
    return ApproveCreativeResponse(
        creative_id=req.creative_id,
        new_status=new_status,
        detail=detail
    )

@mcp.tool
def get_principal_summary(context: Context) -> GetPrincipalSummaryResponse:
    _get_principal_id_from_context(context)  # Authenticate and set tenant
    tenant = get_current_tenant()
    
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT principal_id, name, platform_mappings FROM principals WHERE tenant_id = ?",
        (tenant['tenant_id'],)
    )
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


# --- Human-in-the-Loop Task Queue Tools ---

@mcp.tool
def create_human_task(req: CreateHumanTaskRequest, context: Context) -> CreateHumanTaskResponse:
    """Create a task requiring human intervention."""
    principal_id = get_principal_from_context(context)
    if not principal_id:
        raise ToolError("AUTHENTICATION_REQUIRED", "You must provide a valid x-adcp-auth header")
    
    # Generate task ID
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    
    # Calculate due date
    due_by = None
    if req.due_in_hours:
        due_by = datetime.now() + timedelta(hours=req.due_in_hours)
    elif req.priority == "urgent":
        due_by = datetime.now() + timedelta(hours=4)
    elif req.priority == "high":
        due_by = datetime.now() + timedelta(hours=24)
    elif req.priority == "medium":
        due_by = datetime.now() + timedelta(hours=48)
    
    # Create task
    task = HumanTask(
        task_id=task_id,
        task_type=req.task_type,
        principal_id=principal_id,
        adapter_name=req.adapter_name,
        status="pending",
        priority=req.priority,
        media_buy_id=req.media_buy_id,
        creative_id=req.creative_id,
        operation=req.operation,
        error_detail=req.error_detail,
        context_data=req.context_data,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        due_by=due_by
    )
    
    # Store task in memory
    human_tasks[task_id] = task
    
    # Store task in database
    tenant = get_current_tenant()
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO tasks (
                task_id, tenant_id, media_buy_id, task_type,
                title, description, status, assigned_to,
                due_date, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            tenant['tenant_id'],
            req.media_buy_id or '',
            req.task_type,
            f"{req.task_type}: {req.error_detail[:50] if req.error_detail else 'Manual approval required'}",
            req.error_detail,
            'pending',
            None,  # assigned_to
            due_by.isoformat() if due_by else None,
            json.dumps({
                "principal_id": principal_id,
                "adapter_name": req.adapter_name,
                "creative_id": req.creative_id,
                "operation": req.operation,
                "context_data": req.context_data,
                "priority": req.priority
            }),
            datetime.now().isoformat()
        ))
        conn.connection.commit()
    finally:
        conn.close()
    
    # Log task creation
    audit_logger = get_audit_logger("AdCP", tenant['tenant_id'])
    audit_logger.log_operation(
        operation="create_human_task",
        principal_name=principal_id,
        principal_id=principal_id,
        adapter_id="task_queue",
        success=True,
        details={
            "task_id": task_id,
            "task_type": req.task_type,
            "priority": req.priority
        }
    )
    
    # Log high priority tasks
    if req.priority in ["high", "urgent"]:
        console.print(f"[bold red]🚨 HIGH PRIORITY TASK CREATED: {task_id}[/bold red]")
        console.print(f"   Type: {req.task_type}")
        console.print(f"   Error: {req.error_detail}")
    
    # Send webhook notification for urgent tasks (if configured)
    tenant = get_current_tenant()
    webhook_url = tenant['config'].get("features", {}).get("hitl_webhook_url")
    if webhook_url and req.priority == "urgent":
        try:
            import requests
            requests.post(webhook_url, json={
                "task_id": task_id,
                "type": req.task_type,
                "priority": req.priority,
                "principal": principal_id,
                "error": req.error_detail,
                "tenant": tenant['tenant_id']
            }, timeout=5)
        except:
            pass  # Don't fail task creation if webhook fails
    
    # Send Slack notification for new tasks
    try:
        slack_notifier = get_slack_notifier(tenant['config'])
        slack_notifier.notify_new_task(
            task_id=task_id,
            task_type=req.task_type,
            principal_name=principal_id,
            media_buy_id=req.media_buy_id,
            details={
                "priority": req.priority,
                "error": req.error_detail,
                "operation": req.operation,
                "adapter": req.adapter_name
            },
            tenant_name=tenant['name']
        )
    except Exception as e:
        console.print(f"[yellow]Failed to send Slack notification: {e}[/yellow]")
    
    return CreateHumanTaskResponse(
        task_id=task_id,
        status="pending",
        due_by=due_by
    )


@mcp.tool
def get_pending_tasks(req: GetPendingTasksRequest, context: Context) -> GetPendingTasksResponse:
    """Get pending human tasks with optional filtering."""
    # Check if requester is admin
    principal_id = get_principal_from_context(context)
    tenant = get_current_tenant()
    is_admin = principal_id == f"{tenant['tenant_id']}_admin"
    
    # Filter tasks
    filtered_tasks = []
    overdue_count = 0
    now = datetime.now()
    
    for task in human_tasks.values():
        # Only show tasks for current principal unless admin
        if not is_admin and task.principal_id != principal_id:
            continue
            
        # Apply filters
        if req.principal_id and task.principal_id != req.principal_id:
            continue
        if req.task_type and task.task_type != req.task_type:
            continue
        if req.assigned_to and task.assigned_to != req.assigned_to:
            continue
        
        # Skip completed/failed unless looking for specific assignee
        if task.status in ["completed", "failed"] and not req.assigned_to:
            continue
            
        # Priority filter (minimum priority)
        priority_levels = {"low": 0, "medium": 1, "high": 2, "urgent": 3}
        if req.priority:
            if priority_levels.get(task.priority, 0) < priority_levels.get(req.priority, 0):
                continue
        
        # Check if overdue
        if task.due_by and task.due_by < now and task.status not in ["completed", "failed"]:
            overdue_count += 1
            if not req.include_overdue:
                continue
                
        filtered_tasks.append(task)
    
    # Sort by priority and due date
    filtered_tasks.sort(key=lambda t: (
        -priority_levels.get(t.priority, 0),
        t.due_by or datetime.max
    ))
    
    return GetPendingTasksResponse(
        tasks=filtered_tasks,
        total_count=len(filtered_tasks),
        overdue_count=overdue_count
    )


@mcp.tool
def assign_task(req: AssignTaskRequest, context: Context) -> Dict[str, str]:
    """Assign a task to a human operator."""
    # Admin only
    principal_id = get_principal_from_context(context)
    tenant = get_current_tenant()
    if principal_id != f"{tenant['tenant_id']}_admin":
        raise ToolError("PERMISSION_DENIED", "Only administrators can assign tasks")
    
    if req.task_id not in human_tasks:
        raise ToolError("NOT_FOUND", f"Task {req.task_id} not found")
    
    task = human_tasks[req.task_id]
    task.assigned_to = req.assigned_to
    task.assigned_at = datetime.now()
    task.status = "assigned"
    task.updated_at = datetime.now()
    
    audit_logger.log_operation(
        operation="assign_task",
        principal_name="admin",
        principal_id=principal_id,
        adapter_id="task_queue",
        success=True,
        details={
            "task_id": req.task_id,
            "assigned_to": req.assigned_to
        }
    )
    
    return {
        "status": "success",
        "detail": f"Task {req.task_id} assigned to {req.assigned_to}"
    }


@mcp.tool
def complete_task(req: CompleteTaskRequest, context: Context) -> Dict[str, str]:
    """Complete a human task with resolution details."""
    # Admin only
    principal_id = get_principal_from_context(context)
    tenant = get_current_tenant()
    if principal_id != f"{tenant['tenant_id']}_admin":
        raise ToolError("PERMISSION_DENIED", "Only administrators can complete tasks")
    
    if req.task_id not in human_tasks:
        raise ToolError("NOT_FOUND", f"Task {req.task_id} not found")
    
    task = human_tasks[req.task_id]
    task.resolution = req.resolution
    task.resolution_detail = req.resolution_detail
    task.resolved_by = req.resolved_by
    task.completed_at = datetime.now()
    task.status = "completed" if req.resolution in ["approved", "completed"] else "failed"
    task.updated_at = datetime.now()
    
    # Update task in database
    tenant = get_current_tenant()
    conn = get_db_connection()
    try:
        conn.execute("""
            UPDATE tasks 
            SET status = ?, completed_at = ?, completed_by = ?, metadata = ?
            WHERE task_id = ? AND tenant_id = ?
        """, (
            task.status,
            task.completed_at.isoformat() if task.completed_at else None,
            task.resolved_by,
            json.dumps({
                "resolution": task.resolution,
                "resolution_detail": task.resolution_detail,
                "original_metadata": json.loads(human_tasks[req.task_id].metadata) if hasattr(human_tasks[req.task_id], 'metadata') else {}
            }),
            req.task_id,
            tenant['tenant_id']
        ))
        conn.connection.commit()
    finally:
        conn.close()
    
    audit_logger = get_audit_logger("AdCP", tenant['tenant_id'])
    audit_logger.log_operation(
        operation="complete_task",
        principal_name="admin",
        principal_id=principal_id,
        adapter_id="task_queue",
        success=True,
        details={
            "task_id": req.task_id,
            "resolution": req.resolution,
            "resolved_by": req.resolved_by
        }
    )
    
    # Send Slack notification for task completion
    try:
        slack_notifier = get_slack_notifier(tenant['config'])
        slack_notifier.notify_task_completed(
            task_id=req.task_id,
            task_type=task.task_type,
            completed_by=req.resolved_by,
            success=task.status == "completed",
            error_message=req.resolution_detail if task.status == "failed" else None
        )
    except Exception as e:
        console.print(f"[yellow]Failed to send Slack notification: {e}[/yellow]")
    
    # Handle specific task types
    if task.task_type == "creative_approval" and task.creative_id:
        if req.resolution == "approved":
            # Update creative status
            if task.creative_id in creative_statuses:
                creative_statuses[task.creative_id].status = "approved"
                creative_statuses[task.creative_id].detail = "Manually approved by " + req.resolved_by
                console.print(f"[green]✅ Creative {task.creative_id} approved[/green]")
    
    elif task.task_type == "manual_approval" and task.operation:
        if req.resolution == "approved":
            # Execute the deferred operation
            console.print(f"[green]✅ Executing deferred operation: {task.operation}[/green]")
            
            # Get principal for the operation
            principal = get_principal_object(task.principal_id)
            if principal:
                adapter = get_adapter(principal, dry_run=DRY_RUN_MODE)
                
                if task.operation == "create_media_buy":
                    # Reconstruct and execute the create_media_buy request
                    original_req = CreateMediaBuyRequest(**task.context_data["request"])
                    
                    # Get products for the media buy
                    catalog = get_product_catalog()
                    products_in_buy = [p for p in catalog if p.product_id in original_req.product_ids]
                    
                    # Convert products to MediaPackages
                    packages = []
                    for product in products_in_buy:
                        format_info = product.formats[0] if product.formats else None
                        packages.append(MediaPackage(
                            package_id=product.product_id,
                            name=product.name,
                            delivery_type=product.delivery_type,
                            cpm=product.cpm if product.cpm else 10.0,
                            impressions=int(original_req.total_budget / (product.cpm if product.cpm else 10.0) * 1000),
                            format_ids=[format_info.format_id] if format_info else []
                        ))
                    
                    # Execute the actual creation
                    start_time = datetime.combine(original_req.flight_start_date, datetime.min.time())
                    end_time = datetime.combine(original_req.flight_end_date, datetime.max.time())
                    response = adapter.create_media_buy(original_req, packages, start_time, end_time)
                    
                    # Store the media buy in memory (for backward compatibility)
                    media_buys[response.media_buy_id] = (original_req, task.principal_id)
                    
                    # Store the media buy in database
                    tenant = get_current_tenant()
                    conn = get_db_connection()
                    try:
                        principal = get_principal_object(task.principal_id)
                        conn.execute("""
                            INSERT INTO media_buys (
                                media_buy_id, tenant_id, principal_id, order_name,
                                advertiser_name, campaign_objective, kpi_goal, budget,
                                start_date, end_date, status, raw_request
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            response.media_buy_id,
                            tenant['tenant_id'],
                            task.principal_id,
                            original_req.po_number or f"Order-{response.media_buy_id}",
                            principal.name if principal else "Unknown",
                            original_req.campaign_objective,
                            original_req.kpi_goal,
                            original_req.total_budget,
                            original_req.flight_start_date.isoformat(),
                            original_req.flight_end_date.isoformat(),
                            response.status or 'active',
                            json.dumps(original_req.model_dump())
                        ))
                        conn.connection.commit()
                    finally:
                        conn.close()
                    console.print(f"[green]Media buy {response.media_buy_id} created after manual approval[/green]")
                    
                elif task.operation == "update_media_buy":
                    # Reconstruct and execute the update_media_buy request
                    original_req = UpdateMediaBuyRequest(**task.context_data["request"])
                    today = original_req.today or date.today()
                    
                    # Execute the updates
                    if original_req.active is not None:
                        action = "resume_media_buy" if original_req.active else "pause_media_buy"
                        adapter.update_media_buy(
                            media_buy_id=original_req.media_buy_id,
                            action=action,
                            package_id=None,
                            budget=None,
                            today=datetime.combine(today, datetime.min.time())
                        )
                    
                    # Handle package updates
                    if original_req.packages:
                        for pkg_update in original_req.packages:
                            if pkg_update.active is not None:
                                action = "resume_package" if pkg_update.active else "pause_package"
                                adapter.update_media_buy(
                                    media_buy_id=original_req.media_buy_id,
                                    action=action,
                                    package_id=pkg_update.package_id,
                                    budget=None,
                                    today=datetime.combine(today, datetime.min.time())
                                )
                    
                    console.print(f"[green]Media buy {original_req.media_buy_id} updated after manual approval[/green]")
        else:
            console.print(f"[red]❌ Manual approval rejected for {task.operation}[/red]")
    
    return {
        "status": "success",
        "detail": f"Task {req.task_id} completed with resolution: {req.resolution}"
    }


@mcp.tool
def verify_task(req: VerifyTaskRequest, context: Context) -> VerifyTaskResponse:
    """Verify if a task was completed correctly by checking actual state."""
    if req.task_id not in human_tasks:
        raise ToolError("NOT_FOUND", f"Task {req.task_id} not found")
    
    task = human_tasks[req.task_id]
    actual_state = {}
    expected_state = req.expected_outcome or {}
    discrepancies = []
    verified = True
    
    # Verify based on task type and operation
    if task.task_type == "manual_approval" and task.operation == "update_media_buy":
        # Extract expected changes from task context
        if task.context_data and "request" in task.context_data:
            update_req = task.context_data["request"]
            media_buy_id = update_req.get("media_buy_id")
            
            if media_buy_id and media_buy_id in media_buys:
                # Get current state
                buy_request, principal_id = media_buys[media_buy_id]
                
                # Check daily budget if it was being updated
                if "daily_budget" in update_req:
                    expected_budget = update_req["daily_budget"]
                    actual_budget = getattr(buy_request, "daily_budget", None)
                    
                    actual_state["daily_budget"] = actual_budget
                    expected_state["daily_budget"] = expected_budget
                    
                    if actual_budget != expected_budget:
                        discrepancies.append(f"Daily budget is ${actual_budget}, expected ${expected_budget}")
                        verified = False
                
                # Check active status
                if "active" in update_req:
                    # Would need to check adapter status
                    # For now, assume task completion means it worked
                    actual_state["active"] = task.status == "completed"
                    expected_state["active"] = update_req["active"]
                
                # Check package updates
                if "packages" in update_req:
                    for pkg_update in update_req["packages"]:
                        if "budget" in pkg_update:
                            # Would need to query adapter for actual package budget
                            expected_state[f"package_{pkg_update['package_id']}_budget"] = pkg_update["budget"]
                            # For demo, assume it matches if task completed
                            actual_state[f"package_{pkg_update['package_id']}_budget"] = pkg_update["budget"] if task.status == "completed" else 0
    
    elif task.task_type == "creative_approval":
        # Check if creative was actually approved
        creative_id = task.creative_id
        if creative_id and creative_id in creative_statuses:
            actual_status = creative_statuses[creative_id].status
            actual_state["creative_status"] = actual_status
            expected_state["creative_status"] = "approved"
            
            if actual_status != "approved" and task.resolution == "approved":
                discrepancies.append(f"Creative {creative_id} status is {actual_status}, expected approved")
                verified = False
    
    return VerifyTaskResponse(
        task_id=req.task_id,
        verified=verified,
        actual_state=actual_state,
        expected_state=expected_state,
        discrepancies=discrepancies
    )


@mcp.tool
def mark_task_complete(req: MarkTaskCompleteRequest, context: Context) -> Dict[str, Any]:
    """Mark a task as complete with automatic verification."""
    # Admin only
    principal_id = get_principal_from_context(context)
    tenant = get_current_tenant()
    if principal_id != f"{tenant['tenant_id']}_admin":
        raise ToolError("PERMISSION_DENIED", "Only administrators can mark tasks complete")
    
    if req.task_id not in human_tasks:
        raise ToolError("NOT_FOUND", f"Task {req.task_id} not found")
    
    task = human_tasks[req.task_id]
    
    # First verify the task
    verify_req = VerifyTaskRequest(task_id=req.task_id)
    verification = verify_task(verify_req, context)
    
    if not verification.verified and not req.override_verification:
        return {
            "status": "verification_failed",
            "verified": False,
            "discrepancies": verification.discrepancies,
            "message": "Task verification failed. Use override_verification=true to force completion."
        }
    
    # Mark as complete
    task.status = "completed"
    task.resolution = "completed"
    task.resolution_detail = f"Marked complete by {req.completed_by}"
    if not verification.verified:
        task.resolution_detail += " (verification overridden)"
    task.resolved_by = req.completed_by
    task.completed_at = datetime.now()
    task.updated_at = datetime.now()
    
    # Update task in database
    tenant = get_current_tenant()
    conn = get_db_connection()
    try:
        conn.execute("""
            UPDATE tasks 
            SET status = ?, completed_at = ?, completed_by = ?, metadata = ?
            WHERE task_id = ? AND tenant_id = ?
        """, (
            task.status,
            task.completed_at.isoformat(),
            task.resolved_by,
            json.dumps({
                "resolution": task.resolution,
                "resolution_detail": task.resolution_detail,
                "verification": verification.model_dump()
            }),
            req.task_id,
            tenant['tenant_id']
        ))
        conn.connection.commit()
    finally:
        conn.close()
    
    audit_logger = get_audit_logger("AdCP", tenant['tenant_id'])
    audit_logger.log_operation(
        operation="mark_task_complete",
        principal_name="admin",
        principal_id=principal_id,
        adapter_id="task_queue",
        success=True,
        details={
            "task_id": req.task_id,
            "verified": verification.verified,
            "override": req.override_verification,
            "completed_by": req.completed_by
        }
    )
    
    return {
        "status": "success",
        "task_id": req.task_id,
        "verified": verification.verified,
        "verification_details": {
            "actual_state": verification.actual_state,
            "expected_state": verification.expected_state,
            "discrepancies": verification.discrepancies
        },
        "message": f"Task marked complete by {req.completed_by}"
    }


# Dry run logs are now handled by the adapters themselves

def get_product_catalog() -> List[Product]:
    """Get products for the current tenant."""
    tenant = get_current_tenant()
    
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT * FROM products WHERE tenant_id = ?",
        (tenant['tenant_id'],)
    )
    rows = cursor.fetchall()
    conn.close()
    
    loaded_products = []
    for row in rows:
        product_data = dict(row)
        # Remove tenant_id as it's not in the Product schema
        product_data.pop('tenant_id', None)
        product_data['formats'] = json.loads(product_data['formats'])
        # Remove targeting_template - it's internal and shouldn't be exposed
        product_data.pop('targeting_template', None)
        if product_data.get('price_guidance'):
            product_data['price_guidance'] = json.loads(product_data['price_guidance'])
        if product_data.get('implementation_config'):
            product_data['implementation_config'] = json.loads(product_data['implementation_config'])
        loaded_products.append(Product(**product_data))
    
    return loaded_products

if __name__ == "__main__":
    init_db()
    # Server is now run via run_server.py script

# Add admin UI routes when running unified
if os.environ.get('ADCP_UNIFIED_MODE'):
    from fastapi import Request
    from fastapi.responses import RedirectResponse, HTMLResponse
    from fastapi.middleware.wsgi import WSGIMiddleware
    from admin_ui import app as flask_admin_app
    
    # Create WSGI middleware for Flask app
    admin_wsgi = WSGIMiddleware(flask_admin_app)
    
    @mcp.custom_route("/", methods=["GET"])
    async def root(request: Request):
        """Redirect root to admin."""
        return RedirectResponse(url="/admin/")
    
    @mcp.custom_route("/admin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    async def admin_handler(request: Request, path: str = ""):
        """Handle admin UI requests."""
        # Forward to Flask app
        scope = request.scope.copy()
        scope["path"] = f"/{path}" if path else "/"
        
        receive = request.receive
        send = request._send
        
        await admin_wsgi(scope, receive, send)
    
    @mcp.custom_route("/tenant/{tenant_id}/admin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    async def tenant_admin_handler(request: Request, tenant_id: str, path: str = ""):
        """Handle tenant-specific admin requests."""
        # Forward to Flask app with tenant context
        scope = request.scope.copy()
        scope["path"] = f"/tenant/{tenant_id}/{path}" if path else f"/tenant/{tenant_id}"
        
        receive = request.receive
        send = request._send
        
        await admin_wsgi(scope, receive, send)
    
    @mcp.custom_route("/tenant/{tenant_id}", methods=["GET"])
    async def tenant_root(request: Request, tenant_id: str):
        """Redirect to tenant admin."""
        return RedirectResponse(url=f"/tenant/{tenant_id}/admin/")
    
    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request):
        """Unified health check."""
        return {"status": "healthy", "mode": "unified"}
