"""The seam a transport-boundary test substitutes at: the registry row.

There is no per-tool MCP wrapper left to patch. ``TOOLS`` is the one declaration all three
transports derive from, and ``main._tool_callable`` builds the registered MCP callable from
a row -- so a test that wants a stub implementation replaces the ROW, and gets it on every
transport at once. Patching ``src.core.tools.<mod>._<tool>_impl`` does nothing: the row
captured the function object at import, so the module attribute and the thing the transports
invoke are two different names for what used to be one.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastmcp.server.context import Context

# _TOOLS, not TOOLS: the public registry is a read-only MappingProxyType, and the proxy
# reads through to this dict -- so patching it substitutes the row everywhere TOOLS is
# consulted, without the public surface being mutable.
from src.core.tools.registry import _TOOLS as TOOLS


@contextmanager
def registry_row(tool_name: str, **fields: Any) -> Iterator[None]:
    """Run the block with ``tool_name``'s row fields (``impl``, ``dto``, ...) replaced."""
    with patch.dict(TOOLS, {tool_name: replace(TOOLS[tool_name], **fields)}):
        yield


def registry_impl(tool_name: str, impl: Any) -> Any:
    """Run the block with ``tool_name``'s implementation replaced by ``impl``."""
    return registry_row(tool_name, impl=impl)


def mcp_tool(tool_name: str) -> Any:
    """The generated MCP callable for ``tool_name``, built from the row as registered.

    Built on each call, so calling it inside a :func:`registry_impl` block yields a callable
    bound to the substituted row.
    """
    from src.core.main import _tool_callable

    return _tool_callable(tool_name, TOOLS[tool_name])


def capture_req_via_wrapper(
    *,
    tool_name: str,
    stub_response: Any,
    wrapper_kwargs: dict[str, Any],
) -> Any:
    """Run a tool's MCP boundary with a stub impl; return the request handed to that impl."""
    captured: dict[str, Any] = {}

    async def _impl(req: Any, identity: Any = None, **kwargs: Any) -> Any:
        captured["req"] = req
        return stub_response

    mock_ctx = MagicMock(spec=Context)
    mock_ctx.get_state = AsyncMock(return_value=None)
    with registry_impl(tool_name, _impl):
        asyncio.run(mcp_tool(tool_name)(**wrapper_kwargs, ctx=mock_ctx))
    return captured["req"]
