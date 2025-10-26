import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from rich.console import Console
from sqlalchemy import select

from src.adapters.mock_creative_engine import MockCreativeEngine
from src.core.audit_logger import get_audit_logger
from src.core.auth import (
    get_principal_from_context,
)
from src.landing import generate_tenant_landing_page

logger = logging.getLogger(__name__)

# Database models

# Other imports
from src.core.config_loader import (
    get_current_tenant,
    get_tenant_by_virtual_host,
    load_config,
    set_current_tenant,
)
from src.core.database.database import init_db
from src.core.database.database_session import get_db_session
from src.core.database.models import (
    ObjectWorkflowMapping,
    Tenant,
    WorkflowStep,
)
from src.core.database.models import Principal as ModelPrincipal
from src.core.database.models import Product as ModelProduct

# Schema models (explicit imports to avoid collisions)
# Schema adapters (wrapping generated schemas)
from src.core.schemas import (
    CreateMediaBuyRequest,
    Creative,
    CreativeAssignment,
    CreativeGroup,
    CreativeStatus,
    Product,
)

# Initialize Rich console
console = Console()

# Backward compatibility alias for deprecated Task model
# The workflow system now uses WorkflowStep exclusively
Task = WorkflowStep

# Temporary placeholder classes for missing schemas
# TODO: These should be properly defined in schemas.py
from pydantic import BaseModel


class ApproveAdaptationRequest(BaseModel):
    creative_id: str
    adaptation_id: str
    approve: bool = True
    modifications: dict[str, Any] | None = None


class ApproveAdaptationResponse(BaseModel):
    success: bool
    message: str


# --- Helper Functions ---


# --- Helper Functions ---
# Helper functions moved to src/core/helpers/ modules and imported above

# --- Authentication ---
# Auth functions moved to src/core/auth.py and imported above


# --- Initialization ---
# NOTE: Database initialization moved to startup script to avoid import-time failures
# The run_all_services.py script handles database initialization before starting the MCP server

# Try to load config, but use defaults if no tenant context available
try:
    config = load_config()
except (RuntimeError, Exception) as e:
    # Use minimal config for test environments or when DB is unavailable
    # This handles both "No tenant context set" and database connection errors
    if "No tenant context" in str(e) or "connection" in str(e).lower() or "operational" in str(e).lower():
        config = {
            "creative_engine": {},
            "dry_run": False,
            "adapters": {"mock": {"enabled": True}},
            "ad_server": {"adapter": "mock", "enabled": True},
        }
    else:
        raise

mcp = FastMCP(
    name="AdCPSalesAgent",
    # Sessions enabled for HTTP context (tenant detection via headers)
    # Note: stateless_http is now configured at runtime via run() or global settings
)

# Initialize creative engine with minimal config (will be tenant-specific later)
creative_engine_config: dict[str, Any] = {}
creative_engine = MockCreativeEngine(creative_engine_config)


def load_media_buys_from_db():
    """Load existing media buys from database into memory on startup."""
    try:
        # We can't load tenant-specific media buys at startup since we don't have tenant context
        # Media buys will be loaded on-demand when needed
        console.print("[dim]Media buys will be loaded on-demand from database[/dim]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not initialize media buys from database: {e}[/yellow]")


def load_tasks_from_db():
    """[DEPRECATED] This function is no longer needed - tasks are queried directly from database."""
    # This function is kept for backward compatibility but does nothing
    # All task operations now use direct database queries
    pass


# Removed get_task_from_db - replaced by workflow-based system


# --- In-Memory State ---
media_buys: dict[str, tuple[CreateMediaBuyRequest, str]] = {}
creative_assignments: dict[str, dict[str, list[str]]] = {}
creative_statuses: dict[str, CreativeStatus] = {}
product_catalog: list[Product] = []
creative_library: dict[str, Creative] = {}  # creative_id -> Creative
creative_groups: dict[str, CreativeGroup] = {}  # group_id -> CreativeGroup
creative_assignments_v2: dict[str, CreativeAssignment] = {}  # assignment_id -> CreativeAssignment
# REMOVED: human_tasks dictionary - now using direct database queries only

# Note: load_tasks_from_db() is no longer needed - tasks are queried directly from database

# Authentication cache removed - FastMCP v2.11.0+ properly forwards headers

# Import audit logger for later use

# Import context manager for workflow steps
from src.core.context_manager import ContextManager

context_mgr = ContextManager()

# --- Adapter Configuration ---
# Get adapter from config, fallback to mock
SELECTED_ADAPTER = (
    (config.get("ad_server", {}).get("adapter") or "mock") if config else "mock"
).lower()  # noqa: F841 - used below for adapter selection
AVAILABLE_ADAPTERS = ["mock", "gam", "kevel", "triton", "triton_digital"]

# --- In-Memory State (already initialized above, just adding context_map) ---
context_map: dict[str, str] = {}  # Maps context_id to media_buy_id

# --- Dry Run Mode ---
DRY_RUN_MODE = config.get("dry_run", False)
if DRY_RUN_MODE:
    console.print("[bold yellow]🏃 DRY RUN MODE ENABLED - Adapter calls will be logged[/bold yellow]")

# Display selected adapter
if SELECTED_ADAPTER not in AVAILABLE_ADAPTERS:
    console.print(f"[bold red]❌ Invalid adapter '{SELECTED_ADAPTER}'. Using 'mock' instead.[/bold red]")
    SELECTED_ADAPTER = "mock"
console.print(f"[bold cyan]🔌 Using adapter: {SELECTED_ADAPTER.upper()}[/bold cyan]")


# --- Creative Conversion Helper ---
# Creative helper functions moved to src/core/helpers.py and imported above


# --- Security Helper ---


# --- Activity Feed Helper ---


# --- MCP Tools (Full Implementation) ---


# Unified update tools


# --- Admin Tools ---


# --- Human-in-the-Loop Task Queue Tools ---
# DEPRECATED workflow functions moved to src/core/helpers/workflow_helpers.py and imported above

# Removed get_pending_workflows - replaced by admin dashboard workflow views

# Removed assign_task - assignment handled through admin UI workflow management

# Dry run logs are now handled by the adapters themselves


def get_product_catalog() -> list[Product]:
    """Get products for the current tenant."""
    from sqlalchemy.orm import selectinload

    tenant = get_current_tenant()

    with get_db_session() as session:
        stmt = (
            select(ModelProduct)
            .filter_by(tenant_id=tenant["tenant_id"])
            .options(selectinload(ModelProduct.pricing_options))
        )
        products = session.scalars(stmt).all()

        loaded_products = []
        for product in products:
            # Convert ORM model to Pydantic schema
            # Parse JSON fields that might be strings (SQLite) or dicts (PostgreSQL)
            def safe_json_parse(value):
                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        return value
                return value

            # Parse formats - now stored as strings by the validator
            format_ids = safe_json_parse(product.formats) or []
            # Ensure it's a list of strings (validator guarantees this)
            if not isinstance(format_ids, list):
                format_ids = []

            # Convert pricing_options ORM objects to Pydantic objects
            from src.core.schemas import PricingOption as PricingOptionSchema

            pricing_options = []
            for po in product.pricing_options:
                pricing_option_data = {
                    "pricing_option_id": f"{po.pricing_model}_{po.currency}_{po.id}",
                    "pricing_model": po.pricing_model,
                    "rate": float(po.rate) if po.rate else None,
                    "currency": po.currency,
                    "is_fixed": po.is_fixed,
                    "price_guidance": safe_json_parse(po.price_guidance) if po.price_guidance else None,
                    "parameters": safe_json_parse(po.parameters) if po.parameters else None,
                    "min_spend_per_package": float(po.min_spend_per_package) if po.min_spend_per_package else None,
                }
                pricing_options.append(PricingOptionSchema(**pricing_option_data))

            product_data = {
                "product_id": product.product_id,
                "name": product.name,
                "description": product.description,
                "formats": format_ids,
                "delivery_type": product.delivery_type,
                "pricing_options": pricing_options,
                "measurement": (
                    safe_json_parse(product.measurement)
                    if hasattr(product, "measurement") and product.measurement
                    else None
                ),
                "creative_policy": (
                    safe_json_parse(product.creative_policy)
                    if hasattr(product, "creative_policy") and product.creative_policy
                    else None
                ),
                "is_custom": product.is_custom,
                "expires_at": product.expires_at,
                # Note: brief_relevance is populated dynamically when brief is provided
                "implementation_config": safe_json_parse(product.implementation_config),
                # Required per AdCP spec: either properties OR property_tags
                "properties": (
                    safe_json_parse(product.properties)
                    if hasattr(product, "properties") and product.properties
                    else None
                ),
                "property_tags": (
                    safe_json_parse(product.property_tags)
                    if hasattr(product, "property_tags") and product.property_tags
                    else ["all_inventory"]  # Default required per AdCP spec
                ),
            }
            loaded_products.append(Product(**product_data))

    return loaded_products


