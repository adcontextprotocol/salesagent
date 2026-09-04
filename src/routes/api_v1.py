"""REST API v1 endpoints.

REST transport for AdCP tools, proving the 3-transport pattern
(MCP + A2A + REST). Each endpoint calls the shared _impl/_raw function
and applies version compat at the boundary.
"""

from __future__ import annotations

import inspect
import logging
from importlib import import_module
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.core.auth_context import require_auth, resolve_auth
from src.core.resolved_identity import ResolvedIdentity
from src.core.tools._announced_shape import builder_for
from src.core.tools.registry import TOOLS
from src.core.version_compat import apply_version_compat
from src.routes._derived_body import derived_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


# Note: ToolError handling lives entirely in the global ``@app.exception_handler``
# in src/app.py — REST routes never catch ToolError or import the MCP-boundary
# type (AdCPToolError). The wire-code -> HTTP status table moved to
# src/core/tool_error_logging.py alongside handle_tool_error.


# ---------------------------------------------------------------------------------------
# Routes are DERIVED from the registry. There is no @router decorator to write and no body
# model to assign: TOOLS says which tools are reachable over REST, with what verb and at
# what path, and everything else is resolved from the row.
#
# A tool with no ``*_raw`` wrapper gets no route. That is not an opt-out -- it is the three
# task tools, which ARE their MCP wrapper and have no transport-agnostic callable for a
# route to invoke. They acquire a route when they acquire a wrapper.


def _rest_handler(tool_name: str, spec: Any, raw: Any, body_model: type[BaseModel]) -> Any:
    """One route handler, built from a registry row.

    The body model is the derived one; the builder is resolved off the wrapper, the same
    way MCP resolves it to announce a shape. Nothing here re-states the field set: a route
    that repeated it would be a second place to disagree with the body class beside it.
    """
    builder = builder_for(raw) or builder_for(getattr(raw, "__wrapped__", raw))

    async def handler(body: body_model, identity: ResolvedIdentity | None = None) -> Any:  # type: ignore[valid-type]
        selected = derived_payload(body)
        req = builder(**selected) if builder is not None else body
        response = raw(req=req, identity=identity)
        if inspect.isawaitable(response):
            response = await response
        result = response.model_dump(mode="json")
        # Version compat runs where it ran before and nowhere else. Whether it should run
        # on every tool is a RESPONSE-half question and deliberately not this ticket's.
        if tool_name == "get_products":
            return apply_version_compat("get_products", result, getattr(body, "adcp_version", None))
        return result

    handler.__name__ = tool_name
    handler.__doc__ = (raw.__doc__ or "").strip().split("\n")[0]
    dep = resolve_auth if spec.auth == "optional" else require_auth
    handler.__signature__ = inspect.Signature(
        [
            inspect.Parameter("body", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=body_model),
            inspect.Parameter(
                "identity",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=dep,
                annotation=ResolvedIdentity if spec.auth != "optional" else (ResolvedIdentity | None),
            ),
        ]
    )
    return handler


def _raw_wrapper_for(tool_name: str, impl: Any) -> Any:
    """The transport-agnostic ``*_raw`` callable for a row, or None if the tool has none."""
    module_name = impl.__module__
    for candidate in (module_name, module_name.rpartition(".")[0]):
        if not candidate:
            continue
        found = getattr(import_module(candidate), f"{tool_name}_raw", None)
        if found is not None:
            return found
    return None


for _name, _spec in TOOLS.items():
    if _spec.rest is None:
        continue
    _raw = _raw_wrapper_for(_name, _spec.impl)
    if _raw is None:
        continue
    # The body model IS the DTO. It used to derive from the MCP wrapper parameters, which
    # made the wrapper the REST accepted shape too; the wrappers are gone.
    _body_model = _spec.dto
    router.add_api_route(
        _spec.rest.path,
        _rest_handler(_name, _spec, _raw, _body_model),
        methods=[_spec.rest.verb],
        name=_name,
    )
