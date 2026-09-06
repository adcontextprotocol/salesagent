"""Tests for MCPAuthMiddleware — centralized identity resolution for MCP tools.

Core Invariant: Identity resolution happens exactly once per MCP request in the
middleware; tool functions read the pre-resolved identity from FastMCP context
state and never call resolve_identity_from_context() directly.

These tests verify:
1. MCPAuthMiddleware class exists and inherits from Middleware
2. on_call_tool resolves identity and stores it on context state
3. Auth-required tools reject invalid tokens before tool body runs
4. Discovery tools (auth-optional) get unauthenticated identity
5. context_id is extracted from headers and stored on state
6. Middleware is registered on the MCP server
7. MCP tool wrappers do NOT call resolve_identity_from_context() directly
"""

import ast
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.resolved_identity import ResolvedIdentity

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestMCPAuthMiddlewareExists:
    """Verify MCPAuthMiddleware class structure."""

    def test_module_exists(self):
        """src.core.mcp_auth_middleware module must exist."""
        mod = importlib.import_module("src.core.mcp_auth_middleware")
        assert hasattr(mod, "MCPAuthMiddleware"), "MCPAuthMiddleware class not found"

    def test_inherits_from_middleware(self):
        """MCPAuthMiddleware must inherit from fastmcp.server.middleware.Middleware."""
        from fastmcp.server.middleware import Middleware

        from src.core.mcp_auth_middleware import MCPAuthMiddleware

        assert issubclass(MCPAuthMiddleware, Middleware), (
            "MCPAuthMiddleware must inherit from fastmcp.server.middleware.Middleware"
        )

    def test_has_on_call_tool(self):
        """MCPAuthMiddleware must override on_call_tool."""
        from src.core.mcp_auth_middleware import MCPAuthMiddleware

        # Check it's overridden (not just inherited)
        assert "on_call_tool" in MCPAuthMiddleware.__dict__, "MCPAuthMiddleware must override on_call_tool"

    def test_auth_optional_tools_defined(self):
        """AUTH_OPTIONAL_TOOLS set must be defined with discovery tools."""
        from src.core.mcp_auth_middleware import AUTH_OPTIONAL_TOOLS

        expected_discovery = {
            "get_adcp_capabilities",
            "get_products",
            "list_creative_formats",
            "list_authorized_properties",
        }
        assert expected_discovery.issubset(AUTH_OPTIONAL_TOOLS), (
            f"AUTH_OPTIONAL_TOOLS missing discovery tools: {expected_discovery - AUTH_OPTIONAL_TOOLS}"
        )


class TestMCPAuthMiddlewareBehavior:
    """Verify middleware resolves identity and stores on context state."""

    @pytest.fixture
    def middleware(self):
        from src.core.mcp_auth_middleware import MCPAuthMiddleware

        return MCPAuthMiddleware()

    @pytest.fixture
    def mock_context(self):
        """Create a mock MiddlewareContext with fastmcp_context."""
        fastmcp_ctx = MagicMock()
        state_store = {}

        async def set_state(key, value, *, serializable=True):
            state_store[key] = value

        async def get_state(key):
            return state_store.get(key)

        fastmcp_ctx.set_state = set_state
        fastmcp_ctx.get_state = get_state
        fastmcp_ctx._state_store = state_store

        ctx = MagicMock()
        ctx.fastmcp_context = fastmcp_ctx
        return ctx

    @pytest.mark.asyncio
    async def test_auth_required_tool_stores_identity(self, middleware, mock_context):
        """Auth-required tool: middleware resolves identity and stores on state."""
        mock_context.message = MagicMock()
        mock_context.message.name = "create_media_buy"  # auth-required

        mock_identity = MagicMock(spec=ResolvedIdentity)
        call_next = AsyncMock(return_value=MagicMock())

        with patch(
            "src.core.mcp_auth_middleware.resolve_identity_from_context",
            return_value=mock_identity,
        ) as mock_resolve:
            await middleware.on_call_tool(mock_context, call_next)

            # Middleware called resolve with require_valid_token=True
            mock_resolve.assert_called_once()
            call_kwargs = mock_resolve.call_args
            assert call_kwargs[1].get("require_valid_token") is True or (
                len(call_kwargs[0]) >= 2 and call_kwargs[0][1] is True
            )

        # Identity stored on state
        assert mock_context.fastmcp_context._state_store.get("identity") is mock_identity
        # Tool was called
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_discovery_tool_stores_identity_without_requiring_auth(self, middleware, mock_context):
        """Discovery tool: middleware resolves identity with require_valid_token=False."""
        mock_context.message = MagicMock()
        mock_context.message.name = "get_products"  # discovery/auth-optional

        mock_identity = MagicMock(spec=ResolvedIdentity)
        call_next = AsyncMock(return_value=MagicMock())

        with patch(
            "src.core.mcp_auth_middleware.resolve_identity_from_context",
            return_value=mock_identity,
        ) as mock_resolve:
            await middleware.on_call_tool(mock_context, call_next)

            mock_resolve.assert_called_once()
            call_kwargs = mock_resolve.call_args
            # require_valid_token should be False for discovery tools
            assert call_kwargs[1].get("require_valid_token") is False

        assert mock_context.fastmcp_context._state_store.get("identity") is mock_identity

    @pytest.mark.asyncio
    async def test_auth_failure_rejects_before_tool_runs_with_wire_envelope(self, middleware, mock_context):
        """Auth-required tool with a rejected credential: wire envelope, before the tool body.

        Two obligations, and the second is why this asserts on the envelope
        rather than on the raised class. The middleware runs OUTSIDE the tool
        functions, so its raise never reaches the ``with_error_logging``
        decorator that translates every other MCP raise; left untranslated,
        FastMCP stringifies it into a bare ``ToolError("<message>")`` and the
        buyer gets no code, no recovery and no suggestion — while A2A and REST
        answer the same rejected credential with the full two-layer envelope.
        Asserting ``pytest.raises(AdCPAuthenticationError)`` passed either way,
        so it could not see that divergence.
        """
        from src.core.exceptions import AdCPAuthenticationError
        from src.core.tool_error_logging import AdCPToolError
        from tests.helpers import assert_envelope_shape

        mock_context.message = MagicMock()
        mock_context.message.name = "create_media_buy"

        call_next = AsyncMock()

        with patch(
            "src.core.mcp_auth_middleware.resolve_identity_from_context",
            side_effect=AdCPAuthenticationError(),
        ):
            with pytest.raises(AdCPToolError) as exc_info:
                await middleware.on_call_tool(mock_context, call_next)

        assert_envelope_shape(exc_info.value.envelope, "AUTH_INVALID", recovery="terminal")

        # Tool was NOT called
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_context_id_extracted_from_headers(self, middleware, mock_context):
        """x-context-id extracted from headers and stored on state."""
        mock_context.message = MagicMock()
        mock_context.message.name = "create_media_buy"

        mock_identity = MagicMock(spec=ResolvedIdentity)
        call_next = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "src.core.mcp_auth_middleware.resolve_identity_from_context",
                return_value=mock_identity,
            ),
            patch(
                "src.core.mcp_auth_middleware.get_http_headers",
                return_value={"x-context-id": "test-ctx-123", "x-adcp-auth": "token"},
            ),
        ):
            await middleware.on_call_tool(mock_context, call_next)

        assert mock_context.fastmcp_context._state_store.get("context_id") == "test-ctx-123"


class TestMCPServerMiddlewareRegistration:
    """Verify middleware is registered on the MCP server."""

    def test_mcp_server_has_middleware_registered(self):
        """main.py must call mcp.add_middleware(MCPAuthMiddleware())."""
        source = Path("src/core/main.py").read_text()
        assert "add_middleware" in source, "main.py must register middleware via add_middleware()"
        assert "MCPAuthMiddleware" in source, "main.py must use MCPAuthMiddleware"


class TestGetMediaBuysImplRefactored:
    """get_media_buys _impl must accept ResolvedIdentity, not raw ctx."""

    def test_get_media_buys_impl_accepts_identity_parameter(self):
        """_get_media_buys_impl must accept identity: ResolvedIdentity parameter.

        The legacy pattern passes ctx to _impl which resolves identity inside.
        After refactoring, _impl should receive pre-resolved identity like all other tools.
        """
        import inspect

        from src.core.tools.media_buy_list import _get_media_buys_impl

        sig = inspect.signature(_get_media_buys_impl)
        params = list(sig.parameters.keys())
        assert "identity" in params, (
            f"_get_media_buys_impl must accept 'identity' parameter. "
            f"Current params: {params}. Refactor to receive ResolvedIdentity instead of ctx."
        )


class TestToolsDoNotCallResolveIdentityDirectly:
    """No module under ``src/core/tools`` resolves identity for itself.

    Identity is resolved ONCE per request, at the transport boundary: the MCP middleware
    above, the A2A handler, or the REST auth dependency. A tool that reaches for ambient
    context instead is resolving a second time, and can resolve to a DIFFERENT caller than
    the one the boundary authenticated.

    Derived, not enumerated. This used to carry a hand-written table of fourteen tool names
    and the file each one's MCP wrapper lived in, and grade only the function whose name
    matched the tool. Those wrappers are gone -- every transport reaches an implementation
    through ``TOOLS`` -- so the table graded nothing while still failing whenever a file
    moved. Walking the package instead has no list to fall behind.
    """

    def test_no_tool_module_calls_resolve_identity_from_context(self):
        offenders = []
        for path in sorted((REPO_ROOT / "src" / "core" / "tools").rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "resolve_identity_from_context":
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
        assert offenders == [], (
            f"tool modules must not resolve identity themselves: {offenders}. "
            "The transport boundary resolves it once and hands it to invoke_tool()."
        )