# Creative macro support is now simplified to a single creative_macro string
# that AEE can provide as a third type of provided_signal.
# Ad servers like GAM can inject this string into creatives.

if __name__ == "__main__":
    init_db(exit_on_error=True)  # Exit on error when run as main
    # Server is now run via run_server.py script

# Always add health check endpoint
from fastapi import Request
from fastapi.responses import JSONResponse

# --- Strategy and Simulation Control ---
from src.core.strategy import StrategyManager


def get_strategy_manager(context: Context | None) -> StrategyManager:
    """Get strategy manager for current context."""
    principal_id, tenant_config = get_principal_from_context(context)
    if tenant_config:
        set_current_tenant(tenant_config)
    else:
        tenant_config = get_current_tenant()

    if not tenant_config:
        raise ToolError("No tenant configuration found")

    return StrategyManager(tenant_id=tenant_config.get("tenant_id"), principal_id=principal_id)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "service": "mcp"})


@mcp.custom_route("/admin/reset-db-pool", methods=["POST"])
async def reset_db_pool(request: Request):
    """Reset database connection pool after external data changes.

    This is a testing-only endpoint that flushes the SQLAlchemy connection pool,
    ensuring fresh connections see recently committed data. Only works when
    ADCP_TESTING environment variable is set to 'true'.

    Use case: E2E tests that initialize data via external script need to ensure
    the running MCP server's connection pool picks up that fresh data.
    """
    # Security: Only allow in testing mode
    if os.getenv("ADCP_TESTING") != "true":
        logger.warning("Attempted to reset DB pool outside testing mode")
        return JSONResponse({"error": "This endpoint is only available in testing mode"}, status_code=403)

    try:
        from src.core.database.database_session import reset_engine

        logger.info("Resetting database connection pool, provider cache, and tenant context (testing mode)")

        # Reset SQLAlchemy connection pool
        reset_engine()
        logger.info("  ✓ Database connection pool reset")

        # CRITICAL: Also clear the product catalog provider cache
        # The provider cache holds DatabaseProductCatalog instances that may have
        # stale data from before init_database_ci.py ran
        from product_catalog_providers.factory import _provider_cache

        provider_count = len(_provider_cache)
        _provider_cache.clear()
        logger.info(f"  ✓ Cleared {provider_count} cached product catalog provider(s)")

        # CRITICAL: Clear tenant context ContextVar
        # After data initialization, the tenant context may contain stale tenant data
        # that was loaded before products were created. Force fresh tenant lookup.
        from src.core.config_loader import current_tenant

        try:
            current_tenant.set(None)
            logger.info("  ✓ Cleared tenant context (will force fresh lookup on next request)")
        except Exception as ctx_error:
            logger.warning(f"  ⚠️ Could not clear tenant context: {ctx_error}")

        return JSONResponse(
            {
                "status": "success",
                "message": "Database connection pool, provider cache, and tenant context reset successfully",
                "providers_cleared": provider_count,
            }
        )
    except Exception as e:
        logger.error(f"Failed to reset database state: {e}")
        return JSONResponse({"error": f"Failed to reset: {str(e)}"}, status_code=500)


