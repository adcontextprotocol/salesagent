"""Unit tests for signals agent registry."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.signals_agent_registry import SignalsAgentRegistry


class TestSignalsAgentRegistry:
    """Unit tests for SignalsAgentRegistry class."""

    @pytest.mark.asyncio
    async def test_test_connection_passes_auth_header(self):
        """Test that test_connection passes auth_header to the MCP client."""
        registry = SignalsAgentRegistry()

        # Setup test data
        agent_url = "https://test-signals-agent.example.com/mcp"
        auth = {
            "type": "bearer",
            "credentials": "test-token-123",
        }
        auth_header = "Authorization"

        # Mock the MCP client creation
        with patch("src.core.signals_agent_registry.create_mcp_client") as mock_create_client:
            # Create mock result object
            mock_result = Mock()
            mock_result.structured_content = {"signals": []}
            mock_result.content = []

            mock_client = AsyncMock()
            mock_create_client.return_value.__aenter__.return_value = mock_client
            mock_create_client.return_value.__aexit__.return_value = None
            mock_client.call_tool = AsyncMock(return_value=mock_result)

            # Call test_connection with auth_header
            result = await registry.test_connection(agent_url, auth=auth, auth_header=auth_header)

            # Verify the MCP client was created with auth_header
            mock_create_client.assert_called_once()
            call_kwargs = mock_create_client.call_args[1]

            assert call_kwargs["agent_url"] == agent_url
            assert call_kwargs["auth"] == auth
            assert call_kwargs["auth_header"] == auth_header
            assert call_kwargs["timeout"] == 30

            # Verify successful connection
            assert result["success"] is True
            assert "message" in result

    @pytest.mark.asyncio
    async def test_test_connection_without_auth_header(self):
        """Test that test_connection works without auth_header (uses default)."""
        registry = SignalsAgentRegistry()

        # Setup test data
        agent_url = "https://test-signals-agent.example.com/mcp"
        auth = {
            "type": "bearer",
            "credentials": "test-token-456",
        }

        # Mock the MCP client creation
        with patch("src.core.signals_agent_registry.create_mcp_client") as mock_create_client:
            # Create mock result object
            mock_result = Mock()
            mock_result.structured_content = {"signals": []}
            mock_result.content = []

            mock_client = AsyncMock()
            mock_create_client.return_value.__aenter__.return_value = mock_client
            mock_create_client.return_value.__aexit__.return_value = None
            mock_client.call_tool = AsyncMock(return_value=mock_result)

            # Call test_connection without auth_header
            result = await registry.test_connection(agent_url, auth=auth, auth_header=None)

            # Verify the MCP client was created with auth_header=None
            mock_create_client.assert_called_once()
            call_kwargs = mock_create_client.call_args[1]

            assert call_kwargs["agent_url"] == agent_url
            assert call_kwargs["auth"] == auth
            assert call_kwargs["auth_header"] is None

            # Verify successful connection
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_test_connection_handles_connection_error(self):
        """Test that test_connection handles connection errors gracefully."""
        registry = SignalsAgentRegistry()

        # Setup test data
        agent_url = "https://unreachable-agent.example.com/mcp"
        auth = {
            "type": "bearer",
            "credentials": "test-token-789",
        }
        auth_header = "X-Custom-Auth"

        # Mock the MCP client to raise an exception
        with patch("src.core.signals_agent_registry.create_mcp_client") as mock_create_client:
            mock_create_client.side_effect = Exception("Connection timeout")

            # Call test_connection
            result = await registry.test_connection(agent_url, auth=auth, auth_header=auth_header)

            # Verify error handling
            assert result["success"] is False
            assert "error" in result
            assert "Connection" in result["error"] or "timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_get_signals_from_agent_uses_auth_header(self):
        """Test that _get_signals_from_agent passes auth_header to MCP client."""
        registry = SignalsAgentRegistry()

        # Create test agent with auth_header
        from src.core.signals_agent_registry import SignalsAgent

        test_agent = SignalsAgent(
            agent_url="https://test-agent.example.com/mcp",
            name="Test Agent",
            enabled=True,
            auth={"type": "bearer", "credentials": "test-token-abc"},
            auth_header="X-Custom-Auth",
            timeout=30,
        )

        # Mock the MCP client creation
        with patch("src.core.signals_agent_registry.create_mcp_client") as mock_create_client:
            # Create mock result object
            mock_result = Mock()
            mock_result.structured_content = {"signals": []}
            mock_result.content = []

            mock_client = AsyncMock()
            mock_create_client.return_value.__aenter__.return_value = mock_client
            mock_create_client.return_value.__aexit__.return_value = None
            mock_client.call_tool = AsyncMock(return_value=mock_result)

            # Call _get_signals_from_agent
            signals = await registry._get_signals_from_agent(
                test_agent,
                brief="test query",
                tenant_id="test-tenant",
            )

            # Verify the MCP client was created with correct auth_header
            mock_create_client.assert_called_once()
            call_kwargs = mock_create_client.call_args[1]

            assert call_kwargs["agent_url"] == test_agent.agent_url
            assert call_kwargs["auth"] == test_agent.auth
            assert call_kwargs["auth_header"] == "X-Custom-Auth"
            assert call_kwargs["timeout"] == 30

            # Verify signals were returned
            assert isinstance(signals, list)
