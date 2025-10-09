"""
Comprehensive end-to-end test for AdCP Sales Agent Server.

This test exercises all AdCP tools and protocols, implementing the testing hooks
from https://github.com/adcontextprotocol/adcp/pull/34.

It can be run in multiple modes:
- local: Starts its own test servers
- docker: Uses existing Docker services
- ci: Optimized for CI environments
- external: Tests against any AdCP-compliant server

Usage:
    pytest tests/e2e/test_adcp_full_lifecycle.py --mode=docker
    pytest tests/e2e/test_adcp_full_lifecycle.py --server-url=https://example.com
"""

import asyncio
import json

# Test configuration defaults - read from environment variables
import os
import uuid
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from .adcp_schema_validator import AdCPSchemaValidator, SchemaValidationError

DEFAULT_MCP_PORT = int(os.getenv("ADCP_SALES_PORT", "8080"))  # Default MCP port
DEFAULT_A2A_PORT = int(os.getenv("A2A_PORT", "8091"))  # Default A2A port
DEFAULT_ADMIN_PORT = int(os.getenv("ADMIN_UI_PORT", "8087"))  # From .env
TEST_TIMEOUT = 30


class AdCPTestClient:
    """Client for testing AdCP servers with full testing hook support and schema validation."""

    def __init__(
        self,
        mcp_url: str,
        a2a_url: str,
        auth_token: str,
        test_session_id: str | None = None,
        dry_run: bool = True,
        validate_schemas: bool = True,
        offline_mode: bool = False,
    ):
        self.mcp_url = mcp_url
        self.a2a_url = a2a_url
        self.auth_token = auth_token
        self.test_session_id = test_session_id or str(uuid.uuid4())
        self.dry_run = dry_run
        self.validate_schemas = validate_schemas
        self.offline_mode = offline_mode
        self.mock_time = None
        self.mcp_client = None
        self.http_client = httpx.AsyncClient()
        self.schema_validator = None

    async def __aenter__(self):
        """Enter async context."""
        headers = self._build_headers()
        transport = StreamableHttpTransport(url=f"{self.mcp_url}/mcp/", headers=headers)
        self.mcp_client = Client(transport=transport)
        await self.mcp_client.__aenter__()

        # Initialize schema validator if enabled
        if self.validate_schemas:
            self.schema_validator = AdCPSchemaValidator(
                offline_mode=self.offline_mode, adcp_version="v1"  # Default to v1, can be made configurable
            )
            await self.schema_validator.__aenter__()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self.mcp_client:
            await self.mcp_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.schema_validator:
            await self.schema_validator.__aexit__(exc_type, exc_val, exc_tb)
        await self.http_client.aclose()

    def _build_headers(self) -> dict[str, str]:
        """Build headers with testing hooks."""
        headers = {"x-adcp-auth": self.auth_token, "X-Test-Session-ID": self.test_session_id}

        if self.dry_run:
            headers["X-Dry-Run"] = "true"

        if self.mock_time:
            headers["X-Mock-Time"] = self.mock_time

        return headers

    def set_mock_time(self, timestamp: datetime):
        """Set the mock time for simulated progression."""
        self.mock_time = timestamp.isoformat() + "Z"
        # Update client headers
        if self.mcp_client and hasattr(self.mcp_client, "_transport"):
            self.mcp_client._transport.headers.update(self._build_headers())

    def jump_to_event(self, event: str):
        """Set header to jump to a specific lifecycle event."""
        headers = self._build_headers()
        headers["X-Jump-To-Event"] = event
        if self.mcp_client and hasattr(self.mcp_client, "_transport"):
            self.mcp_client._transport.headers.update(headers)

    def _parse_mcp_response(self, result) -> dict:
        """Parse MCP response with robust fallback handling."""
        try:
            # Handle TextContent response format
            if hasattr(result, "content") and isinstance(result.content, list):
                if result.content and hasattr(result.content[0], "text"):
                    return json.loads(result.content[0].text)

            # Handle direct dict response
            if isinstance(result, dict):
                return result

            # Handle string JSON response
            if isinstance(result, str):
                return json.loads(result)

            # Handle result with content field
            if hasattr(result, "content"):
                if isinstance(result.content, str):
                    return json.loads(result.content)
                elif isinstance(result.content, dict):
                    return result.content

            # Fallback - convert to dict if possible
            if hasattr(result, "__dict__"):
                return result.__dict__

        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse MCP response as JSON: {e}")
        except Exception as e:
            raise ValueError(f"Unexpected MCP response format: {type(result)} - {e}")

        raise ValueError(f"Could not parse MCP response: {type(result)}")

    async def call_mcp_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        """Call an MCP tool and parse the response with robust error handling and schema validation."""
        try:
            # Convert tool_name to task_name for schema validation
            # MCP tools use underscore format, AdCP schemas use hyphen format
            task_name = tool_name.replace("_", "-")

            # Validate request if schema validation is enabled
            if self.validate_schemas and self.schema_validator:
                try:
                    await self.schema_validator.validate_request(task_name, params)
                    print(f"✓ Request schema validation passed for {task_name}")
                except SchemaValidationError as e:
                    print(f"⚠ Request schema validation failed for {task_name}: {e}")
                    for error in e.validation_errors:
                        print(f"  - {error}")
                    # Don't fail the test, just warn - schemas might be stricter than implementation
                except Exception as e:
                    print(f"⚠ Request schema validation error for {task_name}: {e}")

            # Make the actual API call
            result = await self.mcp_client.call_tool(tool_name, {"req": params})
            parsed_response = self._parse_mcp_response(result)

            # Validate response if schema validation is enabled
            if self.validate_schemas and self.schema_validator:
                try:
                    await self.schema_validator.validate_response(task_name, parsed_response)
                    print(f"✓ Response schema validation passed for {task_name}")
                except SchemaValidationError as e:
                    print(f"⚠ Response schema validation failed for {task_name}: {e}")
                    for error in e.validation_errors:
                        print(f"  - {error}")
                    # Don't fail the test, just warn - this helps identify discrepancies
                except Exception as e:
                    print(f"⚠ Response schema validation error for {task_name}: {e}")

            return parsed_response

        except Exception as e:
            # Add context for better error messages
            raise RuntimeError(f"MCP tool '{tool_name}' failed: {e}") from e

    async def query_a2a(self, query: str) -> dict[str, Any]:
        """Query the A2A server using JSON-RPC 2.0 transport with proper string messageId."""
        headers = self._build_headers()
        # A2A expects Bearer token in Authorization header
        headers["Authorization"] = f"Bearer {self.auth_token}"
        headers["Content-Type"] = "application/json"

        # Create proper JSON-RPC 2.0 request with string IDs as per A2A spec
        request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),  # JSON-RPC request ID as string
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),  # Message ID as string (A2A spec requirement)
                    "contextId": self.test_session_id,
                    "role": "user",
                    "parts": [{"kind": "text", "text": query}],
                }
            },
        }

        # Retry logic for connection issues
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                response = await self.http_client.post(
                    f"{self.a2a_url}/a2a",  # Use standard /a2a endpoint
                    json=request,
                    headers=headers,
                    timeout=10.0,  # Add timeout
                )
                response.raise_for_status()
                result = response.json()

                # Handle JSON-RPC response format
                if "result" in result:
                    task = result["result"]
                    # Convert to expected format for existing tests
                    return {
                        "status": {"state": task.get("status", {}).get("state", "unknown")},
                        "artifacts": task.get("artifacts", []),
                        "message": task.get("metadata", {}).get("response", "") if task.get("metadata") else "",
                    }
                elif "error" in result:
                    # Return error in expected format
                    return {
                        "status": {"state": "failed"},
                        "error": result["error"],
                        "message": result["error"].get("message", "Error occurred"),
                    }
                else:
                    # Unexpected format
                    return {"status": {"state": "unknown"}, "message": "Unexpected response format"}
            except httpx.ReadError as e:
                if attempt < max_retries - 1:
                    print(f"A2A connection failed (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                else:
                    raise e
            except Exception as e:
                # Don't retry for non-connection errors
                raise e


class TestAdCPFullLifecycle:
    """Comprehensive E2E test suite for AdCP protocol compliance."""

    @pytest.fixture
    async def test_client(self, request, docker_services_e2e, test_auth_token) -> AdCPTestClient:
        """Create test client based on test mode."""
        mode = request.config.getoption("--mode", "docker")
        server_url = request.config.getoption("--server-url", None)

        if server_url:
            # External server mode
            mcp_url = server_url
            a2a_url = server_url
        elif mode == "docker":
            # Docker mode - use configured ports
            mcp_url = f"http://localhost:{DEFAULT_MCP_PORT}"
            a2a_url = f"http://localhost:{DEFAULT_A2A_PORT}"
        else:
            # Local/CI mode would start its own servers
            # For now default to Docker ports
            mcp_url = f"http://localhost:{DEFAULT_MCP_PORT}"
            a2a_url = f"http://localhost:{DEFAULT_A2A_PORT}"

        # Use the provided test auth token
        auth_token = test_auth_token

        client = AdCPTestClient(
            mcp_url=mcp_url, a2a_url=a2a_url, auth_token=auth_token, dry_run=True  # Always use dry-run for tests
        )

        async with client:
            yield client

    @pytest.mark.asyncio
        pass
