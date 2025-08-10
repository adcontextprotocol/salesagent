"""
MCP Facade - Thin layer that adapts the TaskExecutor for MCP protocol.

This module provides a minimal MCP server that delegates all business logic
to the shared TaskExecutor, maintaining backward compatibility with existing
MCP clients.
"""

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context

from task_executor import TaskExecutor, TaskStatus
from schemas import *
from config_loader import set_current_tenant
import json


class MCPFacade:
    """
    MCP Protocol facade over the TaskExecutor.
    
    This class adapts the task-based executor to work with the MCP protocol,
    handling authentication, context extraction, and response formatting.
    """
    
    def __init__(self):
        self.mcp = FastMCP(name="adcp-sales-agent")
        self.executor = TaskExecutor()
        self._register_tools()
    
    def _get_principal_from_context(self, context: Context) -> str:
        """Extract and authenticate principal from MCP context."""
        if not context:
            raise ToolError("No context provided")
        
        try:
            request = context.get_http_request()
            if not request:
                raise ToolError("No HTTP request in context")
            
            # Extract tenant
            tenant_id = request.headers.get('x-adcp-tenant')
            if not tenant_id:
                host = request.headers.get('host', '')
                subdomain = host.split('.')[0] if '.' in host else None
                if subdomain and subdomain != 'localhost':
                    tenant_id = subdomain
            tenant_id = tenant_id or 'default'
            
            # Extract auth token
            auth_token = request.headers.get('x-adcp-auth')
            if not auth_token:
                raise ToolError("Authentication required")
            
            # Authenticate
            principal_id = self.executor.authenticate(auth_token, tenant_id)
            if not principal_id:
                raise ToolError("Invalid authentication token")
            
            # Set tenant context
            self._set_tenant_context(tenant_id)
            
            return principal_id
            
        except Exception as e:
            raise ToolError(f"Authentication failed: {str(e)}")
    
    def _set_tenant_context(self, tenant_id: str):
        """Set the tenant context."""
        from db_config import get_db_connection
        
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
        
        if row:
            tenant_dict = {
                'tenant_id': row[0],
                'name': row[1],
                'subdomain': row[2],
                'ad_server': row[3],
                'max_daily_budget': row[4],
                'enable_aee_signals': row[5],
                'authorized_emails': json.loads(row[6]) if row[6] else [],
                'authorized_domains': json.loads(row[7]) if row[7] else [],
                'slack_webhook_url': row[8],
                'admin_token': row[9],
                'auto_approve_formats': json.loads(row[10]) if row[10] else [],
                'human_review_required': row[11],
                'slack_audit_webhook_url': row[12],
                'hitl_webhook_url': row[13],
                'policy_settings': json.loads(row[14]) if row[14] else {}
            }
            set_current_tenant(tenant_dict)
    
    def _register_tools(self):
        """Register all MCP tools that map to TaskExecutor methods."""
        
        @self.mcp.tool
        async def get_products(req: GetProductsRequest, context: Context) -> GetProductsResponse:
            """Get available advertising products."""
            principal_id = self._get_principal_from_context(context)
            
            result = await self.executor.get_products(
                principal_id=principal_id,
                brief=req.brief,
                countries=req.countries,
                formats=req.formats,
                targeting_features=req.targeting_features,
                promoted_offering=req.promoted_offering
            )
            
            if result.status == TaskStatus.FAILED:
                raise ToolError(result.error or result.message)
            
            # Format response with message field first (per ADCP v2.4)
            products = [Product(**p) for p in result.data.get("products", [])]
            
            response = GetProductsResponse(
                message=result.message,
                products=products,
                context_id=result.data.get("context_id")
            )
            
            # Add optional fields
            if result.data.get("clarification_needed"):
                response.clarification_needed = True
            
            if result.data.get("policy_compliance"):
                response.policy_compliance = result.data["policy_compliance"]
            
            return response
        
        @self.mcp.tool
        async def get_signals(req: GetSignalsRequest, context: Context) -> GetSignalsResponse:
            """Discover available targeting signals."""
            principal_id = self._get_principal_from_context(context)
            
            result = await self.executor.get_signals(
                principal_id=principal_id,
                query=req.query,
                type=req.type,
                category=req.category
            )
            
            if result.status == TaskStatus.FAILED:
                raise ToolError(result.error or result.message)
            
            # Format response
            signals = [Signal(**s) for s in result.data.get("signals", [])]
            
            return GetSignalsResponse(
                message=result.message,
                signals=signals,
                context_id=result.data.get("context_id")
            )
        
        @self.mcp.tool
        def create_media_buy(req: CreateMediaBuyRequest, context: Context) -> CreateMediaBuyResponse:
            """Create a new media buy campaign."""
            principal_id = self._get_principal_from_context(context)
            
            result = self.executor.create_media_buy(
                principal_id=principal_id,
                product_ids=req.product_ids,
                total_budget=req.total_budget,
                flight_start_date=req.flight_start_date,
                flight_end_date=req.flight_end_date,
                targeting_overlay=req.targeting_overlay,
                promoted_offering=req.promoted_offering
            )
            
            if result.status == TaskStatus.FAILED:
                raise ToolError(result.error or result.message)
            
            response = CreateMediaBuyResponse(
                message=result.message,
                media_buy_id=result.data.get("media_buy_id"),
                status=result.data.get("status"),
                context_id=result.data.get("context_id")
            )
            
            if result.data.get("policy_compliance"):
                response.policy_compliance = result.data["policy_compliance"]
            
            return response
        
        @self.mcp.tool
        def submit_creatives(req: SubmitCreativesRequest, context: Context) -> SubmitCreativesResponse:
            """Submit creatives for a media buy."""
            principal_id = self._get_principal_from_context(context)
            
            # Convert creative objects to dicts
            creatives = [c.model_dump() if hasattr(c, 'model_dump') else c for c in req.creatives]
            
            result = self.executor.submit_creatives(
                principal_id=principal_id,
                media_buy_id=req.media_buy_id,
                creatives=creatives
            )
            
            if result.status == TaskStatus.FAILED:
                raise ToolError(result.error or result.message)
            
            return SubmitCreativesResponse(
                message=result.message,
                creative_ids=result.data.get("creative_ids", []),
                context_id=result.data.get("context_id")
            )
        
        @self.mcp.tool
        def get_media_buy_delivery(req: GetMediaBuyDeliveryRequest, context: Context) -> GetMediaBuyDeliveryResponse:
            """Get delivery metrics for a media buy."""
            principal_id = self._get_principal_from_context(context)
            
            result = self.executor.get_media_buy_delivery(
                principal_id=principal_id,
                media_buy_id=req.media_buy_id,
                start_date=req.start_date,
                end_date=req.end_date
            )
            
            if result.status == TaskStatus.FAILED:
                raise ToolError(result.error or result.message)
            
            # Create mock packages for response
            packages = []
            if result.data.get("metrics"):
                metrics = result.data["metrics"]
                packages.append(
                    PackageDelivery(
                        package_id="pkg_001",
                        product_id="prod_001",
                        impressions=metrics.get("impressions", 0),
                        clicks=metrics.get("clicks", 0),
                        spend=metrics.get("spend", 0),
                        ctr=metrics.get("ctr", 0),
                        cpm=metrics.get("cpm", 0)
                    )
                )
            
            return GetMediaBuyDeliveryResponse(
                message=result.message,
                media_buy_id=req.media_buy_id,
                status=result.data.get("status", "unknown"),
                packages=packages,
                context_id=result.data.get("context_id")
            )
        
        @self.mcp.tool
        def get_targeting_capabilities(req: GetTargetingCapabilitiesRequest, context: Context) -> GetTargetingCapabilitiesResponse:
            """Get available targeting dimensions."""
            principal_id = self._get_principal_from_context(context)
            
            result = self.executor.get_targeting_capabilities(
                principal_id=principal_id,
                channels=req.channels
            )
            
            if result.status == TaskStatus.FAILED:
                raise ToolError(result.error or result.message)
            
            return GetTargetingCapabilitiesResponse(
                message=result.message,
                overlay_dimensions=result.data.get("overlay_dimensions", {}),
                context_id=result.data.get("context_id")
            )
        
        @self.mcp.tool
        def create_human_task(req: CreateHumanTaskRequest, context: Context) -> CreateHumanTaskResponse:
            """Create a task requiring human intervention."""
            principal_id = self._get_principal_from_context(context)
            
            result = self.executor.create_human_task(
                principal_id=principal_id,
                task_type=req.task_type,
                description=req.description,
                metadata=req.metadata
            )
            
            if result.status == TaskStatus.FAILED:
                raise ToolError(result.error or result.message)
            
            return CreateHumanTaskResponse(
                message=result.message,
                task_id=result.data.get("task_id"),
                status=result.data.get("status"),
                context_id=result.data.get("context_id")
            )
        
        @self.mcp.tool
        def verify_task(req: VerifyTaskRequest, context: Context) -> VerifyTaskResponse:
            """Verify if a task was completed correctly."""
            principal_id = self._get_principal_from_context(context)
            
            result = self.executor.verify_task(
                principal_id=principal_id,
                task_id=req.task_id
            )
            
            if result.status == TaskStatus.FAILED:
                raise ToolError(result.error or result.message)
            
            return VerifyTaskResponse(
                message=result.message,
                task_id=req.task_id,
                verified=result.data.get("verified", False),
                details=result.data.get("details"),
                context_id=result.data.get("context_id")
            )
    
    def get_server(self) -> FastMCP:
        """Get the FastMCP server instance."""
        return self.mcp


def create_mcp_facade() -> MCPFacade:
    """Create and return an MCP facade instance."""
    return MCPFacade()