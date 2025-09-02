"""Enhanced MCP server with automatic context management.

This module extends FastMCP to automatically handle context at the protocol layer,
similar to how A2A handles conversation context.
"""

from collections.abc import Callable
from typing import Any

from fastmcp.server import Server
from fastmcp.server.server import Context as FastMCPContext
from pydantic import BaseModel

from src.core.mcp_context_wrapper import MCPContextWrapper


class EnhancedMCPServer(Server):
    """Extended FastMCP server with automatic context management.

    This server automatically:
    1. Extracts/generates context_id from requests
    2. Creates ToolContext for tools
    3. Injects context_id into responses at protocol layer
    """

    def __init__(self, name: str, **kwargs):
        """Initialize the enhanced MCP server.

        Args:
            name: Server name
            **kwargs: Additional FastMCP server arguments
        """
        super().__init__(name, **kwargs)
        self.context_wrapper = MCPContextWrapper()
        self._original_tool_decorator = super().tool

    def tool(self, func: Callable | None = None, **kwargs) -> Callable:
        """Enhanced tool decorator that adds context management.

        This decorator wraps the standard FastMCP tool decorator to add
        automatic context management.
        """

        def decorator(f: Callable) -> Callable:
            # First wrap with context management
            wrapped = self.context_wrapper.wrap_tool(f)
            # Then apply the FastMCP tool decorator
            return self._original_tool_decorator(wrapped, **kwargs)

        if func is None:
            return decorator
        else:
            return decorator(func)

    async def _handle_tool_call(self, tool_name: str, arguments: dict, context: FastMCPContext) -> Any:
        """Override to inject context_id into responses.

        This method is called by FastMCP when processing tool calls.
        We override it to extract context_id and inject it into the response.
        """
        # Call the original handler
        result = await super()._handle_tool_call(tool_name, arguments, context)

        # Extract context_id from request headers
        headers = context.meta.get("headers", {}) if hasattr(context, "meta") else {}
        context_id = headers.get("x-context-id")

        # If no context_id in request, check if the result has one stored
        if not context_id and hasattr(result, "_mcp_context_id"):
            context_id = result._mcp_context_id

        # Inject context_id at protocol layer
        if context_id and isinstance(result, BaseModel):
            # For BaseModel responses, we need to handle this at serialization
            # Store context_id as metadata that the transport can use
            if not hasattr(result, "__mcp_metadata__"):
                result.__mcp_metadata__ = {}
            result.__mcp_metadata__["context_id"] = context_id

        return result

    def _serialize_response(self, result: Any) -> dict:
        """Serialize response and inject context_id.

        This method serializes the response and adds context_id at the
        protocol layer, not in the response object itself.
        """
        # Serialize the result
        if isinstance(result, BaseModel):
            response_data = result.model_dump()
        elif isinstance(result, dict):
            response_data = result
        else:
            response_data = {"value": str(result)}

        # Check for stored context_id
        context_id = None
        if hasattr(result, "__mcp_metadata__"):
            context_id = result.__mcp_metadata__.get("context_id")
        elif hasattr(result, "_mcp_context_id"):
            context_id = result._mcp_context_id

        # Add context_id at protocol layer (wrapper level)
        if context_id:
            # This is where MCP/A2A protocols would add their wrapper
            # For now, we'll add it as a protocol field
            response_data["_context_id"] = context_id

        return response_data


def create_enhanced_mcp_server(name: str = "adcp-server", **kwargs) -> EnhancedMCPServer:
    """Create an enhanced MCP server with automatic context management.

    Args:
        name: Server name
        **kwargs: Additional server configuration

    Returns:
        EnhancedMCPServer instance
    """
    return EnhancedMCPServer(name, **kwargs)
