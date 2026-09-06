"""The one function that turns a response model into the body a buyer receives."""

from __future__ import annotations

from typing import Any

from adcp.types import ProtocolEnvelope


def to_wire(response: ProtocolEnvelope) -> dict[str, Any]:
    """Serialize a tool's response into the body every transport sends.

    One function, three callers. MCP puts the result in ``ToolResult.structured_content``,
    A2A in an artifact ``DataPart``, REST returns it as the HTTP body -- those three
    containers are the only thing that legitimately differs, because the transports really
    do have different envelopes. What goes INSIDE is the same bytes for all of them.

    There is nothing per-transport to add here, and adding one would be the defect this
    replaces. Each transport used to call ``model_dump(mode="json")`` itself and then reach
    into the result: A2A stamped ``message`` and ``success`` into the payload, MCP put the
    same ``message`` in a wrapper field, and REST emitted neither. A buyer therefore saw a
    different document per transport for one response object.

    Envelope fields need no help from this function. ``status``, ``task_id``, ``message``,
    ``replayed`` and the rest are declared on the response model, so they serialize like any
    other field and a field added to the envelope reaches all three transports without anyone
    editing a transport.

    The parameter is bound to ``ProtocolEnvelope``, not ``BaseModel``, because that inheritance
    IS the guarantee above. A plain pydantic model routed through here would type-check against
    the wider bound and produce a body with no envelope at all -- the same reasoning that binds
    ``mcp_result`` to ``AdCPBaseModel`` rather than to ``BaseModel``.
    """
    return response.model_dump(mode="json")
