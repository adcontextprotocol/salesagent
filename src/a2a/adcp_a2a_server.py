#!/usr/bin/env python3
"""
AdCP Sales Agent A2A Server using python-a2a library.
This is a standard implementation using python-a2a's base classes.
No custom protocol code - just business logic.
"""

import logging
import os
import sys
from functools import wraps
from typing import Any

# Flask imports for authentication
from flask import g, jsonify, request
from python_a2a.models import AgentCard, AgentSkill, Task, TaskState, TaskStatus

# Standard python-a2a imports
from python_a2a.server import A2AServer

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Also add the app root for absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import MCP client for AdCP integration
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

# Import database models for authentication
from core.database.database_session import get_db_session
from src.core.database.models import Principal, Tenant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AdCPSalesAgent(A2AServer):
    """Standard python-a2a server implementation for AdCP Sales Agent."""

    # Class attributes for agent metadata (used by python-a2a)
    name = "AdCP Sales Agent"
    description = "AI agent for advertising campaign management via AdCP protocol"
    version = "2.0.0"

    def __init__(self):
        # Create agent card with skills
        # Use production URL for deployed server, localhost for development
        # Check if we're running in production (Fly.io sets FLY_APP_NAME)
        if os.getenv("FLY_APP_NAME") or os.getenv("PRODUCTION") == "true":
            server_url = "https://adcp-sales-agent.fly.dev/a2a/"  # Force production URL with trailing slash
        else:
            server_url = "http://localhost:8091"  # Use localhost in development

        agent_card = AgentCard(
            name=self.name,
            description=self.description,
            url=server_url,
            version=self.version,
            authentication="bearer-token",  # Indicate auth is required
            skills=[
                # Match AdCP specification skills from MCP server
                AgentSkill(name="get_products", description="Retrieve available advertising products and inventory"),
                AgentSkill(name="create_media_buy", description="Create a new media buy for advertising campaigns"),
                AgentSkill(name="get_media_buy_status", description="Check the status of an existing media buy"),
                AgentSkill(name="update_media_buy", description="Update an existing media buy configuration"),
                AgentSkill(name="approve_creative", description="Approve a creative for use in campaigns"),
                AgentSkill(name="assign_creative", description="Assign approved creatives to media packages"),
            ],
            # Enable Google A2A compatibility
            capabilities={
                "google_a2a_compatible": True,  # Enable Google A2A compatibility
                "parts_array_format": True,  # Use parts array format for messages
            },
        )

        # Initialize parent with agent card
        super().__init__(agent_card=agent_card)

        # Enable Google A2A compatibility mode in the library
        self._use_google_a2a = True

        # MCP server configuration
        self.mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp/")
        # Token will be set per request based on authentication
        self.current_token = None  # Will be set during authenticated requests
        self.current_tenant = None  # Will be set during authenticated requests
        self.current_principal = None  # Will be set during authenticated requests
        logger.info(f"AdCP A2A Agent initialized - MCP Server: {self.mcp_url}")

    def require_auth(self, f):
        """Decorator to check authentication before handling requests."""

        @wraps(f)
        def decorated(*args, **kwargs):
            # Get token from various sources
            token = None

            # 1. Check Authorization header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

            # 2. Check custom header
            if not token:
                token = request.headers.get("X-Auth-Token")

            # 3. Check query parameter (for CLI compatibility)
            if not token:
                token = request.args.get("token")

            # 4. Check environment variable (for standard library compatibility)
            if not token:
                token = os.environ.get("A2A_AUTH_TOKEN")

            if not token:
                logger.warning(f"No auth token provided for {request.path}")
                return jsonify({"error": "Authentication required"}), 401

            # Validate token against database
            try:
                with get_db_session() as session:
                    principal = session.query(Principal).filter_by(access_token=token).first()

                    if not principal:
                        logger.warning(f"Invalid token: {token[:10]}...")
                        return jsonify({"error": "Invalid authentication token"}), 401

                    # Get tenant
                    tenant = session.query(Tenant).filter_by(tenant_id=principal.tenant_id).first()

                    if not tenant:
                        logger.error(f"Tenant not found for principal {principal.principal_id}")
                        return jsonify({"error": "Tenant configuration error"}), 500

                    # Store in Flask g object and instance variables
                    g.principal = principal
                    g.tenant = tenant
                    g.token = token

                    # Store in instance for use in async methods
                    self.current_token = token
                    self.current_tenant = tenant
                    self.current_principal = principal

                    logger.info(f"Authenticated: {principal.name} (tenant: {tenant.name})")

            except Exception as e:
                logger.error(f"Authentication error: {e}")
                return jsonify({"error": "Authentication failed"}), 500

            return f(*args, **kwargs)

        return decorated

    def setup_routes(self, app):
        """Add our custom authenticated routes to the standard A2A Flask app.

        Note: Standard routes (/.well-known/agent.json, /a2a, /agent.json, etc.)
        are automatically provided by create_flask_app().
        """

        # Store app reference
        self.app = app

        # Note: We don't need to add /agent.json or / routes since they're provided by create_flask_app()
        # The library provides: /, /a2a, /agent.json, /.well-known/agent.json, /stream

        @app.route("/health", methods=["GET"])
        def custom_health_check():
            """Custom health check endpoint (different from library's /a2a/health)."""
            return jsonify({"status": "healthy"})

        # TEMPORARILY DISABLED - Testing library's default routes
        # Protected endpoints (auth required)
        # @app.route("/tasks/send", methods=["POST"])
        # @self.require_auth
        # def authenticated_task_send():
        #     """Protected endpoint - requires authentication."""
        #     # Process task with authentication context
        #     data = request.json or {}

        #     # Create task from request data
        #     # Ensure message is in the expected format
        #     message_content = data.get("message", data.get("text", ""))
        #     if isinstance(message_content, str):
        #         message_data = {"content": {"text": message_content}}
        #     else:
        #         message_data = message_content

        #     task = Task(
        #         id=data.get("id", str(uuid.uuid4())), message=message_data, status=TaskStatus(state=TaskState.SUBMITTED)
        #     )

        #     # Process with tenant context
        #     result = self.handle_task(task)

        #     # Return result
        #     if hasattr(result, "to_dict"):
        #         return jsonify(result.to_dict())
        #     else:
        #         return jsonify(result)

        # @app.route("/tasks/<task_id>", methods=["GET"])
        # @self.require_auth
        # def authenticated_task_get(task_id):
        #     """Protected endpoint - requires authentication."""
        #     # In production, would fetch task status from database
        #     return jsonify(
        #         {
        #             "id": task_id,
        #             "status": {"state": "completed"},
        #             "tenant": self.current_tenant.name if self.current_tenant else "unknown",
        #         }
        #     )

        # @app.route("/message", methods=["POST"])
        # @self.require_auth
        # def authenticated_message():
        #     """Protected endpoint - requires authentication."""
        #     # Process message with authentication context
        #     data = request.json or {}

        #     # Create task from message
        #     # Ensure message is in the expected format
        #     if isinstance(data, str):
        #         message_data = {"content": {"text": data}}
        #     elif "content" not in data:
        #         # Wrap the entire data as content if it doesn't have content key
        #         message_data = {"content": data}
        #     else:
        #         message_data = data

        #     task = Task(id=str(uuid.uuid4()), message=message_data, status=TaskStatus(state=TaskState.SUBMITTED))

        #     # Process with tenant context
        #     result = self.handle_task(task)

        #     # Return result
        #     if hasattr(result, "to_dict"):
        #         return jsonify(result.to_dict())
        #     else:
        #         return jsonify(result)

    async def get_products(self, query: str = "") -> dict[str, Any]:
        """Get available advertising products."""
        try:
            # Use authenticated token if available, otherwise fall back
            token = self.current_token if self.current_token else os.getenv("MCP_AUTH_TOKEN", "test_principal_token")

            # Create MCP client with authenticated token
            headers = {"x-adcp-auth": token}
            transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

            async with Client(transport=transport) as client:
                # Call get_products tool - MCP tools expect params wrapped in 'req'
                # promoted_offering is REQUIRED per AdCP spec
                params = {
                    "req": {
                        "brief": query if query else "General advertising inquiry",
                        "promoted_offering": f"Products and services from {self.current_principal.name if self.current_principal else 'advertiser'}",
                    }
                }
                result = await client.call_tool("get_products", params)

                # The result is a CallToolResult object with structured_content
                if (
                    result
                    and hasattr(result, "structured_content")
                    and result.structured_content
                    and "products" in result.structured_content
                ):
                    products = result.structured_content["products"]
                    if not products:
                        return {"message": "No products are currently available."}

                    product_list = []
                    for product in products[:10]:  # Limit to first 10
                        # Product is a dict
                        product_info = {
                            "name": product.get("name", "Unknown"),
                            "id": product.get("product_id", "unknown"),
                            "formats": [f.get("format_id", "") for f in product.get("formats", [])],
                        }
                        # Handle pricing info
                        if product.get("is_fixed_price") and product.get("cpm"):
                            product_info["pricing"] = f"CPM ${product['cpm']}"
                        elif product.get("price_guidance"):
                            pg = product["price_guidance"]
                            floor = pg.get("floor", 0)
                            p50 = pg.get("p50", 0)
                            product_info["pricing"] = f"CPM ${floor}-{p50}" if p50 else f"CPM ${floor}+"
                        product_list.append(product_info)

                    return {
                        "products": product_list,
                        "total": len(products),
                        "message": f"Found {len(products)} advertising products",
                    }
                else:
                    return self._get_mock_products()

        except Exception as e:
            logger.error(f"Error getting products from MCP: {e}")
            # Fallback to mock data
            return self._get_mock_products()

    async def create_campaign(
        self, product_ids: list[str], budget: float, start_date: str, end_date: str
    ) -> dict[str, Any]:
        """Create a new advertising campaign."""
        try:
            # Use authenticated token
            token = self.current_token if self.current_token else os.getenv("MCP_AUTH_TOKEN", "test_principal_token")
            headers = {"x-adcp-auth": token}
            transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

            async with Client(transport=transport) as client:
                # MCP tools expect params wrapped in 'req'
                params = {
                    "req": {
                        "product_ids": product_ids,
                        "budget": budget,
                        "start_date": start_date,
                        "end_date": end_date,
                    }
                }
                result = await client.call_tool("create_media_buy", params)

                if result:
                    # Extract media_buy_id from structured_content
                    media_buy_id = "unknown"
                    if hasattr(result, "structured_content") and result.structured_content:
                        media_buy_id = result.structured_content.get("media_buy_id", "unknown")
                    elif hasattr(result, "media_buy_id"):
                        media_buy_id = result.media_buy_id

                    return {
                        "success": True,
                        "media_buy_id": media_buy_id,
                        "message": f"Campaign {media_buy_id} created successfully",
                    }
                else:
                    return {"success": False, "message": "No result from MCP server"}

        except Exception as e:
            logger.error(f"Error creating campaign: {e}")
            return {"success": False, "error": str(e), "message": "Failed to create campaign"}

    def get_targeting(self) -> dict[str, Any]:
        """Get available targeting options."""
        return {
            "targeting_options": {
                "geographic": ["Country", "State/Region", "DMA", "Postal Code"],
                "demographic": ["Age ranges", "Gender", "Household income"],
                "behavioral": ["Interest categories", "Purchase intent", "Content affinity"],
                "contextual": ["Content categories", "Keywords", "Topics"],
                "device": ["Desktop", "Mobile", "Tablet", "Connected TV"],
                "custom": ["First-party data segments", "Lookalike audiences"],
            },
            "message": "Multiple targeting dimensions available",
        }

    def get_pricing(self) -> dict[str, Any]:
        """Get pricing information."""
        return {
            "pricing_models": {
                "CPM": {"premium": "$25-60", "standard": "$8-25", "remnant": "$2-8"},
                "CPC": {"search": "$0.50-5.00", "display": "$0.20-2.00"},
                "CPA": {"leads": "$20-200", "installs": "$2-10"},
                "Fixed": {"homepage_takeover": "$10,000-50,000/day", "newsletter": "$2,000-10,000/week"},
            },
            "minimum_budget": "$500",
            "volume_discounts": "Available for budgets over $10,000",
        }

    def handle_task(self, task: Task) -> Task:
        """
        Handle incoming tasks using python-a2a's standard task processing.
        This is called automatically by the python-a2a framework.
        """
        try:
            # Extract message text
            message_data = task.message or {}
            content = message_data.get("content", {})

            # Handle both dict and string content
            if isinstance(content, dict):
                # Try multiple possible field names for the text content
                text = content.get("text", "") or content.get("message", "") or str(content)
            else:
                text = str(content)

            logger.info(f"Processing task: {text[:100]}...")

            # Route based on keywords and return structured data per AdCP spec
            text_lower = text.lower()

            if any(word in text_lower for word in ["create", "campaign", "buy"]):
                # Parse message and actually create the media buy
                import asyncio
                import re

                # Extract product ID
                product_match = re.search(r"prod_\d+", text_lower)
                product_ids = [product_match.group(0)] if product_match else ["prod_1"]

                # Extract budget
                budget_match = re.search(r"\$?([\d,]+(?:\.\d+)?)", text)
                budget = float(budget_match.group(1).replace(",", "")) if budget_match else 5000.0

                # Extract dates
                dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
                start_date = dates[0] if len(dates) >= 1 else "2025-09-01"
                end_date = dates[1] if len(dates) >= 2 else "2025-09-30"

                # Create the media buy
                logger.info(f"Creating media buy: {product_ids}, ${budget}, {start_date} to {end_date}")

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.create_campaign(product_ids, budget, start_date, end_date))

                # Return proper artifact
                if result.get("success"):
                    task.artifacts = [
                        {
                            "name": "media_buy_created",
                            "parts": [
                                {
                                    "kind": "application/json",
                                    "data": {
                                        "media_buy_id": result.get("media_buy_id", "unknown"),
                                        "status": "created",
                                        "products": product_ids,
                                        "budget": budget,
                                        "flight_dates": {"start": start_date, "end": end_date},
                                    },
                                }
                            ],
                        }
                    ]
                else:
                    task.artifacts = [
                        {"name": "media_buy_error", "parts": [{"kind": "application/json", "data": result}]}
                    ]

            elif any(word in text_lower for word in ["target", "audience"]):
                result = self.get_targeting()
                task.artifacts = [
                    {"name": "targeting_options", "parts": [{"kind": "application/json", "data": result}]}
                ]

            elif any(word in text_lower for word in ["price", "pricing", "cost", "cpm", "budget"]):
                result = self.get_pricing()
                task.artifacts = [
                    {"name": "pricing_information", "parts": [{"kind": "application/json", "data": result}]}
                ]

            elif any(word in text_lower for word in ["product", "inventory", "available", "catalog"]):
                # Handle product queries - return structured product data
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.get_products(text))

                # Create structured artifact per AdCP spec
                task.artifacts = [{"name": "product_catalog", "parts": [{"kind": "application/json", "data": result}]}]

            else:
                # General help response with structured capabilities
                capabilities = {
                    "supported_queries": [
                        "product_catalog",
                        "targeting_options",
                        "pricing_information",
                        "campaign_creation",
                    ],
                    "message": "I can help you with advertising inventory, targeting, pricing, and campaign creation",
                    "example_queries": [
                        "What video ad products do you have available?",
                        "Show me targeting options",
                        "What are your pricing models?",
                        "How do I create a media buy?",
                    ],
                }
                task.artifacts = [
                    {"name": "capabilities", "parts": [{"kind": "application/json", "data": capabilities}]}
                ]

            task.status = TaskStatus(state=TaskState.COMPLETED)

        except Exception as e:
            logger.error(f"Error handling task: {e}")
            # Error response following AdCP spec
            task.artifacts = [
                {
                    "name": "error_response",
                    "parts": [
                        {
                            "kind": "application/json",
                            "data": {"error": str(e), "message": "An error occurred while processing your request"},
                        }
                    ],
                }
            ]
            task.status = TaskStatus(state=TaskState.FAILED)

        return task

    def _get_mock_products(self) -> dict[str, Any]:
        """Return mock products for demo/fallback."""
        return {
            "products": [
                {
                    "name": "Premium Homepage Banner",
                    "id": "homepage_premium",
                    "formats": ["display_728x90", "display_970x250"],
                    "pricing": "CPM $25-35",
                },
                {
                    "name": "Sports Section Video",
                    "id": "sports_video",
                    "formats": ["video_16x9"],
                    "pricing": "CPM $45-60",
                },
                {
                    "name": "Mobile App Banner",
                    "id": "mobile_banner",
                    "formats": ["display_320x50", "display_300x250"],
                    "pricing": "CPM $8-12",
                },
            ],
            "total": 3,
            "message": "Found 3 advertising products (mock data)",
        }