@mcp.custom_route("/debug/db-state", methods=["GET"])
async def debug_db_state(request: Request):
    """Debug endpoint to show database state (testing only)."""
    if os.getenv("ADCP_TESTING") != "true":
        return JSONResponse({"error": "Only available in testing mode"}, status_code=403)

    try:
        from src.core.database.database_session import get_db_session

        with get_db_session() as session:
            # Count all products
            product_stmt = select(ModelProduct)
            all_products = session.scalars(product_stmt).all()

            # Get ci-test-token principal
            principal_stmt = select(ModelPrincipal).filter_by(access_token="ci-test-token")
            principal = session.scalars(principal_stmt).first()

            principal_info = None
            tenant_info = None
            tenant_products: list[ModelProduct] = []

            if principal:
                principal_info = {
                    "principal_id": principal.principal_id,
                    "tenant_id": principal.tenant_id,
                }

                # Get tenant
                tenant_stmt = select(Tenant).filter_by(tenant_id=principal.tenant_id)
                tenant = session.scalars(tenant_stmt).first()
                if tenant:
                    tenant_info = {
                        "tenant_id": tenant.tenant_id,
                        "name": tenant.name,
                        "is_active": tenant.is_active,
                    }

                # Get products for that tenant
                tenant_product_stmt = select(ModelProduct).filter_by(tenant_id=principal.tenant_id)
                tenant_products = list(session.scalars(tenant_product_stmt).all())

            return JSONResponse(
                {
                    "total_products": len(all_products),
                    "principal": principal_info,
                    "tenant": tenant_info,
                    "tenant_products_count": len(tenant_products),
                    "tenant_product_ids": [p.product_id for p in tenant_products],
                }
            )
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@mcp.custom_route("/debug/tenant", methods=["GET"])
async def debug_tenant(request: Request):
    """Debug endpoint to check tenant detection from headers."""
    headers = dict(request.headers)

    # Check for Apx-Incoming-Host header
    apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")
    host_header = headers.get("host") or headers.get("Host")

    # Resolve tenant using same logic as auth
    tenant_id = None
    tenant_name = None
    detection_method = None

    # Try Apx-Incoming-Host first
    if apx_host:
        tenant = get_tenant_by_virtual_host(apx_host)
        if tenant:
            tenant_id = tenant.get("tenant_id")
            tenant_name = tenant.get("name")
            detection_method = "apx-incoming-host"

    # Try Host header subdomain
    if not tenant_id and host_header:
        subdomain = host_header.split(".")[0] if "." in host_header else None
        if subdomain and subdomain not in ["localhost", "adcp-sales-agent", "www", "sales-agent"]:
            tenant_id = subdomain
            detection_method = "host-subdomain"

    response_data = {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "detection_method": detection_method,
        "apx_incoming_host": apx_host,
        "host": host_header,
    }

    # Add X-Tenant-Id header to response
    response = JSONResponse(response_data)
    if tenant_id:
        response.headers["X-Tenant-Id"] = tenant_id

    return response


@mcp.custom_route("/debug/root", methods=["GET"])
async def debug_root(request: Request):
    """Debug endpoint to test root route logic without redirects."""
    headers = dict(request.headers)

    # Check for Apx-Incoming-Host header (Approximated.app virtual host)
    # Try both capitalized and lowercase versions since HTTP header names are case-insensitive
    apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")
    # Also check standard Host header for direct virtual hosts
    host_header = headers.get("host") or headers.get("Host")

    virtual_host = apx_host or host_header

    # Get tenant
    tenant = get_tenant_by_virtual_host(virtual_host) if virtual_host else None

    debug_info = {
        "all_headers": headers,
        "apx_host": apx_host,
        "host_header": host_header,
        "virtual_host": virtual_host,
        "tenant_found": tenant is not None,
        "tenant_id": tenant.get("tenant_id") if tenant else None,
        "tenant_name": tenant.get("name") if tenant else None,
    }

    # Also test landing page generation
    if tenant:
        try:
            html_content = generate_tenant_landing_page(tenant, virtual_host)
            debug_info["landing_page_generated"] = True
            debug_info["landing_page_length"] = len(html_content)
        except Exception as e:
            debug_info["landing_page_generated"] = False
            debug_info["landing_page_error"] = str(e)

    return JSONResponse(debug_info)


