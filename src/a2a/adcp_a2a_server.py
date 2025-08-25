#!/usr/bin/env python3
"""
AdCP Sales Agent A2A Server using python-a2a library.
This is a standard implementation using python-a2a's base classes.
No custom protocol code - just business logic.
"""

import logging
import os
import sys
from typing import Any

from python_a2a.models import AgentCard, AgentSkill, Task, TaskState, TaskStatus

# Standard python-a2a imports
from python_a2a.server import A2AServer

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import MCP client for AdCP integration
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

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
        agent_card = AgentCard(
            name=self.name,
            description=self.description,
            url="http://localhost:8091",
            version=self.version,
            skills=[
                AgentSkill(name="get_products", description="Browse available advertising products and inventory"),
                AgentSkill(name="create_campaign", description="Create and manage advertising campaigns"),
                AgentSkill(name="get_targeting", description="Get available targeting options"),
                AgentSkill(name="get_pricing", description="Get pricing information and models"),
            ],
        )

        # Initialize parent with agent card
        super().__init__(agent_card=agent_card)

        # MCP server configuration
        self.mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp/")
        self.mcp_token = os.getenv("MCP_AUTH_TOKEN", "test_principal_token")
        logger.info(f"AdCP A2A Agent initialized - MCP Server: {self.mcp_url}")

    async def get_products(self, query: str = "") -> dict[str, Any]:
        """Get available advertising products."""
        try:
            # Create MCP client
            headers = {"x-adcp-auth": self.mcp_token}
            transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

            async with Client(transport=transport) as client:
                # Call get_products tool
                result = await client.tools.get_products(brief=query if query else None)

                if result and hasattr(result, "products"):
                    products = result.products
                    if not products:
                        return {"message": "No products are currently available."}

                    product_list = []
                    for product in products[:10]:  # Limit to first 10
                        product_info = {
                            "name": product.name,
                            "id": product.product_id,
                            "formats": product.supported_formats,
                        }
                        if hasattr(product, "price_model"):
                            product_info["pricing"] = product.price_model
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
            headers = {"x-adcp-auth": self.mcp_token}
            transport = StreamableHttpTransport(url=self.mcp_url, headers=headers)

            async with Client(transport=transport) as client:
                result = await client.tools.create_media_buy(
                    product_ids=product_ids, total_budget=budget, flight_start_date=start_date, flight_end_date=end_date
                )

                if result:
                    return {
                        "success": True,
                        "media_buy_id": result.media_buy_id if hasattr(result, "media_buy_id") else "mock_id",
                        "message": "Campaign created successfully",
                    }

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
                text = content.get("text", "")
            else:
                text = str(content)

            logger.info(f"Processing task: {text[:100]}...")

            # Route based on keywords (simple routing for demo)
            text_lower = text.lower()

            if any(word in text_lower for word in ["product", "inventory", "available", "catalog"]):
                # Handle product queries
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.get_products(text))

                # Format response
                if "products" in result:
                    response_text = f"Found {result['total']} products:\n\n"
                    for p in result["products"][:5]:
                        response_text += f"• {p['name']} (ID: {p['id']})\n"
                        response_text += f"  Formats: {', '.join(p['formats'])}\n"
                        if "pricing" in p:
                            response_text += f"  Pricing: {p['pricing']}\n"
                        response_text += "\n"
                else:
                    response_text = result.get("message", "No products available")

            elif any(word in text_lower for word in ["target", "audience"]):
                result = self.get_targeting()
                response_text = "Available targeting options:\n\n"
                for category, options in result["targeting_options"].items():
                    response_text += f"**{category.title()}:**\n"
                    response_text += f"• {', '.join(options)}\n\n"

            elif any(word in text_lower for word in ["price", "pricing", "cost", "cpm", "budget"]):
                result = self.get_pricing()
                response_text = "Pricing information:\n\n"
                response_text += f"Minimum budget: {result['minimum_budget']}\n\n"
                for model, tiers in result["pricing_models"].items():
                    response_text += f"**{model}:**\n"
                    if isinstance(tiers, dict):
                        for tier, price in tiers.items():
                            response_text += f"• {tier}: {price}\n"
                    response_text += "\n"
                response_text += f"\n{result['volume_discounts']}"

            elif any(word in text_lower for word in ["create", "campaign", "buy"]):
                response_text = "To create a campaign, please provide:\n"
                response_text += "• Product IDs (from product catalog)\n"
                response_text += "• Total budget\n"
                response_text += "• Start and end dates\n\n"
                response_text += "Example: Create campaign with product_id=sports_video, budget=$5000, dates=2025-02-01 to 2025-02-28"

            else:
                response_text = "I can help you with:\n"
                response_text += "• Browse available products and inventory\n"
                response_text += "• View targeting options\n"
                response_text += "• Check pricing information\n"
                response_text += "• Create advertising campaigns\n\n"
                response_text += "What would you like to know?"

            # Create response artifacts
            task.artifacts = [{"parts": [{"type": "text", "text": response_text}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)

        except Exception as e:
            logger.error(f"Error handling task: {e}")
            task.artifacts = [{"parts": [{"type": "text", "text": f"I encountered an error: {str(e)}"}]}]
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
    logger.info("Using standard python-a2a server - no custom protocol code")

    # Create agent
    agent = AdCPSalesAgent()

    # Create Flask app and setup routes
    from flask import Flask

    app = Flask(__name__)
    agent.setup_routes(app)

    # Use waitress production server instead of Flask dev server
    # This avoids the WERKZEUG_SERVER_FD issue in Docker
    from waitress import serve

    logger.info(f"Running with Waitress WSGI server on {host}:{port}")
    serve(app, host=host, port=port, threads=4)


if __name__ == "__main__":
    main()
