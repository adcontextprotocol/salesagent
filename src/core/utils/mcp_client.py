"""Unified MCP client utility for consistent agent communication.

This module provides a single, standardized way to create MCP clients for
communicating with external agents (creative agents, signals agents, etc.).

Key features:
- Consistent URL handling (respects user's URL, no suffix appending)
- Standardized auth header building
- Built-in retry logic with exponential backoff
- Proper error handling and logging
- Testable in isolation

Usage:
    from src.core.utils.mcp_client import create_mcp_client

    async with create_mcp_client(
        agent_url="https://example.com/mcp",
        auth={"type": "bearer", "credentials": "token123"},
        timeout=30
    ) as client:
        result = await client.call_tool("tool_name", params)
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    """Raised when MCP client connection fails after all retries."""

    pass


class MCPCompatibilityError(Exception):
    """Raised when MCP SDK version compatibility issue detected."""

    pass


def _build_auth_headers(auth: dict[str, Any] | None, auth_header: str | None = None) -> dict[str, str]:
    """Build authentication headers from auth config.

    Args:
        auth: Auth configuration dict with 'type' and 'credentials' keys
        auth_header: Optional custom header name (defaults based on auth type)

    Returns:
        Dictionary of headers to include in request

    Examples:
        >>> _build_auth_headers({"type": "bearer", "credentials": "token123"})
        {"Authorization": "Bearer token123"}

        >>> _build_auth_headers({"type": "api_key", "credentials": "key123"})
        {"x-api-key": "key123"}

        >>> _build_auth_headers({"type": "bearer", "credentials": "token"}, "X-Custom-Auth")
        {"X-Custom-Auth": "Bearer token"}
    """
    headers: dict[str, str] = {}

    if not auth:
        return headers

    auth_type = auth.get("type")
    credentials = auth.get("credentials")

    if not auth_type or not credentials:
        return headers

    # Determine header name
    if auth_header:
        header_name = auth_header
    elif auth_type == "bearer":
        header_name = "Authorization"
    elif auth_type == "api_key":
        header_name = "x-api-key"
    else:
        # Generic auth type - use x-api-key as default
        header_name = "x-api-key"

    # Format header value
    if auth_type == "bearer":
        headers[header_name] = f"Bearer {credentials}"
    else:
        # For api_key and other types, use credentials as-is
        headers[header_name] = credentials

    return headers


@asynccontextmanager
async def create_mcp_client(
    agent_url: str,
    auth: dict[str, Any] | None = None,
    auth_header: str | None = None,
    timeout: int = 30,
    max_retries: int = 3,
):
    """Create MCP client with standardized connection handling.

    This is the ONLY place where MCP clients should be created. This ensures
    consistent URL handling, auth, retry logic, and error handling across
    all agent communications.

    Args:
        agent_url: URL of the MCP agent endpoint
                  Examples: "https://creative.adcontextprotocol.org/mcp"
                           "https://audience-agent.fly.dev/FastMCP/"
                  NOTE: Use the exact URL the user provided - no modifications!
        auth: Optional auth configuration dict
              Format: {"type": "bearer"|"api_key", "credentials": "token_value"}
        auth_header: Optional custom auth header name
                    (defaults: "Authorization" for bearer, "x-api-key" for api_key)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum connection retry attempts (default: 3)

    Yields:
        Connected MCP Client instance

    Raises:
        MCPConnectionError: If connection fails after all retries
        MCPCompatibilityError: If MCP SDK version incompatibility detected

    Example:
        async with create_mcp_client(
            agent_url="https://creative.adcontextprotocol.org/mcp",
            auth={"type": "bearer", "credentials": "token123"},
            timeout=30
        ) as client:
            result = await client.call_tool("list_creative_formats", {})
            formats = result.structured_content
    """
    # Strip trailing slashes only - preserve the actual path
    agent_url = agent_url.rstrip("/")

    # Build auth headers
    headers = _build_auth_headers(auth, auth_header)

    # Retry loop with exponential backoff
    retry_delay = 1.0  # seconds
    last_exception = None

    for attempt in range(max_retries):
        try:
            # Create transport and client
            transport = StreamableHttpTransport(url=agent_url, headers=headers)
            client = Client(transport=transport)

            # Use client's built-in context manager
            async with client:
                # Success! Yield the connected client
                logger.debug(f"MCP client connected to {agent_url} on attempt {attempt + 1}")
                yield client
                return

        except Exception as e:
            last_exception = e
            error_msg = str(e)

            # Check for known compatibility issues
            if "notifications/initialized" in error_msg:
                logger.warning(
                    f"MCP SDK compatibility issue with {agent_url}: "
                    f"Server doesn't support 'notifications/initialized' notification. "
                    f"This is a known issue between FastMCP SDK versions."
                )
                raise MCPCompatibilityError(
                    f"MCP SDK compatibility issue with {agent_url}: "
                    f"Server doesn't support notifications/initialized notification. "
                    f"The agent may need to upgrade their FastMCP version to match the client."
                ) from e

            # Log and retry
            logger.warning(
                f"MCP connection attempt {attempt + 1}/{max_retries} failed for {agent_url}: "
                f"{type(e).__name__}: {e}"
            )

            if attempt < max_retries - 1:
                # Exponential backoff
                await asyncio.sleep(retry_delay * (2**attempt))
            else:
                # Final attempt failed
                logger.error(
                    f"All {max_retries} connection attempts failed for {agent_url}. "
                    f"Last error: {type(e).__name__}: {e}"
                )
                raise MCPConnectionError(
                    f"Failed to connect to MCP agent at {agent_url} after {max_retries} attempts: "
                    f"{type(e).__name__}: {e}"
                ) from last_exception


async def check_mcp_agent_connection(
    agent_url: str, auth: dict[str, Any] | None = None, auth_header: str | None = None
) -> dict[str, Any]:
    """Check connection to an MCP agent.

    This is useful for Admin UI "Test Connection" buttons and diagnostics.

    Args:
        agent_url: URL of the MCP agent endpoint
        auth: Optional auth configuration
        auth_header: Optional custom auth header name

    Returns:
        Dict with success status, message, and optional tool count
        Format: {"success": bool, "message": str, "tool_count": int}
                or {"success": bool, "error": str}

    Example:
        result = await check_mcp_agent_connection(
            agent_url="https://creative.adcontextprotocol.org/mcp",
            auth={"type": "bearer", "credentials": "token123"}
        )
        if result["success"]:
            print(f"Connected! Found {result['tool_count']} tools")
        else:
            print(f"Failed: {result['error']}")
    """
    try:
        async with create_mcp_client(agent_url=agent_url, auth=auth, auth_header=auth_header, timeout=10) as client:
            # Try to list tools to verify full functionality
            tools = await client.list_tools()

            return {
                "success": True,
                "message": "Successfully connected to MCP agent",
                "tool_count": len(tools) if isinstance(tools, list) else 0,
            }

    except MCPCompatibilityError as e:
        logger.warning(f"MCP compatibility issue during connection test: {e}")
        return {
            "success": False,
            "error": f"MCP SDK compatibility issue: {str(e)}",
        }

    except MCPConnectionError as e:
        logger.error(f"MCP connection test failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Connection failed: {str(e)}",
        }

    except Exception as e:
        logger.error(f"Unexpected error during MCP connection test: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }
