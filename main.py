import json
import os
import sys
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
from init_database import init_db
from schemas import *
from config_loader import (
    load_config, get_current_tenant, set_current_tenant,
    get_tenant_config, current_tenant
)
from db_config import get_db_connection
from slack_notifier import get_slack_notifier
from product_catalog_providers.factory import get_product_catalog_provider
from policy_check_service import PolicyCheckService, PolicyStatus

# --- Authentication ---

def get_principal_from_token(token: str, tenant_id: str) -> Optional[str]:
    """Looks up a principal_id from the database using a token."""
    # Check for tenant admin token first
    tenant = get_current_tenant()
    if tenant and token == tenant.get('admin_token'):
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
        
        # Load tenant by ID with all new fields
        conn = get_db_connection()
        cursor = conn.execute(
            """SELECT tenant_id, name, subdomain, ad_server, max_daily_budget, 
                      enable_aee_signals, authorized_emails, authorized_domains, 
                      slack_webhook_url, admin_token, auto_approve_formats, 
                      human_review_required, slack_audit_webhook_url, hitl_webhook_url,
                      policy_settings
               FROM tenants 
               WHERE tenant_id = ? AND is_active = ?""",
            (tenant_id, True)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print(f"No active tenant found for ID: {tenant_id}")
            return None
            
        # Set tenant context with new fields
        # Handle JSON fields that might be strings (SQLite) or already parsed (PostgreSQL)
        def safe_json_loads(value, default=None):
            if value is None:
                return default
            if isinstance(value, str):
                return json.loads(value)
            return value
        
        tenant_dict = {
            'tenant_id': row[0],
            'name': row[1],
            'subdomain': row[2],
            'ad_server': row[3],
            'max_daily_budget': row[4],
            'enable_aee_signals': row[5],
            'authorized_emails': safe_json_loads(row[6], []),
            'authorized_domains': safe_json_loads(row[7], []),
            'slack_webhook_url': row[8],
            'admin_token': row[9],
            'auto_approve_formats': safe_json_loads(row[10], []),
            'human_review_required': row[11],
            'slack_audit_webhook_url': row[12],
            'hitl_webhook_url': row[13],
            'policy_settings': safe_json_loads(row[14], None)
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
    if result and result[0]:
        # Handle JSON that might already be parsed (PostgreSQL) or string (SQLite)
        return json.loads(result[0]) if isinstance(result[0], str) else result[0]
    return {}

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
        # Handle JSON that might already be parsed (PostgreSQL) or string (SQLite)
        platform_mappings = json.loads(result[2]) if isinstance(result[2], str) else result[2]
        return Principal(
            principal_id=result[0],
            name=result[1],
            platform_mappings=platform_mappings
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
    # Get tenant and adapter config from database
    tenant = get_current_tenant()
    selected_adapter = tenant.get('ad_server', 'mock')
    
    # Get adapter config from adapter_config table
    conn = get_db_connection()
    cursor = conn.execute(
        """SELECT adapter_type, mock_dry_run, gam_network_code, gam_refresh_token,
                  gam_company_id, gam_trafficker_id, gam_manual_approval_required,
                  kevel_network_id, kevel_api_key, kevel_manual_approval_required,
                  triton_station_id, triton_api_key
           FROM adapter_config 
           WHERE tenant_id = ?""",
        (tenant['tenant_id'],)
    )
    row = cursor.fetchone()
    conn.close()
    
    adapter_config = {'enabled': True}
    if row:
        adapter_type = row[0]
        if adapter_type == 'mock':
            adapter_config['dry_run'] = row[1]
        elif adapter_type == 'google_ad_manager':
            adapter_config['network_code'] = row[2]
            adapter_config['refresh_token'] = row[3]
            adapter_config['company_id'] = row[4]
            adapter_config['trafficker_id'] = row[5]
            adapter_config['manual_approval_required'] = row[6]
        elif adapter_type == 'kevel':
            adapter_config['network_id'] = row[7]
            adapter_config['api_key'] = row[8]
            adapter_config['manual_approval_required'] = row[9]
        elif adapter_type == 'triton':
            adapter_config['station_id'] = row[10]
            adapter_config['api_key'] = row[11]
    
    if not selected_adapter:
        # Default to mock if no adapter specified
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

# Try to load config, but use defaults if no tenant context available
try:
    config = load_config()
except RuntimeError as e:
    if "No tenant in context" in str(e):
        # Use minimal config for test environments
        config = {
            'creative_engine': {},
            'dry_run': False,
            'adapters': {'mock': {'enabled': True}},
            'ad_server': {'adapter': 'mock', 'enabled': True}
        }
    else:
        raise

mcp = FastMCP(name="AdCPSalesAgent")
console = Console()

# Add health check endpoint
from fastapi import Request
from fastapi.responses import JSONResponse

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request):
    """Health check endpoint for Docker container health monitoring."""
    return JSONResponse(
        content={"status": "healthy", "service": "adcp-server"},
        status_code=200
    )

# Initialize creative engine with minimal config (will be tenant-specific later)
creative_engine_config = {}
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
async def get_products(req: GetProductsRequest, context: Context) -> GetProductsResponse:
    principal_id = _get_principal_id_from_context(context) # Authenticate
    
    # Get tenant information
    tenant = get_current_tenant()
    if not tenant:
        raise ToolError("No tenant context available")
    
    # Get the Principal object with ad server mappings
    principal = get_principal_object(principal_id) if principal_id else None
    principal_data = principal.model_dump() if principal else None
    
    # Check policy compliance first
    policy_service = PolicyCheckService()
    # Handle policy_settings that might already be a dict (PostgreSQL JSONB) or a string (SQLite)
    policy_settings = tenant.get('policy_settings')
    if policy_settings:
        if isinstance(policy_settings, str):
            policy_settings = json.loads(policy_settings)
    else:
        policy_settings = None
    
    policy_result = await policy_service.check_brief_compliance(
        brief=req.brief,
        promoted_offering=req.promoted_offering,
        tenant_policies=policy_settings
    )
    
    # Log the policy check
    audit_logger = get_audit_logger("AdCP", tenant['tenant_id'])
    audit_logger.log_operation(
        operation="policy_check",
        principal_name=principal_id or "anonymous",
        principal_id=principal_id,
        adapter_id="policy_service",
        success=policy_result.status != PolicyStatus.BLOCKED,
        details={
            "brief": req.brief[:100] + "..." if len(req.brief) > 100 else req.brief,
            "promoted_offering": req.promoted_offering[:100] + "..." if req.promoted_offering and len(req.promoted_offering) > 100 else req.promoted_offering,
            "policy_status": policy_result.status,
            "reason": policy_result.reason,
            "restrictions": policy_result.restrictions
        }
    )
    
    # Handle policy result based on settings
    # Handle policy_settings that might already be a dict (PostgreSQL JSONB) or a string (SQLite)
    policy_settings_raw = tenant.get('policy_settings')
    if policy_settings_raw:
        policy_settings = json.loads(policy_settings_raw) if isinstance(policy_settings_raw, str) else policy_settings_raw
    else:
        policy_settings = {}
    
    if policy_result.status == PolicyStatus.BLOCKED:
        # Always block if policy says blocked
        logger.warning(f"Brief blocked by policy: {policy_result.reason}")
        return GetProductsResponse(products=[])
    
    # If restricted and manual review is required, create a task
    if (policy_result.status == PolicyStatus.RESTRICTED and 
        policy_settings.get('require_manual_review', False)):
        
        # Create a manual review task
        conn = get_db_connection()
        task_id = f"policy_review_{tenant['tenant_id']}_{int(datetime.utcnow().timestamp())}"
        
        task_details = {
            "brief": req.brief,
            "promoted_offering": req.promoted_offering,
            "principal_id": principal_id,
            "policy_status": policy_result.status,
            "restrictions": policy_result.restrictions,
            "reason": policy_result.reason
        }
        
        conn.execute("""
            INSERT INTO tasks (
                tenant_id, task_id, media_buy_id, task_type, 
                status, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            tenant['tenant_id'],
            task_id,
            None,  # No media buy associated
            'policy_review',
            'pending',
            json.dumps(task_details),
            datetime.utcnow()
        ))
        
        conn.connection.commit()
        conn.close()
        
        logger.info(f"Created policy review task {task_id} for restricted brief")
        
        # Return empty list with message about pending review
        return GetProductsResponse(products=[])
    
    # Get the product catalog provider for this tenant
    provider = await get_product_catalog_provider(
        tenant['tenant_id'],
        {}  # Config is no longer needed for provider initialization
    )
    
    # Query products using the brief
    products = await provider.get_products(
        brief=req.brief,
        tenant_id=tenant['tenant_id'],
        principal_id=principal_id,
        principal_data=principal_data,
        context=None  # Could add additional context here if needed
    )
    
    # Filter products based on policy compliance
    eligible_products = []
    for product in products:
        is_eligible, reason = policy_service.check_product_eligibility(
            policy_result,
            product.model_dump()
        )
        
        if is_eligible:
            # Add policy compliance information to product
            if policy_result.status == PolicyStatus.RESTRICTED:
                product.policy_compliance = f"Restricted: {', '.join(policy_result.restrictions)}"
            else:
                product.policy_compliance = "Compliant"
            eligible_products.append(product)
        else:
            logger.info(f"Product {product.product_id} excluded: {reason}")
    
    return GetProductsResponse(products=eligible_products)

@mcp.tool
async def get_signals(req: GetSignalsRequest, context: Context) -> GetSignalsResponse:
    """Optional endpoint for discovering available signals (audiences, contextual, etc.)"""
    principal_id = _get_principal_id_from_context(context)
    
    # Get tenant information
    tenant = get_current_tenant()
    if not tenant:
        raise ToolError("No tenant context available")
    
    # Mock implementation - in production, this would query from a signal provider
    # or the ad server's available audience segments
    signals = []
    
    # Sample signals for demonstration
    sample_signals = [
        Signal(
            signal_id="auto_intenders_q1_2025",
            name="Auto Intenders Q1 2025",
            description="Users actively researching new vehicles in Q1 2025",
            type="audience",
            category="automotive",
            reach=2.5,
            cpm_uplift=3.0
        ),
        Signal(
            signal_id="luxury_travel_enthusiasts",
            name="Luxury Travel Enthusiasts",
            description="High-income individuals interested in premium travel experiences",
            type="audience",
            category="travel",
            reach=1.2,
            cpm_uplift=5.0
        ),
        Signal(
            signal_id="sports_content",
            name="Sports Content Pages",
            description="Target ads on sports-related content",
            type="contextual",
            category="sports",
            reach=15.0,
            cpm_uplift=1.5
        ),
        Signal(
            signal_id="finance_content",
            name="Finance & Business Content",
            description="Target ads on finance and business content",
            type="contextual",
            category="finance",
            reach=8.0,
            cpm_uplift=2.0
        ),
        Signal(
            signal_id="urban_millennials",
            name="Urban Millennials",
            description="Millennials living in major metropolitan areas",
            type="audience",
            category="demographic",
            reach=5.0,
            cpm_uplift=1.8
        ),
        Signal(
            signal_id="pet_owners",
            name="Pet Owners",
            description="Households with dogs or cats",
            type="audience",
            category="lifestyle",
            reach=35.0,
            cpm_uplift=1.2
        )
    ]
    
    # Filter based on request parameters
    for signal in sample_signals:
        # Apply query filter
        if req.query:
            query_lower = req.query.lower()
            if (query_lower not in signal.name.lower() and 
                query_lower not in signal.description.lower() and
                query_lower not in signal.category.lower()):
                continue
        
        # Apply type filter
        if req.type and signal.type != req.type:
            continue
            
        # Apply category filter
        if req.category and signal.category != req.category:
            continue
            
        signals.append(signal)
    
    # Apply limit
    if req.limit:
        signals = signals[:req.limit]
    
    return GetSignalsResponse(signals=signals)

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
    
    # Get tenant configuration for automatic media buy creation
    tenant = get_current_tenant()
    tenant_auto_create = tenant.get('automatic_media_buy_creation', False)
    
    # Check products for automatic creation setting
    conn = get_db_connection()
    placeholders = ','.join(['%s'] * len(req.product_ids))
    cursor = conn.execute(
        f"""SELECT product_id, automatic_creation 
           FROM products 
           WHERE tenant_id = %s AND product_id IN ({placeholders})""",
        [tenant['tenant_id']] + req.product_ids
    )
    product_auto_settings = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    
    # All products must have automatic_creation=True for auto-creation
    all_products_auto = all(product_auto_settings.get(pid, False) for pid in req.product_ids)
    
    # Check if manual approval is required based on:
    # 1. Adapter configuration (highest priority)
    # 2. Product settings (all products must be auto)
    # 3. Tenant settings (must be enabled)
    adapter_manual_required = adapter.manual_approval_required if hasattr(adapter, 'manual_approval_required') else False
    manual_approval_operations = adapter.manual_approval_operations if hasattr(adapter, 'manual_approval_operations') else []
    
    # Determine if human approval is needed
    needs_human_approval = (
        (adapter_manual_required and 'create_media_buy' in manual_approval_operations) or
        not all_products_auto or
        not tenant_auto_create
    )
    
    if needs_human_approval:
        # Generate context_id for tracking the conversation
        context_id = f"ctx_{uuid.uuid4().hex[:12]}"
        
        # Determine the reason for manual approval
        if adapter_manual_required and 'create_media_buy' in manual_approval_operations:
            reason = "Publisher requires manual approval for all media buy creation"
        elif not all_products_auto:
            reason = f"One or more products require manual approval"
        else:
            reason = "Tenant settings require manual approval for media buy creation"
        
        # Create a human task with full context
        task_req = CreateHumanTaskRequest(
            task_type="manual_approval",
            priority="high",
            media_buy_id=f"pending_{uuid.uuid4().hex[:8]}",
            operation="create_media_buy",
            error_detail=reason,
            context_data={
                "request": req.model_dump(mode='json'),  # Ensure date serialization
                "principal_id": principal_id,
                "adapter": adapter.__class__.adapter_name,
                "context_id": context_id,  # Include for conversation tracking
                "approval_reason": reason,
                "product_auto_settings": product_auto_settings,
                "tenant_auto_create": tenant_auto_create
            },
            due_in_hours=4
        )
        
        task_response = _create_human_task_internal(task_req, principal_id)
        
        return CreateMediaBuyResponse(
            context_id=context_id,  # Include context_id for status checking
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
    
    # Generate context_id (unique identifier for status checking)
    context_id = f"ctx_{uuid.uuid4().hex[:12]}"
    
    # Store the media buy in memory (for backward compatibility)
    media_buys[response.media_buy_id] = (req, principal_id)
    # Store context_id mapping
    if not hasattr(media_buys, 'context_map'):
        media_buys.context_map = {}
    media_buys.context_map[context_id] = response.media_buy_id
    
    # Store the media buy in database
    tenant = get_current_tenant()
    conn = get_db_connection()
    
    # Determine initial status
    initial_status = 'pending_creative' if not req.creatives else response.status or 'active'
    
    try:
        conn.execute("""
            INSERT INTO media_buys (
                media_buy_id, tenant_id, principal_id, order_name,
                advertiser_name, campaign_objective, kpi_goal, budget,
                start_date, end_date, status, raw_request, context_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            response.media_buy_id,
            tenant['tenant_id'],
            principal_id,
            req.po_number or f"Order-{response.media_buy_id}",
            principal.name,
            None,  # campaign_objective - not in request schema
            None,  # kpi_goal - not in request schema
            req.total_budget,
            req.flight_start_date.isoformat(),
            req.flight_end_date.isoformat(),
            initial_status,
            json.dumps(req.model_dump(mode='json')),
            context_id
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
        # Update status to active if creatives are attached
        conn = get_db_connection()
        try:
            conn.execute("UPDATE media_buys SET status = 'active' WHERE media_buy_id = %s", (response.media_buy_id,))
            conn.connection.commit()
        finally:
            conn.close()
    
    # Return response with context_id
    response.context_id = context_id
    response.status = initial_status
    return response

@mcp.tool
def check_media_buy_status(req: CheckMediaBuyStatusRequest, context: Context) -> CheckMediaBuyStatusResponse:
    """Check the status of a media buy using the context_id returned from create_media_buy."""
    principal_id = _get_principal_id_from_context(context)
    
    # Get the media_buy_id from context_id
    media_buy_id = None
    if hasattr(media_buys, 'context_map') and req.context_id in media_buys.context_map:
        media_buy_id = media_buys.context_map[req.context_id]
    
    # If not in memory, check database
    if not media_buy_id:
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                "SELECT media_buy_id, status, budget, start_date, end_date FROM media_buys WHERE context_id = %s",
                (req.context_id,)
            )
            row = cursor.fetchone()
            if row:
                media_buy_id = row['media_buy_id']
                status = row['status']
                budget = row['budget']
            else:
                raise ToolError(f"Invalid context_id: {req.context_id}")
        finally:
            conn.close()
    else:
        # Get from memory (for backward compatibility)
        if media_buy_id in media_buys:
            buy_data, buy_principal = media_buys[media_buy_id]
            if buy_principal != principal_id:
                raise ToolError("Unauthorized access to media buy")
            status = "active"  # Default for in-memory buys
            budget = buy_data.total_budget
        else:
            # Check database
            conn = get_db_connection()
            try:
                cursor = conn.execute(
                    "SELECT status, budget FROM media_buys WHERE media_buy_id = %s",
                    (media_buy_id,)
                )
                row = cursor.fetchone()
                if row:
                    status = row['status']
                    budget = row['budget']
                else:
                    raise ToolError(f"Media buy not found: {media_buy_id}")
            finally:
                conn.close()
    
    # Count attached creatives
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT COUNT(DISTINCT creative_id) as count FROM creative_associations WHERE media_buy_id = ?",
            (media_buy_id,)
        )
        creative_count = cursor.fetchone()['count'] or 0
    finally:
        conn.close()
    
    # Get package details
    packages = []
    if media_buy_id in media_buys:
        buy_data, _ = media_buys[media_buy_id]
        for product_id in buy_data.product_ids:
            packages.append({
                "product_id": product_id,
                "status": "active" if status == "active" else "pending"
            })
    
    return CheckMediaBuyStatusResponse(
        media_buy_id=media_buy_id,
        status=status,
        detail=f"Media buy is {status}",
        creative_count=creative_count,
        packages=packages if packages else None,
        budget_spent=0.0,  # Would need adapter integration for actual spend
        budget_remaining=budget if budget else 0.0
    )

@mcp.tool
def add_creative_assets(req: AddCreativeAssetsRequest, context: Context) -> AddCreativeAssetsResponse:
    """Add creative assets to a media buy (AdCP spec compliant)."""
    _verify_principal(req.media_buy_id, context)
    
    # Initialize creative engine with tenant config
    tenant = get_current_tenant()
    # Build creative engine config from tenant fields
    creative_engine_config = {
        'auto_approve_formats': tenant.get('auto_approve_formats', []),
        'human_review_required': tenant.get('human_review_required', True)
    }
    creative_engine = MockCreativeEngine(creative_engine_config)
    
    # Process creatives through the creative engine
    statuses = creative_engine.process_creatives(req.creatives)
    has_approved_creative = False
    
    for status in statuses: 
        creative_statuses[status.creative_id] = status
        if status.status == "approved":
            has_approved_creative = True
        
        # Send Slack notification for pending creatives
        if status.status == "pending_review":
            try:
                principal_id = _get_principal_id_from_context(context)
                principal = get_principal_object(principal_id)
                creative = next((c for c in req.creatives if c.creative_id == status.creative_id), None)
                
                # Build notifier config from tenant fields
                notifier_config = {
                    'features': {
                        'slack_webhook_url': tenant.get('slack_webhook_url'),
                        'slack_audit_webhook_url': tenant.get('slack_audit_webhook_url')
                    }
                }
                slack_notifier = get_slack_notifier(notifier_config)
                slack_notifier.notify_creative_pending(
                    creative_id=status.creative_id,
                    principal_name=principal.name if principal else principal_id,
                    format_type=creative.format.format_id if creative else "unknown",
                    media_buy_id=req.media_buy_id
                )
            except Exception as e:
                console.print(f"[yellow]Failed to send Slack notification: {e}[/yellow]")
    
    return AddCreativeAssetsResponse(statuses=statuses)

@mcp.tool
def check_creative_status(req: CheckCreativeStatusRequest, context: Context) -> CheckCreativeStatusResponse:
    statuses = [creative_statuses.get(cid) for cid in req.creative_ids if cid in creative_statuses]
    return CheckCreativeStatusResponse(statuses=statuses)

"""
TODO: Fix schema - ApproveAdaptationRequest not defined
@mcp.tool
def approve_adaptation(req: ApproveAdaptationRequest, context: Context) -> ApproveAdaptationResponse:
    # Approve a suggested creative adaptation.
    principal_id = _get_principal_id_from_context(context)
    
    # Verify creative ownership
    if req.creative_id not in creative_library:
        return ApproveAdaptationResponse(
            success=False,
            message=f"Creative '{req.creative_id}' not found"
        )
    
    creative = creative_library[req.creative_id]
    if creative.principal_id != principal_id:
        return ApproveAdaptationResponse(
            success=False,
            message=f"Principal does not own creative '{req.creative_id}'"
        )
    
    # Check if the creative has this adaptation
    if req.creative_id not in creative_statuses:
        return ApproveAdaptationResponse(
            success=False,
            message=f"Creative '{req.creative_id}' has no status information"
        )
    
    status = creative_statuses[req.creative_id]
    adaptation = None
    for adapt in status.suggested_adaptations:
        if adapt.adaptation_id == req.adaptation_id:
            adaptation = adapt
            break
    
    if not adaptation:
        return ApproveAdaptationResponse(
            success=False,
            message=f"Adaptation '{req.adaptation_id}' not found for creative '{req.creative_id}'"
        )
    
    if not req.approve:
        return ApproveAdaptationResponse(
            success=True,
            message=f"Adaptation '{req.adaptation_id}' rejected"
        )
    
    # Create the adapted creative
    new_creative_id = f"{req.creative_id}_{adaptation.format_id}_adapted"
    new_name = adaptation.name
    if req.modifications and 'name' in req.modifications:
        new_name = req.modifications['name']
    
    new_creative = Creative(
        creative_id=new_creative_id,
        principal_id=principal_id,
        group_id=creative.group_id,
        format_id=adaptation.format_id,
        content_uri=f"https://cdn.publisher.com/adapted/{new_creative_id}.mp4",  # Mock URL
        name=new_name,
        click_through_url=creative.click_through_url,
        metadata={
            'adapted_from': req.creative_id,
            'adaptation_id': req.adaptation_id,
            'changes': adaptation.changes_summary
        },
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    creative_library[new_creative_id] = new_creative
    
    # Auto-approve the adapted creative
    new_status = CreativeStatus(
        creative_id=new_creative_id,
        status="approved",
        detail="Adapted creative auto-approved",
        suggested_adaptations=[]
    )
    creative_statuses[new_creative_id] = new_status
    
    # Log the adaptation
    from audit_logger import get_audit_logger
    tenant = get_current_tenant()
    logger = get_audit_logger("AdCP", tenant['tenant_id'])
    logger.log_operation(
        operation="approve_adaptation",
        principal_name=get_principal_object(principal_id).name,
        principal_id=principal_id,
        adapter_id="N/A",
        success=True,
        details={
            "original_creative_id": req.creative_id,
            "new_creative_id": new_creative_id,
            "adaptation_id": req.adaptation_id
        }
    )
    
    return ApproveAdaptationResponse(
        success=True,
        new_creative=new_creative,
        status=new_status,
        message=f"Adaptation approved and creative '{new_creative_id}' generated"
    )
"""

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
        
        task_response = _create_human_task_internal(task_req, principal_id)
        
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
    # Build creative engine config from tenant fields
    creative_engine_config = {
        'auto_approve_formats': tenant.get('auto_approve_formats', []),
        'human_review_required': tenant.get('human_review_required', True)
    }
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

# DEPRECATED: get_principal_summary is NOT part of the AdCP spec
# This tool will be removed in a future version
# Use check_media_buy_status with context_id instead
@mcp.tool
def get_principal_summary(context: Context) -> GetPrincipalSummaryResponse:
    """
    DEPRECATED: This tool is not part of the AdCP specification.
    Use check_media_buy_status with context_id from create_media_buy instead.
    This tool will be removed in a future version.
    """
    console.print("[yellow]⚠️  WARNING: get_principal_summary is deprecated and not part of AdCP spec[/yellow]")
    console.print("[yellow]   Use check_media_buy_status with context_id instead[/yellow]")
    
    _get_principal_id_from_context(context)  # Authenticate and set tenant
    tenant = get_current_tenant()
    
    conn = get_db_connection()
    cursor = conn.execute(
        "SELECT principal_id, name, platform_mappings FROM principals WHERE tenant_id = %s",
        (tenant['tenant_id'],)
    )
    rows = cursor.fetchall()
    conn.close()
    summaries = []
    for row in rows:
        # Handle JSON that might already be parsed (PostgreSQL) or string (SQLite)
        platform_mappings = json.loads(row[2]) if isinstance(row[2], str) else row[2]
        summaries.append(PrincipalSummary(
            principal_id=row[0], 
            name=row[1], 
            platform_mappings=platform_mappings,
            live_media_buys=sum(1 for _, pid in media_buys.values() if pid == row[0]),
            total_spend=sum(br.total_budget for br, pid in media_buys.values() if pid == row[0])
        ))
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

def _create_human_task_internal(req: CreateHumanTaskRequest, principal_id: str) -> CreateHumanTaskResponse:
    """Internal function to create a human task - can be called directly."""
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
            INSERT INTO human_tasks (
                tenant_id, task_id, task_type, title, 
                description, status, assigned_to, due_by, 
                context_data, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            tenant['tenant_id'],
            task_id,
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
    webhook_url = tenant.get("hitl_webhook_url")
    if webhook_url and req.priority == "urgent":
        try:
            import requests
            requests.post(webhook_url, json={
                "task_id": task_id,
                "type": req.task_type,
                "error": req.error_detail,
                "priority": req.priority,
                "adapter": req.adapter_name,
                "media_buy_id": req.media_buy_id
            }, timeout=5)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not send webhook notification: {e}[/yellow]")
    
    return CreateHumanTaskResponse(
        task_id=task_id,
        status="pending",
        assigned_to=None,
        due_by=due_by
    )

@mcp.tool
def create_human_task(req: CreateHumanTaskRequest, context: Context) -> CreateHumanTaskResponse:
    """Create a task requiring human intervention."""
    principal_id = get_principal_from_context(context)
    if not principal_id:
        raise ToolError("AUTHENTICATION_REQUIRED", "You must provide a valid x-adcp-auth header")
    
    # Call the internal function
    return _create_human_task_internal(req, principal_id)


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
    
    audit_logger = get_audit_logger("AdCP", tenant['tenant_id'])
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
        # Build notifier config from tenant fields
        notifier_config = {
            'features': {
                'slack_webhook_url': tenant.get('slack_webhook_url'),
                'slack_audit_webhook_url': tenant.get('slack_audit_webhook_url')
            }
        }
        slack_notifier = get_slack_notifier(notifier_config)
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
                            None,  # campaign_objective - not in request schema
                            None,  # kpi_goal - not in request schema
                            original_req.total_budget,
                            original_req.flight_start_date.isoformat(),
                            original_req.flight_end_date.isoformat(),
                            response.status or 'active',
                            json.dumps(original_req.model_dump(mode='json'))
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
    
    # Get column names for PostgreSQL compatibility
    column_names = [desc[0] for desc in cursor.description]
    conn.close()
    
    loaded_products = []
    for row in rows:
        # Handle both SQLite Row objects and PostgreSQL tuples
        if hasattr(row, 'keys'):
            # SQLite Row object
            product_data = dict(row)
        else:
            # PostgreSQL tuple - create dict from column names
            product_data = dict(zip(column_names, row))
        # Remove tenant_id as it's not in the Product schema
        product_data.pop('tenant_id', None)
        
        # Handle JSONB fields - PostgreSQL returns them as Python objects, SQLite as strings
        if product_data['formats'] and isinstance(product_data['formats'], str):
            product_data['formats'] = json.loads(product_data['formats'])
            
        # Remove targeting_template - it's internal and shouldn't be exposed
        product_data.pop('targeting_template', None)
        
        if product_data.get('price_guidance'):
            if isinstance(product_data['price_guidance'], str):
                product_data['price_guidance'] = json.loads(product_data['price_guidance'])
                
        if product_data.get('implementation_config'):
            if isinstance(product_data['implementation_config'], str):
                product_data['implementation_config'] = json.loads(product_data['implementation_config'])
        loaded_products.append(Product(**product_data))
    
    return loaded_products

@mcp.tool
def get_targeting_capabilities(req: GetTargetingCapabilitiesRequest, context: Context) -> GetTargetingCapabilitiesResponse:
    """Get available targeting dimensions for specified channels."""
    from targeting_dimensions import (
        get_channel_capabilities, get_supported_channels, Channel,
        TargetingDimensionInfo, ChannelTargetingCapabilities
    )
    
    # Determine which channels to return
    channels = req.channels if req.channels else [c.value for c in get_supported_channels()]
    
    capabilities = []
    for channel_str in channels:
        try:
            channel = Channel(channel_str)
            caps = get_channel_capabilities(channel)
            
            # Convert to response format
            overlay_dims = [
                TargetingDimensionInfo(
                    key=d.key,
                    display_name=d.display_name,
                    description=d.description,
                    data_type=d.data_type,
                    required=d.required,
                    values=d.values
                )
                for d in caps.overlay_dimensions
            ]
            
            aee_dims = None
            if req.include_aee_dimensions:
                aee_dims = [
                    TargetingDimensionInfo(
                        key=d.key,
                        display_name=d.display_name,
                        description=d.description,
                        data_type=d.data_type,
                        required=d.required,
                        values=d.values
                    )
                    for d in caps.aee_dimensions
                ]
            
            capabilities.append(
                ChannelTargetingCapabilities(
                    channel=channel_str,
                    overlay_dimensions=overlay_dims,
                    aee_dimensions=aee_dims
                )
            )
        except ValueError:
            # Skip invalid channel names
            continue
    
    return GetTargetingCapabilitiesResponse(capabilities=capabilities)

@mcp.tool
def check_aee_requirements(req: CheckAEERequirementsRequest, context: Context) -> CheckAEERequirementsResponse:
    """Check if required AEE dimensions are supported for a channel."""
    from targeting_dimensions import get_aee_dimensions, Channel
    
    try:
        channel = Channel(req.channel)
    except ValueError:
        return CheckAEERequirementsResponse(
            supported=False,
            missing_dimensions=req.required_dimensions,
            available_dimensions=[]
        )
    
    # Get available AEE dimensions
    aee_dims = get_aee_dimensions(channel)
    available_keys = [d.key for d in aee_dims]
    
    # Check which are missing
    missing = [dim for dim in req.required_dimensions if dim not in available_keys]
    
    return CheckAEERequirementsResponse(
        supported=len(missing) == 0,
        missing_dimensions=missing,
        available_dimensions=available_keys
    )

# Creative macro support is now simplified to a single creative_macro string
# that AEE can provide as a third type of provided_signal.
# Ad servers like GAM can inject this string into creatives.

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