def main():
    """Run the A2A server using python-a2a's standard server."""
    port = int(os.getenv("A2A_PORT", "8091"))
    host = os.getenv("A2A_HOST", "0.0.0.0")

    logger.info(f"Starting AdCP A2A Agent on {host}:{port}")
    logger.info("Using standard python-a2a server with create_flask_app()")

    # Create agent
    agent = AdCPSalesAgent()

    # Use python-a2a's standard Flask app creation
    # This automatically provides all A2A spec endpoints including /.well-known/agent.json
    from python_a2a.server.http import create_flask_app

    app = create_flask_app(agent)

    # Configure Flask to be aware it's mounted at /a2a in production
    if os.getenv("FLY_APP_NAME") or os.getenv("PRODUCTION") == "true":
        app.config["APPLICATION_ROOT"] = "/a2a"
        # This helps with URL generation in templates and redirects
        logger.info("Configured APPLICATION_ROOT=/a2a for production deployment")

    # Our custom routes are added via agent.setup_routes() which is called by create_flask_app

    # Use waitress production server instead of Flask dev server
    # This avoids the WERKZEUG_SERVER_FD issue in Docker
    from waitress import serve

    logger.info(f"Running with Waitress WSGI server on {host}:{port}")
    logger.info("Standard A2A endpoints: /.well-known/agent.json, /a2a, /agent.json, /stream")
    serve(app, host=host, port=port, threads=4)


if __name__ == "__main__":
    main()
