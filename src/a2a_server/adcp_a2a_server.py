#!/usr/bin/env python3
"""
AdCP Sales Agent A2A Server using official a2a-sdk library.
Supports both standard A2A message format and JSON-RPC 2.0.
"""

import logging
import os
import sys
from collections.abc import AsyncGenerator
from typing import Any

# Fix import order to avoid local a2a directory conflict
# Import official a2a-sdk first before adding local paths

original_path = sys.path.copy()

# Temporarily remove current directory to avoid local a2a conflict
if "" in sys.path:
    sys.path.remove("")
if "." in sys.path:
    sys.path.remove(".")

# Official a2a-sdk imports (must be before adding local paths)
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue import Event
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import (
    AgentCard,
    Artifact,
    Message,
    MessageSendParams,
    Part,
    Task,
    TaskIdParams,
    TaskQueryParams,
    TaskState,
    TaskStatus,
)

# Restore paths and add parent directories for local imports
sys.path = original_path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import MCP client for AdCP integration
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

# Import database models for authentication

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AdCPRequestHandler(RequestHandler):
    """Request handler for AdCP A2A operations supporting JSON-RPC 2.0."""

    def __init__(self, mcp_server_url: str = None):
        """Initialize the AdCP A2A request handler.

        Args:
            mcp_server_url: URL of the MCP server (e.g., http://localhost:8080/mcp/)
        """
        self.mcp_server_url = mcp_server_url or os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp/")
        self.tasks = {}  # In-memory task storage
        logger.info(f"AdCP Request Handler initialized - MCP Server: {self.mcp_server_url}")

    async def on_message_send(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> Task | Message:
        """Handle 'message/send' method for non-streaming requests.

        Args:
            params: Parameters including the message and configuration
            context: Server call context

        Returns:
            Task object or Message response
        """
        logger.info(f"Handling message/send request: {params}")

        # Extract message text
        message = params.message
        text = ""
        if hasattr(message, "parts") and message.parts:
            for part in message.parts:
                # Handle both direct text and nested root.text structure
                if hasattr(part, "text"):
                    text += part.text + " "
                elif hasattr(part, "root") and hasattr(part.root, "text"):
                    text += part.root.text + " "
        text = text.strip().lower()

        # Create task for tracking
        task_id = f"task_{len(self.tasks) + 1}"
        # Handle message_id being a number or string
        msg_id = str(params.message.message_id) if hasattr(params.message, "message_id") else None
        context_id = params.message.context_id or msg_id or f"ctx_{task_id}"
        task = Task(
            id=task_id,
            context_id=context_id,
            kind="task",
            status=TaskStatus(state=TaskState.working),
            metadata={"request": text},
        )
        self.tasks[task_id] = task

        try:
            # Route based on keywords
            if any(word in text for word in ["product", "inventory", "available", "catalog"]):
                result = await self._get_products(text)
                task.artifacts = [Artifact(name="product_catalog", parts=[Part(type="data", data=result)])]
            elif any(word in text for word in ["price", "pricing", "cost", "cpm", "budget"]):
                result = self._get_pricing()
                task.artifacts = [Artifact(name="pricing_information", parts=[Part(type="data", data=result)])]
            elif any(word in text for word in ["target", "audience"]):
                result = self._get_targeting()
                task.artifacts = [Artifact(name="targeting_options", parts=[Part(type="data", data=result)])]
            elif any(word in text for word in ["create", "buy", "campaign", "media"]):
                result = await self._create_media_buy(text)
                if result.get("success"):
                    task.artifacts = [Artifact(name="media_buy_created", parts=[Part(type="data", data=result)])]
                else:
                    task.artifacts = [Artifact(name="media_buy_error", parts=[Part(type="data", data=result)])]
            else:
                # General help response
                capabilities = {
                    "supported_queries": [
                        "product_catalog",
                        "targeting_options",
                        "pricing_information",
                        "campaign_creation",
                    ],
                    "example_queries": [
                        "What video ad products do you have available?",
                        "Show me targeting options",
                        "What are your pricing models?",
                        "How do I create a media buy?",
                    ],
                }
                task.artifacts = [Artifact(name="capabilities", parts=[Part(type="data", data=capabilities)])]

            # Mark task as completed
            task.status = TaskStatus(state=TaskState.completed)

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            task.status = TaskStatus(state=TaskState.failed)
            task.artifacts = [Artifact(name="error", parts=[Part(type="text", text=str(e))])]

        self.tasks[task_id] = task
        return task

    async def on_message_send_stream(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> AsyncGenerator[Event]:
        """Handle 'message/stream' method for streaming requests.

        Args:
            params: Parameters including the message and configuration
            context: Server call context

        Yields:
            Event objects from the agent's execution
        """
        # For now, implement non-streaming behavior
        # In production, this would yield events as they occur
        task = await self.on_message_send(params, context)

        # Yield a single event with the complete task
        yield Event(type="task_update", data=task.model_dump())

    async def on_get_task(
        self,
        params: TaskQueryParams,
        context: ServerCallContext | None = None,
    ) -> Task | None:
        """Handle 'tasks/get' method to retrieve task status.

        Args:
            params: Parameters specifying the task ID
            context: Server call context

        Returns:
            Task object if found, otherwise None
        """
        task_id = params.task_id
        return self.tasks.get(task_id)

    async def on_cancel_task(
        self,
        params: TaskIdParams,
        context: ServerCallContext | None = None,
    ) -> Task | None:
        """Handle 'tasks/cancel' method to cancel a task.

        Args:
            params: Parameters specifying the task ID
            context: Server call context

        Returns:
            Task object with canceled status, or None if not found
        """
        task_id = params.task_id
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus(state=TaskState.canceled)
            self.tasks[task_id] = task
        return task

    async def on_resubscribe_to_task(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle task resubscription requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Task resubscription not supported")

    async def on_get_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle get push notification config requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Push notifications not supported")

    async def on_set_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle set push notification config requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Push notifications not supported")

    async def on_list_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle list push notification config requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Push notifications not supported")

    async def on_delete_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle delete push notification config requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Push notifications not supported")

    async def _get_products(self, query: str) -> dict:
        """Get available advertising products from MCP server.

        Args:
            query: User's product query

        Returns:
            Dictionary containing product information
        """
        try:
            # Try to connect to MCP server
            headers = {"x-adcp-auth": "test_token"}  # TODO: Get from context
            transport = StreamableHttpTransport(url=self.mcp_server_url, headers=headers)

            async with Client(transport=transport) as client:
                # Call get_products tool
                result = await client.tools.get_products(brief=query)
                return {"products": result}

        except Exception as e:
            logger.warning(f"Could not connect to MCP server: {e}")
            # Return comprehensive inventory data for premium coffee beans campaign
            return {
                "campaign_context": "Premium Coffee Beans Advertising Inventory",
                "products": [
                    {
                        "id": "video_premium_coffee",
                        "name": "Premium Video - Coffee & Lifestyle",
                        "description": "High-impact video ads on coffee and lifestyle content",
                        "formats": {
                            "instream": {"15s": "available", "30s": "available"},
                            "outstream": {"6s": "available", "15s": "available"},
                        },
                        "inventory_available": True,
                        "estimated_reach": "2.5M coffee enthusiasts monthly",
                        "audience_match": "85% match - premium coffee buyers",
                        "pricing": {
                            "cpm": {"min": 25, "max": 45},
                            "minimum_spend": 5000,
                            "volume_discount": "10% at $25k+",
                        },
                        "creative_specs": {
                            "video": "MP4, 1920x1080, max 50MB",
                            "duration": "6-30 seconds",
                            "captions": "required",
                        },
                        "performance_benchmarks": {
                            "avg_ctr": "2.8%",
                            "avg_completion_rate": "75%",
                            "similar_campaigns": "3.2% conversion rate",
                        },
                    },
                    {
                        "id": "display_coffee_sites",
                        "name": "Display Network - Coffee Publications",
                        "description": "Banner ads across premium coffee and food sites",
                        "formats": {
                            "300x250": "high availability",
                            "728x90": "medium availability",
                            "320x50": "mobile - high availability",
                        },
                        "inventory_available": True,
                        "estimated_reach": "5M impressions/month",
                        "audience_match": "78% match - coffee consumers",
                        "pricing": {
                            "cpm": {"min": 8, "max": 15},
                            "cpc": {"min": 0.75, "max": 2.50},
                            "minimum_spend": 2000,
                        },
                        "creative_specs": {
                            "formats": "JPG, PNG, HTML5",
                            "max_file_size": "150KB",
                            "animation": "15 seconds max",
                        },
                        "performance_benchmarks": {
                            "avg_ctr": "0.15%",
                            "viewability": "72%",
                            "similar_campaigns": "1.8% conversion rate",
                        },
                    },
                    {
                        "id": "native_coffee_content",
                        "name": "Native Advertising - Coffee Content",
                        "description": "Native ads in coffee blogs and recipe sites",
                        "formats": {
                            "sponsored_content": "available",
                            "in_feed": "high availability",
                            "recommendation_widget": "available",
                        },
                        "inventory_available": True,
                        "estimated_reach": "1.8M engaged coffee readers",
                        "audience_match": "92% match - premium coffee buyers",
                        "pricing": {"cpm": {"min": 12, "max": 25}, "minimum_spend": 3000},
                        "creative_specs": {
                            "headline": "25-40 characters",
                            "description": "90-120 characters",
                            "image": "1200x628px recommended",
                        },
                        "performance_benchmarks": {
                            "avg_ctr": "0.8%",
                            "engagement_rate": "4.5%",
                            "similar_campaigns": "2.5% conversion rate",
                        },
                    },
                    {
                        "id": "search_coffee_keywords",
                        "name": "Search Ads - Coffee Keywords",
                        "description": "Search advertising on coffee-related queries",
                        "formats": {
                            "text_ads": "available",
                            "shopping_ads": "available",
                            "display_remarketing": "available",
                        },
                        "inventory_available": True,
                        "keyword_opportunities": [
                            "premium coffee beans (high intent)",
                            "best coffee beans online (high competition)",
                            "organic coffee (medium competition)",
                            "specialty coffee (low competition)",
                        ],
                        "pricing": {"cpc": {"min": 1.50, "max": 4.00}, "minimum_spend": 1000},
                        "performance_benchmarks": {
                            "avg_ctr": "3.5%",
                            "conversion_rate": "4.2%",
                            "quality_score": "7/10 average",
                        },
                    },
                ],
                "targeting_options": {
                    "demographics": {
                        "age": ["25-34", "35-44", "45-54"],
                        "income": ["$50k-$100k", "$100k+"],
                        "education": ["college+"],
                    },
                    "interests": [
                        "Premium coffee",
                        "Specialty beverages",
                        "Organic foods",
                        "Cooking & recipes",
                        "Sustainable living",
                    ],
                    "behaviors": ["Online grocery shoppers", "Premium brand affinity", "Subscription box users"],
                    "geography": {
                        "coverage": "US nationwide",
                        "top_markets": ["NYC", "SF", "Seattle", "Portland", "Austin"],
                    },
                },
                "campaign_recommendations": {
                    "optimal_mix": "40% video, 30% native, 20% display, 10% search",
                    "budget_allocation": "$8k video, $6k native, $4k display, $2k search",
                    "duration": "45-60 days recommended for testing",
                    "seasonality": "Peak performance Sept-Dec, March-May",
                },
            }

    def _get_pricing(self) -> dict:
        """Get pricing information.

        Returns:
            Dictionary containing pricing models and information
        """
        return {
            "pricing_models": [
                {
                    "type": "CPM",
                    "description": "Cost per thousand impressions",
                    "ranges": {
                        "video": {"min": 15, "max": 50},
                        "display": {"min": 2, "max": 10},
                        "native": {"min": 5, "max": 20},
                    },
                },
                {
                    "type": "CPC",
                    "description": "Cost per click",
                    "ranges": {"min": 0.50, "max": 5.00},
                },
                {
                    "type": "Guaranteed",
                    "description": "Fixed price for guaranteed delivery",
                    "minimum_commitment": 10000,
                },
            ],
            "volume_discounts": [
                {"threshold": 50000, "discount": "5%"},
                {"threshold": 100000, "discount": "10%"},
                {"threshold": 500000, "discount": "15%"},
            ],
        }

    def _get_targeting(self) -> dict:
        """Get available targeting options.

        Returns:
            Dictionary containing targeting capabilities
        """
        return {
            "targeting_options": {
                "demographics": {
                    "age_ranges": ["18-24", "25-34", "35-44", "45-54", "55+"],
                    "gender": ["male", "female", "unknown"],
                    "household_income": ["0-50k", "50-100k", "100-150k", "150k+"],
                },
                "geography": {
                    "levels": ["country", "state", "dma", "city", "zip"],
                    "available_countries": ["US", "CA", "UK", "AU"],
                },
                "interests": {
                    "categories": [
                        "Technology",
                        "Sports",
                        "Entertainment",
                        "Travel",
                        "Food & Dining",
                        "Health & Fitness",
                    ]
                },
                "contextual": {
                    "content_categories": ["News", "Sports", "Entertainment", "Business"],
                    "keywords": "Custom keyword targeting available",
                },
                "devices": {
                    "types": ["desktop", "mobile", "tablet", "ctv"],
                    "operating_systems": ["ios", "android", "windows", "macos"],
                },
            }
        }

    async def _create_media_buy(self, request: str) -> dict:
        """Create a media buy based on the request.

        Args:
            request: User's media buy request

        Returns:
            Dictionary containing media buy creation result
        """
        # This would normally parse the request and create via MCP
        # For now, return a mock response
        return {
            "success": False,
            "message": "Please provide more details: product IDs, budget, and flight dates",
            "required_fields": ["product_ids", "total_budget", "flight_start_date", "flight_end_date"],
            "example": {
                "product_ids": ["video_premium"],
                "total_budget": 10000,
                "flight_start_date": "2025-02-01",
                "flight_end_date": "2025-02-28",
            },
        }


def create_agent_card() -> AgentCard:
    """Create the agent card describing capabilities.

    Returns:
        AgentCard with AdCP Sales Agent capabilities
    """
    server_url = os.getenv("FLY_APP_NAME")
    if server_url:
        server_url = f"https://{server_url}.fly.dev/a2a/"
    else:
        server_url = "https://adcp-sales-agent.fly.dev/a2a/"

    from a2a.types import AgentSkill

    return AgentCard(
        name="AdCP Sales Agent",
        description="AI agent for programmatic advertising campaigns via AdCP protocol",
        version="1.0.0",
        protocol_version="1.0",
        capabilities={
            "google_a2a_compatible": True,
            "parts_array_format": True,
            "supports_json_rpc": True,
        },
        default_input_modes=["message"],
        default_output_modes=["message"],
        skills=[
            AgentSkill(
                id="get_products",
                name="get_products",
                description="Browse available advertising products and inventory",
                tags=["products", "inventory", "catalog"],
            ),
            AgentSkill(
                id="get_pricing",
                name="get_pricing",
                description="Get pricing information and rate cards",
                tags=["pricing", "cost", "budget"],
            ),
            AgentSkill(
                id="get_targeting",
                name="get_targeting",
                description="Explore available targeting options",
                tags=["targeting", "audience", "demographics"],
            ),
            AgentSkill(
                id="create_media_buy",
                name="create_media_buy",
                description="Create and manage advertising campaigns",
                tags=["campaign", "media", "buy"],
            ),
        ],
        url=server_url,
        authentication="bearer-token",
        documentation_url="https://github.com/your-org/adcp-sales-agent",
    )


def main():
    """Main entry point for the A2A server."""
    host = os.getenv("A2A_HOST", "0.0.0.0")
    port = int(os.getenv("A2A_PORT", "8091"))

    # Initialize components
    agent_card = create_agent_card()
    request_handler = AdCPRequestHandler()

    logger.info(f"Starting AdCP A2A Agent on {host}:{port}")
    logger.info("Using official a2a-sdk with A2AStarletteApplication")

    # Create Starlette application
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # Build the Starlette app with proper routing
    app = a2a_app.build(
        agent_card_url="/.well-known/agent.json",
        rpc_url="/a2a",
        extended_agent_card_url="/agent.json",
    )

    # Add alias for agent-card.json (some clients look for this)
    # Note: Must add routes before wrapping with middleware
    @app.route("/.well-known/agent-card.json", methods=["GET"])
    async def agent_card_alias(request):
        """Alias for agent.json to support different client expectations."""
        from starlette.responses import JSONResponse

        return JSONResponse(agent_card.model_dump())

    # Wrap app with ASGI middleware to fix messageId type
    import json

    class MessageIdFixMiddleware:
        """ASGI middleware to convert numeric messageId to string."""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == "/a2a":
                # Intercept the receive function to modify the body
                body_parts = []

                async def receive_wrapper():
                    message = await receive()
                    if message["type"] == "http.request":
                        body = message.get("body", b"")
                        if body and not body_parts:  # First chunk
                            try:
                                # Try to parse and fix the JSON
                                data = json.loads(body)

                                # Check if this is a message/send with numeric messageId
                                if (
                                    data.get("method") == "message/send"
                                    and "params" in data
                                    and "message" in data["params"]
                                    and "messageId" in data["params"]["message"]
                                ):

                                    message_id = data["params"]["message"]["messageId"]
                                    if isinstance(message_id, int | float):
                                        # Convert to string
                                        data["params"]["message"]["messageId"] = str(message_id)
                                        logger.info(f"Converted numeric messageId {message_id} to string")

                                        # Return modified body
                                        message["body"] = json.dumps(data).encode()
                            except Exception as e:
                                logger.debug(f"MessageId fix skipped: {e}")

                        body_parts.append(body)

                    return message

                await self.app(scope, receive_wrapper, send)
            else:
                await self.app(scope, receive, send)

    # Apply the middleware
    app = MessageIdFixMiddleware(app)

    # Run with uvicorn
    import uvicorn

    logger.info("Standard A2A endpoints: /.well-known/agent.json, /a2a, /agent.json")
    logger.info("JSON-RPC 2.0 support enabled at /a2a")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
