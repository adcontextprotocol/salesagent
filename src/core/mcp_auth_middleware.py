"""FastMCP middleware for centralized MCP identity resolution.

Resolves identity once per tool call and stores it on FastMCP context state.
Tool functions read the pre-resolved identity via ctx.get_state('identity')
instead of calling resolve_identity_from_context() directly.
"""

import logging

from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from src.core.exceptions import AdCPSalesAgentError
from src.core.tool_error_logging import _translate_to_tool_error
from src.core.transport_helpers import resolve_identity_from_context

logger = logging.getLogger(__name__)

# Discovery tools that work without authentication.
# All other tools require a valid auth token.
AUTH_OPTIONAL_TOOLS = frozenset(
    {
        "get_adcp_capabilities",
        "get_products",
        "list_accounts",
        "list_creative_formats",
    }
)


class MCPAuthMiddleware(Middleware):
    """Resolve identity before tool execution and store on context state.

    After this middleware runs, tools read identity via:
        identity = ctx.get_state('identity')
        context_id = ctx.get_state('context_id')  # may be None
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next,
    ) -> ToolResult:
        tool_name = context.message.name
        require_auth = tool_name not in AUTH_OPTIONAL_TOOLS

        try:
            identity = resolve_identity_from_context(
                context.fastmcp_context,
                require_valid_token=require_auth,
            )
        except AdCPSalesAgentError as exc:
            # This middleware runs OUTSIDE the tool functions, so its raise never
            # reaches the ``with_error_logging`` decorator that translates every
            # other MCP raise. Unhandled, FastMCP stringifies it into a bare
            # ``ToolError("<message>")`` and the buyer gets no code, no recovery
            # and no suggestion — while A2A and REST answer the same rejected
            # credential with the full two-layer envelope. Translate here through
            # the SAME boundary translator (never a hand-built envelope), exactly
            # as RequestCompatMiddleware does for its own out-of-tool raises.
            _translate_to_tool_error(exc)

        if context.fastmcp_context:
            await context.fastmcp_context.set_state("identity", identity, serializable=False)

            # Extract x-context-id from HTTP headers for tools that need it
            try:
                headers = get_http_headers(include_all=True) or {}
                ctx_id = headers.get("x-context-id")
                if ctx_id:
                    await context.fastmcp_context.set_state("context_id", ctx_id, serializable=False)
            except Exception:
                logger.debug("Could not set context_id state", exc_info=True)

        return await call_next(context)
