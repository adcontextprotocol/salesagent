"""
A2A Facade - Thin layer that adapts the TaskExecutor for A2A protocol.

This module provides a minimal A2A server that delegates all business logic
to the shared TaskExecutor, maintaining architectural symmetry with the MCP facade.
"""

import json
import logging
import os
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware

from task_executor import TaskExecutor, TaskStatus

logger = logging.getLogger(__name__)
from config_loader import set_current_tenant


class A2AFacade:
    """
    A2A Protocol facade over the TaskExecutor.
    
    This class adapts the task-based executor to work with the A2A protocol,
    handling authentication, context extraction, and response formatting.
    
    Mirrors the architecture of MCPFacade for consistency.
    """
    
    def __init__(self):
        self.executor = TaskExecutor()
        self.app = self._create_app()
        
    def _create_app(self) -> Starlette:
        """Create the Starlette app with A2A routes."""
        app = Starlette(
            routes=[
                Route("/", self._handle_agent_card, methods=["GET"]),
                Route("/", self._handle_rpc, methods=["POST"]),  # Also handle POST at root for compatibility
                Route("/.well-known/agent-card.json", self._handle_agent_card, methods=["GET"]),
                Route("/rpc", self._handle_rpc, methods=["POST"]),
            ]
        )
        
        # Add CORS for browser-based agents
        # NOTE: In production, replace with specific allowed origins
        allowed_origins = os.environ.get("A2A_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "x-adcp-auth", "x-adcp-tenant"],
        )
        
        return app
    
    def _authenticate_request(self, request: Request) -> Optional[str]:
        """Extract and authenticate principal from A2A request."""
        # Extract auth token
        auth_token = request.headers.get("x-adcp-auth")
        if not auth_token:
            return None
        
        # Extract tenant - default to "test" for now since we're using test data
        tenant_id = request.headers.get("x-adcp-tenant")
        if not tenant_id:
            host = request.headers.get("host", "")
            subdomain = host.split(".")[0] if "." in host else None
            if subdomain and subdomain not in ["localhost", "127", "0"]:
                tenant_id = subdomain
        tenant_id = tenant_id or "default"  # Use "default" as default tenant
        
        # Authenticate
        principal_id = self.executor.authenticate(auth_token, tenant_id)
        
        if principal_id:
            # Set tenant context
            self._set_tenant_context(tenant_id)
        
        return principal_id
    
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
    
    async def _handle_agent_card(self, request: Request) -> JSONResponse:
        """Return the Agent Card describing capabilities."""
        # Get the full URL for this request
        url = str(request.url).replace(request.url.path, "")
        
        agent_card = {
            "name": "ADCP Sales Agent",
            "version": "2.4",
            "description": "Advertising Context Protocol (AdCP) sales agent for managing programmatic advertising",
            "protocolVersion": "0.3.0",
            "url": f"{url}/rpc",  # URL should point to the RPC endpoint
            "rpcEndpoints": [
                {
                    "url": f"{url}/rpc",
                    "transport": "http",
                    "methods": ["POST"]
                }
            ],
            "capabilities": {
                "extensions": None,
                "pushNotifications": None,
                "stateTransitionHistory": None,
                "streaming": None
            },
            "skills": self._get_skills(),
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
            "supportsAuthenticatedExtendedCard": False,
            "securitySchemes": {
                "bearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Use x-adcp-auth header with your access token"
                }
            },
            "security": [{"bearer": []}]
        }
        return JSONResponse(agent_card)
    
    def _get_skills(self) -> list:
        """Get the list of A2A skills (agent abilities) - matches MCP tools exactly."""
        return [
            {
                "id": "get_products",
                "name": "get_products",
                "description": "Get available advertising products",
                "tags": ["advertising", "products", "discovery"],
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "brief": {"type": "string", "description": "Natural language description"},
                        "countries": {"type": "array", "items": {"type": "string"}},
                        "formats": {"type": "array", "items": {"type": "string"}},
                        "targeting_features": {"type": "object"},
                        "promoted_offering": {"type": "object"}
                    }
                }
            },
            {
                "id": "get_signals",
                "name": "get_signals",
                "description": "Discover available targeting signals",
                "tags": ["targeting", "signals", "discovery"],
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "type": {"type": "string", "enum": ["audience", "contextual", "geographic"]},
                        "category": {"type": "string"}
                    }
                }
            },
            {
                "id": "message/send",
                "name": "message/send",
                "description": "Send a message in the conversation",
                "tags": ["messaging", "conversation"],
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Message content"},
                        "context_id": {"type": "string", "description": "Conversation context ID"},
                        "metadata": {"type": "object", "description": "Optional metadata"}
                    },
                    "required": ["content"]
                }
            },
            {
                "id": "message/list",
                "name": "message/list",
                "description": "Get conversation messages",
                "tags": ["messaging", "conversation"],
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "context_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                        "offset": {"type": "integer", "default": 0}
                    }
                }
            },
            {
                "id": "context/clear",
                "name": "context/clear",
                "description": "Clear conversation context",
                "tags": ["context", "conversation"],
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "context_id": {"type": "string"}
                    },
                    "required": ["context_id"]
                }
            },
            {
                "id": "create_media_buy",
                "name": "create_media_buy",
                "description": "Create a new media buy campaign",
                "tags": ["campaign", "creation", "media-buy"],
                "inputSchema": {
                    "type": "object",
                    "required": ["product_ids", "total_budget", "flight_start_date", "flight_end_date"],
                    "properties": {
                        "product_ids": {"type": "array", "items": {"type": "string"}},
                        "total_budget": {"type": "number"},
                        "flight_start_date": {"type": "string", "format": "date"},
                        "flight_end_date": {"type": "string", "format": "date"},
                        "targeting_overlay": {"type": "object"},
                        "promoted_offering": {"type": "object"}
                    }
                }
            },
            {
                "id": "submit_creatives",
                "name": "submit_creatives",
                "description": "Submit creatives for a media buy",
                "tags": ["creative", "assets", "submission"],
                "inputSchema": {
                    "type": "object",
                    "required": ["media_buy_id", "creatives"],
                    "properties": {
                        "media_buy_id": {"type": "string"},
                        "creatives": {"type": "array"}
                    }
                }
            },
            {
                "id": "get_media_buy_status",
                "name": "get_media_buy_status",
                "description": "Get status of a media buy",
                "tags": ["monitoring", "status", "media-buy"],
                "inputSchema": {
                    "type": "object",
                    "required": ["media_buy_id"],
                    "properties": {
                        "media_buy_id": {"type": "string"}
                    }
                }
            },
            {
                "id": "update_media_buy",
                "name": "update_media_buy",
                "description": "Update a media buy",
                "tags": ["campaign", "update", "media-buy"],
                "inputSchema": {
                    "type": "object",
                    "required": ["media_buy_id", "updates"],
                    "properties": {
                        "media_buy_id": {"type": "string"},
                        "updates": {"type": "object"}
                    }
                }
            },
            {
                "id": "get_creative_status",
                "name": "get_creative_status",
                "description": "Get status of a creative",
                "tags": ["creative", "status", "monitoring"],
                "inputSchema": {
                    "type": "object",
                    "required": ["creative_id"],
                    "properties": {
                        "creative_id": {"type": "string"}
                    }
                }
            },
            {
                "id": "get_media_buy_delivery",
                "name": "get_media_buy_delivery",
                "description": "Get delivery metrics for a media buy",
                "tags": ["monitoring", "metrics", "analytics"],
                "inputSchema": {
                    "type": "object",
                    "required": ["media_buy_id"],
                    "properties": {
                        "media_buy_id": {"type": "string"},
                        "start_date": {"type": "string", "format": "date"},
                        "end_date": {"type": "string", "format": "date"}
                    }
                }
            },
            {
                "id": "get_targeting_capabilities",
                "name": "get_targeting_capabilities",
                "description": "Get available targeting dimensions",
                "tags": ["targeting", "capabilities", "discovery"],
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "channels": {"type": "array", "items": {"type": "string"}}
                    }
                }
            },
            {
                "id": "create_human_task",
                "name": "create_human_task",
                "description": "Create a task requiring human intervention",
                "tags": ["human-in-the-loop", "task", "approval"],
                "inputSchema": {
                    "type": "object",
                    "required": ["task_type", "description"],
                    "properties": {
                        "task_type": {"type": "string"},
                        "description": {"type": "string"},
                        "metadata": {"type": "object"}
                    }
                }
            },
            {
                "id": "verify_task",
                "name": "verify_task",
                "description": "Verify if a task was completed correctly",
                "tags": ["verification", "task", "human-in-the-loop"],
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string"}
                    }
                }
            }
        ]
    
    async def _handle_rpc(self, request: Request) -> JSONResponse:
        """Handle JSON-RPC 2.0 requests."""
        body = None
        try:
            # Parse request
            body = await request.json()
            
            # Validate JSON-RPC
            if body.get("jsonrpc") != "2.0":
                return self._error_response(-32600, "Invalid Request", body.get("id"))
            
            method = body.get("method")
            params = body.get("params", {})
            request_id = body.get("id")
            
            if not method:
                return self._error_response(-32600, "Invalid Request", request_id)
            
            # Authenticate
            principal_id = self._authenticate_request(request)
            if not principal_id:
                return self._error_response(-32000, "Authentication required", request_id)
            
            # Execute task via TaskExecutor
            result = await self._execute_task(method, params, principal_id)
            
            # Format response
            return JSONResponse({
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._error_response(-32603, str(e), body.get("id") if isinstance(body, dict) else None)
    
    async def _execute_task(self, method: str, params: Dict, principal_id: str) -> Dict:
        """Execute a task by mapping A2A method to TaskExecutor method."""
        
        # Extract context_id if provided
        context_id = params.get("context_id")
        
        # Map A2A methods to TaskExecutor methods (exact match with MCP tools)
        if method == "get_products":
            result = await self.executor.get_products(
                principal_id=principal_id,
                brief=params.get("brief"),
                countries=params.get("countries"),
                formats=params.get("formats"),
                targeting_features=params.get("targeting_features"),
                promoted_offering=params.get("promoted_offering"),
                context_id=context_id,
                protocol="a2a"
            )
            
        elif method == "get_signals":
            result = await self.executor.get_signals(
                principal_id=principal_id,
                query=params.get("query"),
                type=params.get("type"),
                category=params.get("category")
            )
            
        elif method == "message/send":
            # Handle both direct content and A2A Inspector's nested message format
            content = params.get("content")
            
            # Check if we have a nested message structure from A2A Inspector
            if not content and "message" in params:
                message = params["message"]
                if isinstance(message, dict) and "parts" in message:
                    parts = message.get("parts", [])
                    if parts and len(parts) > 0:
                        part = parts[0]
                        if isinstance(part, dict) and part.get("kind") == "text":
                            content = part.get("text", "")
            
            # Extract context_id from message or params
            context_id = params.get("context_id")
            if not context_id and "message" in params:
                context_id = params["message"].get("contextId")
            
            # Store the incoming user message
            self.executor.send_message(
                principal_id=principal_id,
                content=content or "",
                context_id=context_id,
                metadata={"role": "user", "source": "a2a_rpc"},
                protocol="a2a"
            )
            
            # Generate intelligent response based on content
            response_parts = []
            products_data = None
            
            if content:
                content_lower = content.lower()
                
                # Check for product/inventory queries
                if any(word in content_lower for word in ["product", "inventory", "sport", "video", "display", "audio"]):
                    try:
                        # Get products based on the query
                        product_result = await self.executor.get_products(
                            principal_id=principal_id,
                            brief=content,
                            context_id=context_id,
                            protocol="a2a"
                        )
                        
                        if hasattr(product_result, 'data') and product_result.data.get("products"):
                            products_data = product_result.data["products"]
                            if products_data:
                                # Add text summary
                                product_names = []
                                for p in products_data[:3]:  # Show top 3 products
                                    name = p.get('name', 'Unknown')
                                    product_names.append(name)
                                
                                summary_text = f"I found {len(products_data)} products matching your query. Here are the details:"
                                response_parts.append({
                                    "kind": "text",
                                    "text": summary_text
                                })
                                
                                # Add structured data part with full product details
                                response_parts.append({
                                    "kind": "data",
                                    "mimeType": "application/json",
                                    "data": {
                                        "type": "products",
                                        "products": products_data
                                    }
                                })
                            else:
                                response_parts.append({
                                    "kind": "text",
                                    "text": "I couldn't find any products matching your specific criteria. Could you provide more details about what type of inventory you're looking for?"
                                })
                        else:
                            response_parts.append({
                                "kind": "text",
                                "text": "I can help you find advertising inventory. Could you specify the type of media (display, video, audio) or targeting criteria you're interested in?"
                            })
                    except Exception as e:
                        logger.error(f"Error getting products: {e}")
                        response_parts.append({
                            "kind": "text",
                            "text": "I can help you explore our advertising inventory. What type of campaigns are you planning?"
                        })
                
                # Check for campaign/media buy queries
                elif any(word in content_lower for word in ["campaign", "media buy", "create", "budget"]):
                    response_parts.append({
                        "kind": "text",
                        "text": "I can help you create a media buy. To get started, I'll need to know your budget, campaign dates, and the products you're interested in. Would you like to see available products first?"
                    })
                
                # Check for status queries
                elif any(word in content_lower for word in ["status", "delivery", "performance", "metrics"]):
                    response_parts.append({
                        "kind": "text",
                        "text": "I can help you check campaign status and delivery metrics. Please provide the media buy ID you'd like to check."
                    })
                
                # Default helpful response
                else:
                    response_parts.append({
                        "kind": "text",
                        "text": "I can help you with: finding advertising inventory, creating media buys, submitting creatives, and checking campaign performance. What would you like to do?"
                    })
            else:
                response_parts.append({
                    "kind": "text",
                    "text": "I can help you with advertising inventory and media buying."
                })
            
            # Generate the response message ID
            import uuid
            from datetime import datetime
            response_message_id = f"msg_{uuid.uuid4().hex[:12]}"
            
            # Store the agent's response (just the text part for history)
            text_content = response_parts[0]["text"] if response_parts else ""
            self.executor.send_message(
                principal_id="agent",
                content=text_content,
                context_id=context_id,
                metadata={"role": "agent", "source": "a2a_agent", "has_data": products_data is not None},
                protocol="a2a"
            )
            
            # Return the A2A-compatible Message response with multiple parts
            result = {
                "kind": "message",
                "messageId": response_message_id,
                "role": "agent",
                "parts": response_parts,
                "contextId": context_id,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {}
            }
            
        elif method == "message/list":
            result = self.executor.get_messages(
                principal_id=principal_id,
                context_id=params.get("context_id"),
                limit=params.get("limit", 50),
                offset=params.get("offset", 0)
            )
            
        elif method == "context/clear":
            result = self.executor.clear_context(
                principal_id=principal_id,
                context_id=params.get("context_id")
            )
            
        elif method == "create_media_buy":
            result = self.executor.create_media_buy(
                principal_id=principal_id,
                product_ids=params.get("product_ids", []),
                total_budget=params.get("total_budget", 0),
                flight_start_date=params.get("flight_start_date"),
                flight_end_date=params.get("flight_end_date"),
                targeting_overlay=params.get("targeting_overlay"),
                promoted_offering=params.get("promoted_offering")
            )
            
        elif method == "submit_creatives":
            result = self.executor.submit_creatives(
                principal_id=principal_id,
                media_buy_id=params.get("media_buy_id"),
                creatives=params.get("creatives", [])
            )
            
        elif method == "get_media_buy_status":
            result = self.executor.get_media_buy_status(
                principal_id=principal_id,
                media_buy_id=params.get("media_buy_id")
            )
            
        elif method == "update_media_buy":
            result = self.executor.update_media_buy(
                principal_id=principal_id,
                media_buy_id=params.get("media_buy_id"),
                updates=params.get("updates", {})
            )
            
        elif method == "get_creative_status":
            result = self.executor.get_creative_status(
                principal_id=principal_id,
                creative_id=params.get("creative_id")
            )
            
        elif method == "get_media_buy_delivery":
            result = self.executor.get_media_buy_delivery(
                principal_id=principal_id,
                media_buy_id=params.get("media_buy_id"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date")
            )
            
        elif method == "get_targeting_capabilities":
            result = self.executor.get_targeting_capabilities(
                principal_id=principal_id,
                channels=params.get("channels")
            )
            
        elif method == "create_human_task":
            result = self.executor.create_human_task(
                principal_id=principal_id,
                task_type=params.get("task_type"),
                description=params.get("description"),
                metadata=params.get("metadata")
            )
            
        elif method == "verify_task":
            result = self.executor.verify_task(
                principal_id=principal_id,
                task_id=params.get("task_id")
            )
            
        else:
            raise ValueError(f"Method not found: {method}")
        
        # Format TaskResult for A2A response
        return self._format_a2a_response(result)
    
    def _format_a2a_response(self, task_result) -> Dict:
        """Format TaskExecutor result for A2A protocol."""
        # Handle direct dict responses (for messaging methods)
        if isinstance(task_result, dict):
            return task_result
            
        # Handle TaskResult objects - format as A2A Task
        response = {
            "kind": "task",
            "id": task_result.task_id,
            "status": {
                "state": task_result.status.value,
                "message": task_result.message if task_result.message else None
            },
            "artifact": task_result.data,
            "history": []  # Could add execution history here
        }
        
        # Add error details if failed
        if task_result.status.value == "failed" and task_result.error:
            response["status"]["error"] = task_result.error
        
        # Add policy compliance if present
        if task_result.data and task_result.data.get("policy_compliance"):
            response["policy_compliance"] = task_result.data["policy_compliance"]
        
        # Add clarification flag if needed
        if task_result.data and task_result.data.get("clarification_needed"):
            response["clarification_needed"] = True
        
        return response
    
    def _error_response(self, code: int, message: str, request_id: Any) -> JSONResponse:
        """Create a JSON-RPC error response."""
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            },
            "id": request_id
        })
    
    def get_app(self) -> Starlette:
        """Get the Starlette app instance."""
        return self.app


def create_a2a_facade() -> A2AFacade:
    """Create and return an A2A facade instance."""
    return A2AFacade()
