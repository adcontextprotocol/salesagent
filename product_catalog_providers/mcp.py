"""MCP-based product catalog provider for upstream server integration."""

import asyncio
from typing import Any

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from src.core.schemas import Product

from .base import ProductCatalogProvider


class MCPProductCatalog(ProductCatalogProvider):
    """
    Product catalog provider that calls an upstream MCP server.

    This enables agent-to-agent communication where the sales agent
    can query another agent for available products based on a brief.

    Configuration:
        upstream_url: URL of the upstream MCP server
        upstream_token: Optional authentication token
        upstream_auth_header: Optional auth header name (default: "Authorization")
        tool_name: Name of the tool to call (default: "get_products")
        timeout: Request timeout in seconds (default: 30)
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.upstream_url = config.get("upstream_url", "http://localhost:9000/mcp/")
        self.upstream_token = config.get("upstream_token")
        self.upstream_auth_header = config.get("upstream_auth_header", "Authorization")
        self.tool_name = config.get("tool_name", "get_products")
        self.timeout = config.get("timeout", 30)
        self.client = None

    async def initialize(self) -> None:
        """Initialize the MCP client connection."""
        headers = {}
        if self.upstream_token:
            headers[self.upstream_auth_header] = self.upstream_token

        transport = StreamableHttpTransport(url=self.upstream_url, headers=headers)
        self.client = Client(transport=transport)
        await self.client.__aenter__()

    async def shutdown(self) -> None:
        """Clean up the MCP client connection."""
        if self.client:
            await self.client.__aexit__(None, None, None)

    async def get_products(
        self,
        brief: str,
        tenant_id: str,
        principal_id: str | None = None,
        context: dict[str, Any] | None = None,
        principal_data: dict[str, Any] | None = None,
    ) -> list[Product]:
        """
        Query upstream MCP server for products matching the brief.

        The upstream server should expose a tool that accepts:
        - brief: The advertising brief
        - tenant_id: The tenant making the request
        - principal_id: The advertiser ID
        - principal_data: Full principal object including ad server mappings
        - context: Optional context information

        And returns a list of products in the expected format.
        """
        if not self.client:
            await self.initialize()

        # Prepare the request for the upstream tool
        request_data = {
            "brief": brief,
            "tenant_id": tenant_id,
        }

        if principal_id:
            request_data["principal_id"] = principal_id

        if principal_data:
            request_data["principal_data"] = principal_data

        if context:
            request_data["context"] = context

        # Call the upstream tool
        try:
            result = await asyncio.wait_for(self.client.call_tool(self.tool_name, request_data), timeout=self.timeout)

            # Convert the result to Product objects
            products = []
            for product_data in result.get("products", []):
                products.append(Product(**product_data))

            return products

        except TimeoutError as err:
            raise Exception(f"Upstream MCP server timeout after {self.timeout} seconds") from err
        except Exception as e:
            raise Exception(f"Error calling upstream MCP server: {str(e)}") from e
