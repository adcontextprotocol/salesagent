"""REST API v1 endpoints.

REST transport for AdCP tools, proving the 3-transport pattern
(MCP + A2A + REST). Every route reaches its implementation through
``src.core.tools._boundary.invoke_tool``.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, create_model

from src.core.auth_context import require_auth, resolve_auth
from src.core.resolved_identity import ResolvedIdentity
from src.core.tools._announced_shape import apply_signature
from src.core.tools._boundary import invoke_tool
from src.core.tools._wire import to_wire
from src.core.tools.registry import TOOLS

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
# Every row with a ``rest`` binding gets a route. There is no second condition: the handler
# calls ``invoke_tool``, which reaches the implementation through the registry, so a row can
# no longer be reachable over one transport and not another for want of a per-tool wrapper.


def _body_model_for(spec: Any) -> Any:
    """The DTO, with any field carried in the URL path made optional.

    Not a second shape: it is the DTO subclassed, relaxing exactly the fields ``path_fields``
    names, so a buyer who puts the id in the URL -- the only place REST puts it -- is not
    rejected for omitting it from the body. The handler validates the merged result back into
    the DTO itself, which stays the accepted shape.
    """
    if not spec.rest.path_fields:
        return spec.dto
    relaxed: dict[str, Any] = {
        name: (spec.dto.model_fields[name].annotation | None, None) for name in spec.rest.path_fields
    }
    return create_model(f"{spec.dto.__name__}Body", __base__=spec.dto, **relaxed)


def _rest_handler(tool_name: str, spec: Any, body_model: type[BaseModel]) -> Any:
    """One route handler, built from a registry row.

    The body model IS the DTO, so FastAPI has already produced the request: there is no
    payload to extract and nothing to rebuild. This used to run ``derived_payload`` over a
    separately-derived body class and hand the result to a builder -- two more shapes
    between the buyer and the implementation, each able to drop a field the other accepted.

    PATH FIELDS are the one place the body is not the whole request. A row whose path is
    templated (``PUT /media-buys/{media_buy_id}``) names those fields in ``path_fields``, and
    the URL is the resource identity, so the path value WINS over a body that disagrees. The
    merge happens before validation because the DTO requires the field: validating the body
    first would reject a request that named the task in the only place REST puts it. The body
    model for such a row is the DTO with exactly those fields made optional -- derived from
    the row, so it is a projection of the one declaration, not a second one.
    """

    # body is annotated Any HERE and typed for real below: handler.__signature__ is
    # replaced wholesale with one carrying body_model, which is what FastAPI reads. The
    # inline annotation was a runtime variable in a type position -- decorative, and it
    # cost a type: ignore to say so.
    async def handler(body: Any, identity: ResolvedIdentity | None = None, **path_values: Any) -> Any:
        if path_values:
            body = spec.dto.model_validate({**body.model_dump(exclude_unset=True), **path_values})
        # Named, not frozen: the handler names the TOOL and ``invoke_tool`` reads the registry
        # per call. A route that froze the callable at import could not be substituted -- the
        # registry row and the thing the route invoked were two different objects.
        response = await invoke_tool(tool_name, body, identity)
        return to_wire(response)

    handler.__name__ = tool_name
    handler.__doc__ = (spec.impl.__doc__ or "").strip().split("\n")[0]
    dep = resolve_auth if spec.auth == "optional" else require_auth
    path_params = [
        # Typed from the DTO field, so the path segment is validated as the field it fills.
        inspect.Parameter(
            name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=spec.dto.model_fields[name].annotation,
        )
        for name in sorted(spec.rest.path_fields)
    ]
    apply_signature(
        handler,
        inspect.Signature(
            [
                *path_params,
                inspect.Parameter("body", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=body_model),
                inspect.Parameter(
                    "identity",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=dep,
                    annotation=ResolvedIdentity if spec.auth != "optional" else (ResolvedIdentity | None),
                ),
            ]
        ),
    )
    return handler


for _name, _spec in TOOLS.items():
    if _spec.rest is None:
        continue
    # The body model IS the DTO. It used to derive from the MCP wrapper parameters, which
    # made the wrapper the REST accepted shape too; the wrappers are gone. The one projection
    # is a templated path: those fields travel in the URL, so the body may omit them.
    router.add_api_route(
        _spec.rest.path,
        _rest_handler(_name, _spec, _body_model_for(_spec)),
        methods=[_spec.rest.verb],
        name=_name,
    )