@mcp.custom_route("/debug/landing", methods=["GET"])
async def debug_landing(request: Request):
    """Debug endpoint to test landing page generation directly."""
    headers = dict(request.headers)

    # Same logic as root route
    apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")
    host_header = headers.get("host") or headers.get("Host")
    virtual_host = apx_host or host_header

    if virtual_host:
        tenant = get_tenant_by_virtual_host(virtual_host)
        if tenant:
            try:
                html_content = generate_tenant_landing_page(tenant, virtual_host)
                return HTMLResponse(content=html_content)
            except Exception as e:
                return JSONResponse({"error": f"Landing page generation failed: {e}"}, status_code=500)

    return JSONResponse({"error": "No tenant found"}, status_code=404)


@mcp.custom_route("/debug/root-logic", methods=["GET"])
async def debug_root_logic(request: Request):
    """Debug endpoint that exactly mimics the root route logic for testing."""
    headers = dict(request.headers)

    # Exact same logic as root route
    apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")
    host_header = headers.get("host") or headers.get("Host")
    virtual_host = apx_host or host_header

    debug_info: dict[str, Any] = {
        "step": "initial",
        "virtual_host": virtual_host,
        "apx_host": apx_host,
        "host_header": host_header,
    }

    if virtual_host:
        debug_info["step"] = "virtual_host_found"

        # First try to look up tenant by exact virtual host match
        tenant = get_tenant_by_virtual_host(virtual_host)
        debug_info["exact_tenant_lookup"] = tenant is not None

        # If no exact match, check for domain-based routing patterns
        if not tenant and ".sales-agent.scope3.com" in virtual_host and not virtual_host.startswith("admin."):
            debug_info["step"] = "subdomain_fallback"
            subdomain = virtual_host.split(".sales-agent.scope3.com")[0]
            debug_info["extracted_subdomain"] = subdomain

            # This is the fallback logic we don't need for test-agent
            try:
                with get_db_session() as db_session:
                    stmt = select(Tenant).filter_by(subdomain=subdomain, is_active=True)
                    tenant_obj = db_session.scalars(stmt).first()
                    if tenant_obj:
                        debug_info["subdomain_tenant_found"] = True
                        # Build tenant dict...
                    else:
                        debug_info["subdomain_tenant_found"] = False
            except Exception as e:
                debug_info["subdomain_error"] = str(e)

        if tenant:
            debug_info["step"] = "tenant_found"
            debug_info["tenant_id"] = tenant.get("tenant_id")
            debug_info["tenant_name"] = tenant.get("name")

            # Try landing page generation
            try:
                html_content = generate_tenant_landing_page(tenant, virtual_host)
                debug_info["step"] = "landing_page_success"
                debug_info["landing_page_length"] = len(html_content)
                debug_info["would_return"] = "HTMLResponse"
            except Exception as e:
                debug_info["step"] = "landing_page_error"
                debug_info["error"] = str(e)
                debug_info["would_return"] = "fallback HTMLResponse"
        else:
            debug_info["step"] = "no_tenant_found"
            debug_info["would_return"] = "redirect to /admin/"
    else:
        debug_info["step"] = "no_virtual_host"
        debug_info["would_return"] = "redirect to /admin/"

    return JSONResponse(debug_info)


@mcp.custom_route("/health/config", methods=["GET"])
async def health_config(request: Request):
    """Configuration health check endpoint."""
    try:
        from src.core.startup import validate_startup_requirements

        validate_startup_requirements()
        return JSONResponse(
            {
                "status": "healthy",
                "service": "mcp",
                "component": "configuration",
                "message": "All configuration validation passed",
            }
        )
    except Exception as e:
        return JSONResponse(
            {"status": "unhealthy", "service": "mcp", "component": "configuration", "error": str(e)}, status_code=500
        )


