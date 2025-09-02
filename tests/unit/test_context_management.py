"""Tests for the new automatic context management system."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastmcp.server import Context as FastMCPContext
from pydantic import BaseModel

from src.core.mcp_context_wrapper import MCPContextWrapper
from src.core.tool_context import ToolContext


class TestRequest(BaseModel):
    """Test request model."""

    query: str


class TestResponse(BaseModel):
    """Test response model."""

    result: str
    message: str | None = None


@pytest.fixture
def mock_fastmcp_context():
    """Create a simplified mock FastMCP context."""
    context = MagicMock(spec=FastMCPContext)

    # Headers for both meta access and HTTP request access
    headers = {
        "x-adcp-auth": "test_token_123",
        "x-context-id": "ctx_test123",
        "X-Test-Session-ID": "test_session_123",
        "X-Force-Error": "none",
    }

    # Mock for meta access (used by MCP context wrapper)
    context.meta = {"headers": headers}

    # Mock for HTTP request access (used by testing hooks)
    mock_request = MagicMock()
    mock_request.headers = headers
    context.get_http_request.return_value = mock_request

    return context


@pytest.fixture
def mock_tenant():
    """Mock tenant data."""
    return {"tenant_id": "tenant_test", "name": "Test Tenant"}


@pytest.fixture
def mock_principal():
    """Mock principal data."""
    return {"principal_id": "principal_test", "name": "Test Principal", "platform_mappings": {}}


class TestToolContext:
    """Test the ToolContext class."""

    def test_tool_context_creation(self):
        """Test creating a ToolContext."""
        context = ToolContext(
            context_id="ctx_123",
            tenant_id="tenant_123",
            principal_id="principal_123",
            tool_name="test_tool",
            request_timestamp=datetime.now(UTC),
            conversation_history=[],
            metadata={"test": "data"},
        )

        assert context.context_id == "ctx_123"
        assert context.tenant_id == "tenant_123"
        assert context.principal_id == "principal_123"
        assert context.tool_name == "test_tool"
        assert context.metadata["test"] == "data"

    def test_is_async_operation(self):
        """Test checking if operation is async."""
        # Sync context (no workflow)
        sync_context = ToolContext(
            context_id="ctx_123",
            tenant_id="tenant_123",
            principal_id="principal_123",
            tool_name="test_tool",
            request_timestamp=datetime.now(UTC),
        )
        assert not sync_context.is_async_operation()

        # Async context (with workflow)
        async_context = ToolContext(
            context_id="ctx_123",
            tenant_id="tenant_123",
            principal_id="principal_123",
            tool_name="test_tool",
            request_timestamp=datetime.now(UTC),
            workflow_id="wf_123",
        )
        assert async_context.is_async_operation()

    def test_add_to_history(self):
        """Test adding messages to conversation history."""
        context = ToolContext(
            context_id="ctx_123",
            tenant_id="tenant_123",
            principal_id="principal_123",
            tool_name="test_tool",
            request_timestamp=datetime.now(UTC),
        )

        # Add a message
        context.add_to_history({"type": "request", "content": "test message"})

        assert len(context.conversation_history) == 1
        assert context.conversation_history[0]["type"] == "request"
        assert context.conversation_history[0]["content"] == "test message"
        assert "timestamp" in context.conversation_history[0]


class TestMCPContextWrapper:
    """Test the MCP context wrapper."""

    @patch("src.core.mcp_context_wrapper.get_principal_from_context")
    @patch("src.core.mcp_context_wrapper.get_current_tenant")
    @patch("src.core.mcp_context_wrapper.get_context_manager")
    def test_sync_tool_wrapping(
        self,
        mock_get_context_manager,
        mock_get_tenant,
        mock_get_principal,
        mock_fastmcp_context,
        mock_tenant,
        mock_principal,
    ):
        """Test wrapping a synchronous tool."""
        # Setup mocks
        mock_get_principal.return_value = "principal_test"
        mock_get_tenant.return_value = mock_tenant
        mock_context_manager = MagicMock()
        mock_get_context_manager.return_value = mock_context_manager

        # Create wrapper
        wrapper = MCPContextWrapper()

        # Define a test tool
        def test_tool(req: TestRequest, context: ToolContext) -> TestResponse:
            """Test tool function."""
            assert isinstance(context, ToolContext)
            assert context.principal_id == "principal_test"
            assert context.tenant_id == "tenant_test"
            return TestResponse(result=f"Processed: {req.query}")

        # Wrap the tool
        wrapped_tool = wrapper.wrap_tool(test_tool)

        # Call the wrapped tool
        request = TestRequest(query="test query")
        result = wrapped_tool(request, context=mock_fastmcp_context)

        assert isinstance(result, TestResponse)
        assert result.result == "Processed: test query"

    @patch("src.core.mcp_context_wrapper.get_principal_from_context")
    @patch("src.core.mcp_context_wrapper.get_current_tenant")
    @patch("src.core.mcp_context_wrapper.get_context_manager")
    async def test_async_tool_wrapping(
        self,
        mock_get_context_manager,
        mock_get_tenant,
        mock_get_principal,
        mock_fastmcp_context,
        mock_tenant,
        mock_principal,
    ):
        """Test wrapping an asynchronous tool."""
        # Setup mocks
        mock_get_principal.return_value = "principal_test"
        mock_get_tenant.return_value = mock_tenant
        mock_context_manager = MagicMock()
        mock_get_context_manager.return_value = mock_context_manager

        # Create wrapper
        wrapper = MCPContextWrapper()

        # Define an async test tool
        async def async_test_tool(req: TestRequest, context: ToolContext) -> TestResponse:
            """Async test tool function."""
            assert isinstance(context, ToolContext)
            assert context.principal_id == "principal_test"
            assert context.tenant_id == "tenant_test"
            assert context.context_id == "ctx_test123"  # From mock headers
            return TestResponse(result=f"Async processed: {req.query}")

        # Wrap the tool
        wrapped_tool = wrapper.wrap_tool(async_test_tool)

        # Call the wrapped tool
        request = TestRequest(query="async test query")
        result = await wrapped_tool(request, context=mock_fastmcp_context)

        assert isinstance(result, TestResponse)
        assert result.result == "Async processed: async test query"

    @patch("src.core.mcp_context_wrapper.get_principal_from_context")
    @patch("src.core.mcp_context_wrapper.get_current_tenant")
    @patch("src.core.mcp_context_wrapper.get_context_manager")
    def test_context_extraction(
        self, mock_get_context_manager, mock_get_tenant, mock_get_principal, mock_fastmcp_context, mock_tenant
    ):
        """Test extracting context from FastMCP context."""
        # Setup mocks
        mock_get_principal.return_value = "principal_test"
        mock_get_tenant.return_value = mock_tenant
        mock_context_manager = MagicMock()
        mock_get_context_manager.return_value = mock_context_manager

        # Create wrapper
        wrapper = MCPContextWrapper()

        # Test extraction from kwargs
        context = wrapper._extract_fastmcp_context((), {"context": mock_fastmcp_context})
        assert context == mock_fastmcp_context

        # Test extraction from args
        context = wrapper._extract_fastmcp_context((mock_fastmcp_context,), {})
        assert context == mock_fastmcp_context

        # Test no context found
        context = wrapper._extract_fastmcp_context((), {})
        assert context is None

    @patch("src.core.mcp_context_wrapper.get_principal_from_context")
    @patch("src.core.mcp_context_wrapper.get_current_tenant")
    @patch("src.core.mcp_context_wrapper.get_context_manager")
    def test_tool_context_creation(
        self, mock_get_context_manager, mock_get_tenant, mock_get_principal, mock_fastmcp_context, mock_tenant
    ):
        """Test creating ToolContext from FastMCP context."""
        # Setup mocks
        mock_get_principal.return_value = "principal_test"
        mock_get_tenant.return_value = mock_tenant
        mock_context_manager = MagicMock()
        mock_context_manager.get_or_create_context.return_value = None
        mock_get_context_manager.return_value = mock_context_manager

        # Create wrapper
        wrapper = MCPContextWrapper()

        # Create ToolContext
        tool_context = wrapper._create_tool_context(mock_fastmcp_context, "test_tool")

        assert isinstance(tool_context, ToolContext)
        assert tool_context.context_id == "ctx_test123"
        assert tool_context.tenant_id == "tenant_test"
        assert tool_context.principal_id == "principal_test"
        assert tool_context.tool_name == "test_tool"
        assert tool_context.metadata["headers"]["x-context-id"] == "ctx_test123"


class TestContextInjection:
    """Test context_id injection at protocol layer."""

    @patch("src.core.mcp_context_wrapper.get_principal_from_context")
    @patch("src.core.mcp_context_wrapper.get_current_tenant")
    @patch("src.core.mcp_context_wrapper.get_context_manager")
    def test_response_enhancement(
        self, mock_get_context_manager, mock_get_tenant, mock_get_principal, mock_fastmcp_context, mock_tenant
    ):
        """Test that context_id is stored for protocol layer."""
        # Setup mocks
        mock_get_principal.return_value = "principal_test"
        mock_get_tenant.return_value = mock_tenant
        mock_context_manager = MagicMock()
        mock_get_context_manager.return_value = mock_context_manager

        # Create wrapper
        wrapper = MCPContextWrapper()

        # Define a tool that returns a response
        def test_tool(req: TestRequest, context: ToolContext) -> TestResponse:
            return TestResponse(result="test")

        # Wrap the tool
        wrapped_tool = wrapper.wrap_tool(test_tool)

        # Call the wrapped tool
        request = TestRequest(query="test")
        result = wrapped_tool(request, context=mock_fastmcp_context)

        # Check that context_id is stored for protocol layer
        assert hasattr(result, "_mcp_context_id")
        assert result._mcp_context_id == "ctx_test123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