# Add admin UI routes when running unified
unified_mode = os.environ.get("ADCP_UNIFIED_MODE")
logger.info(f"STARTUP: ADCP_UNIFIED_MODE = '{unified_mode}' (type: {type(unified_mode)})")
if unified_mode:
    from fastapi.middleware.wsgi import WSGIMiddleware
    from fastapi.responses import HTMLResponse, RedirectResponse

    from src.admin.app import create_app

    # Create Flask app and get the app instance
    flask_admin_app, _ = create_app()

    # Create WSGI middleware for Flask app
    admin_wsgi = WSGIMiddleware(flask_admin_app)

    logger.info("STARTUP: Registering unified mode routes...")

    logger.info("STARTUP: ADCP_UNIFIED_MODE enabled, registering routes...")

    async def handle_landing_page(request: Request):
        """Common landing page logic for both root and /landing routes."""
        headers = dict(request.headers)
        apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")

        # Check if this is an external domain request
        if apx_host and apx_host.endswith(".adcontextprotocol.org"):
            # Look up tenant by virtual host
            tenant = get_tenant_by_virtual_host(apx_host)

            if tenant:
                # Generate tenant landing page
                try:
                    html_content = generate_tenant_landing_page(tenant, apx_host)
                    return HTMLResponse(content=html_content)
                except Exception as e:
                    logger.error(f"Error generating landing page: {e}", exc_info=True)
                    return HTMLResponse(
                        content=f"""
                    <html>
                    <body>
                    <h1>Welcome to {tenant.get("name", "AdCP Sales Agent")}</h1>
                    <p>This is a sales agent for advertising inventory.</p>
                    <p>Domain: {apx_host}</p>
                    </body>
                    </html>
                    """
                    )

        # Check if this is a subdomain request
        if apx_host and ".sales-agent.scope3.com" in apx_host:
            # Extract subdomain from apx_host
            subdomain = apx_host.split(".sales-agent.scope3.com")[0]

            # Look up tenant by subdomain
            try:
                with get_db_session() as db_session:
                    stmt = select(Tenant).filter_by(subdomain=subdomain, is_active=True)
                    tenant_obj = db_session.scalars(stmt).first()
                    if tenant_obj:
                        tenant = {
                            "tenant_id": tenant_obj.tenant_id,
                            "name": tenant_obj.name,
                            "subdomain": tenant_obj.subdomain,
                            "virtual_host": tenant_obj.virtual_host,
                        }
                        # Generate tenant landing page for subdomain
                        try:
                            html_content = generate_tenant_landing_page(tenant, apx_host)
                            return HTMLResponse(content=html_content)
                        except Exception as e:
                            logger.error(f"Error generating subdomain landing page: {e}", exc_info=True)
                            return HTMLResponse(
                                content=f"""
                            <html>
                            <body>
                            <h1>Welcome to {tenant.get("name", "AdCP Sales Agent")}</h1>
                            <p>Subdomain: {apx_host}</p>
                            </body>
                            </html>
                            """
                            )
            except Exception as e:
                logger.error(f"Error looking up subdomain {subdomain}: {e}")

        # Fallback for unrecognized domains
        return HTMLResponse(
            content=f"""
        <html>
        <body>
        <h1>🎉 LANDING PAGE WORKING!</h1>
        <p>Domain: {apx_host}</p>
        <p>Success! The landing page is working.</p>
        </body>
        </html>
        """
        )

    # Task Management Tools (for HITL)

    @mcp.tool
    def list_tasks(
        status: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        context: Context | None = None,
    ) -> dict[str, Any]:
        """List workflow tasks with filtering options.

        Args:
            status: Filter by task status ("pending", "in_progress", "completed", "failed", "requires_approval")
            object_type: Filter by object type ("media_buy", "creative", "product")
            object_id: Filter by specific object ID
            limit: Maximum number of tasks to return (default: 20)
            offset: Number of tasks to skip (default: 0)
            context: MCP context (automatically provided)

        Returns:
            Dict containing tasks list and pagination info
        """

        # Get tenant and principal info
        tenant = get_current_tenant()
        # Import here to avoid circular dependency
        from src.core.tools.signals import _get_principal_id_from_context  # type: ignore[attr-defined]

        principal_id = _get_principal_id_from_context(context)

        with get_db_session() as session:
            # Base query for workflow steps in this tenant
            # TODO: Fix this - Context should not be joined here
            stmt = select(WorkflowStep).filter(WorkflowStep.tenant_id == tenant["tenant_id"])  # type: ignore[attr-defined]

            # Apply status filter
            if status:
                stmt = stmt.where(WorkflowStep.status == status)

            # Apply object type/ID filters
            if object_type and object_id:
                stmt = stmt.join(ObjectWorkflowMapping).where(
                    ObjectWorkflowMapping.object_type == object_type, ObjectWorkflowMapping.object_id == object_id
                )
            elif object_type:
                stmt = stmt.join(ObjectWorkflowMapping).where(ObjectWorkflowMapping.object_type == object_type)

            # Get total count before pagination
            from sqlalchemy import func

            total = session.scalar(select(func.count()).select_from(stmt.subquery()))

            # Apply pagination and ordering
            tasks = session.scalars(stmt.order_by(WorkflowStep.created_at.desc()).offset(offset).limit(limit)).all()

            # Format tasks for response
            formatted_tasks = []
            for task in tasks:
                # Get associated objects
                mapping_stmt = select(ObjectWorkflowMapping).filter_by(step_id=task.step_id)
                mappings = session.scalars(mapping_stmt).all()

                formatted_task = {
                    "task_id": task.step_id,
                    "status": task.status,
                    "type": task.step_type,
                    "tool_name": task.tool_name,
                    "owner": task.owner,
                    "created_at": task.created_at.isoformat() if hasattr(task.created_at, "isoformat") else str(task.created_at),  # type: ignore[union-attr]
                    "updated_at": None,  # WorkflowStep doesn't have updated_at field
                    "context_id": task.context_id,
                    "associated_objects": [
                        {"type": m.object_type, "id": m.object_id, "action": m.action} for m in mappings  # type: ignore[attr-defined]
                    ],
                }

                # Add error message if failed
                if task.status == "failed" and task.error_message:
                    formatted_task["error_message"] = task.error_message

                # Add basic request info if available
                if task.request_data:
                    if isinstance(task.request_data, dict):
                        formatted_task["summary"] = {
                            "operation": task.request_data.get("operation"),
                            "media_buy_id": task.request_data.get("media_buy_id"),
                            "po_number": (
                                task.request_data.get("request", {}).get("po_number")
                                if task.request_data.get("request")
                                else None
                            ),
                        }

                formatted_tasks.append(formatted_task)

            return {
                "tasks": formatted_tasks,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total if total is not None else False,
            }

    @mcp.tool
    def get_task(task_id: str, context: Context | None = None) -> dict[str, Any]:
        """Get detailed information about a specific task.

        Args:
            task_id: The unique task/workflow step ID
            context: MCP context (automatically provided)

        Returns:
            Dict containing complete task details
        """

        # Get tenant info
        tenant = get_current_tenant()
        principal_id = _get_principal_id_from_context(context)

        with get_db_session() as session:
            # Find the task in this tenant
            stmt = (
                select(WorkflowStep)
                .join(Context)
                .where(WorkflowStep.step_id == task_id, Context.tenant_id == tenant["tenant_id"])
            )
            task = session.scalars(stmt).first()

            if not task:
                raise ValueError(f"Task {task_id} not found")

            # Get associated objects
            mapping_stmt2 = select(ObjectWorkflowMapping).filter_by(step_id=task_id)
            mappings = session.scalars(mapping_stmt2).all()

            # Build detailed response
            task_detail = {
                "task_id": task.step_id,
                "context_id": task.context_id,
                "status": task.status,
                "type": task.step_type,
                "tool_name": task.tool_name,
                "owner": task.owner,
                "created_at": task.created_at.isoformat() if hasattr(task.created_at, "isoformat") else str(task.created_at),  # type: ignore[union-attr]
                "updated_at": None,  # WorkflowStep doesn't have updated_at field
                "request_data": task.request_data,
                "response_data": task.response_data,
                "error_message": task.error_message,
                "associated_objects": [
                    {
                        "type": m.object_type,  # type: ignore[attr-defined]
                        "id": m.object_id,  # type: ignore[attr-defined]
                        "action": m.action,  # type: ignore[attr-defined]
                        "created_at": m.created_at.isoformat() if hasattr(m.created_at, "isoformat") else str(m.created_at),  # type: ignore[union-attr]
                    }
                    for m in mappings
                ],
            }

            return task_detail

    @mcp.tool
    def complete_task(
        task_id: str,
        status: str = "completed",
        response_data: dict[str, Any] | None = None,
        error_message: str | None = None,
        context: Context | None = None,
    ) -> dict[str, Any]:
        """Complete a pending task (simulates human approval or async completion).

        Args:
            task_id: The unique task/workflow step ID
            status: New status ("completed" or "failed")
            response_data: Optional response data for completed tasks
            error_message: Error message if status is "failed"
            context: MCP context (automatically provided)

        Returns:
            Dict containing task completion status
        """

        # Get tenant info
        tenant = get_current_tenant()
        principal_id = _get_principal_id_from_context(context)

        if status not in ["completed", "failed"]:
            raise ValueError(f"Invalid status '{status}'. Must be 'completed' or 'failed'")

        with get_db_session() as session:
            # Find the task in this tenant
            stmt = (
                select(WorkflowStep)
                .join(Context)
                .where(WorkflowStep.step_id == task_id, Context.tenant_id == tenant["tenant_id"])
            )
            task = session.scalars(stmt).first()

            if not task:
                raise ValueError(f"Task {task_id} not found")

            if task.status not in ["pending", "in_progress", "requires_approval"]:
                raise ValueError(f"Task {task_id} is already {task.status} and cannot be completed")

            # Update task status
            task.status = status
            task.updated_at = datetime.now(UTC)

            if status == "completed":
                task.response_data = response_data or {"manually_completed": True, "completed_by": principal_id}
                task.error = None
            else:  # failed
                task.error = error_message or "Task marked as failed manually"
                if response_data:
                    task.response_data = response_data

            session.commit()

            # Log the completion
            audit_logger = get_audit_logger("task_management", tenant["tenant_id"])
            audit_logger.log_operation(
                operation="complete_task",
                principal_name="Manual Completion",
                principal_id=principal_id,
                adapter_id="system",
                success=True,
                details={
                    "task_id": task_id,
                    "new_status": status,
                    "original_status": "pending",  # We know it was pending/in_progress
                    "task_type": task.step_type,
                },
            )

            return {
                "task_id": task_id,
                "status": status,
                "message": f"Task {task_id} marked as {status}",
                "completed_at": task.updated_at.isoformat(),
                "completed_by": principal_id,
            }

    @mcp.custom_route("/", methods=["GET"])
    async def root(request: Request):
        """Root route handler for all domains."""
        return await handle_landing_page(request)

    @mcp.custom_route("/landing", methods=["GET"])
    async def landing_page(request: Request):
        """Landing page route for external domains."""
        return await handle_landing_page(request)

    logger.info("STARTUP: Registered root route")

    @mcp.custom_route(
        "/admin/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    )
    async def admin_handler(request: Request, path: str = ""):
        """Handle admin UI requests."""
        # Forward to Flask app
        scope = request.scope.copy()
        scope["path"] = f"/{path}" if path else "/"

        receive = request.receive
        send = request._send

        await admin_wsgi(scope, receive, send)

    @mcp.custom_route(
        "/tenant/{tenant_id}/admin/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    )
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


# Import MCP tools from separate modules at the end to avoid circular imports
# Tools are imported and then registered with MCP manually (no decorators in tool modules)
from src.core.tools.creative_formats import list_creative_formats  # noqa: E402, F401
from src.core.tools.creatives import list_creatives, sync_creatives  # noqa: E402, F401
from src.core.tools.media_buy_create import create_media_buy  # noqa: E402, F401
from src.core.tools.media_buy_delivery import get_media_buy_delivery  # noqa: E402, F401
from src.core.tools.media_buy_update import update_media_buy  # noqa: E402, F401
from src.core.tools.performance import update_performance_index  # noqa: E402, F401
from src.core.tools.products import get_products  # noqa: E402, F401
from src.core.tools.properties import list_authorized_properties  # noqa: E402, F401
from src.core.tools.signals import activate_signal, get_signals  # noqa: E402, F401

# Register tools with MCP (must be done after imports to avoid circular dependency)
# This breaks the circular import: tool modules no longer import mcp from main.py
mcp.tool()(get_products)
mcp.tool()(list_creative_formats)
mcp.tool()(sync_creatives)
mcp.tool()(list_creatives)
mcp.tool()(get_signals)
mcp.tool()(activate_signal)
mcp.tool()(list_authorized_properties)
mcp.tool()(create_media_buy)
mcp.tool()(update_media_buy)
mcp.tool()(get_media_buy_delivery)
mcp.tool()(update_performance_index)
