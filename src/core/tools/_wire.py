"""The one function that turns a response model into the body a buyer receives."""

from __future__ import annotations

from typing import Any

from adcp.types import ProtocolEnvelope

from src.core.version_negotiation import SERVED_ADCP_VERSION


def to_wire(response: ProtocolEnvelope) -> dict[str, Any]:
    r"""Serialize a tool's response into the body every transport sends.

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

    ``adcp_version`` is stamped HERE, and it is the one exception to "nothing to add" above --
    which it does not actually contradict, because it is not per-transport. It is a property of
    the SELLER, not of the response: the release this build served, identical on every response
    and unknowable to an implementation. AdCP 3.1.1
    ``compliance/universal/version-negotiation.yaml``, step ``get_capabilities_with_version``,
    grades it with ``envelope_field_present`` and ``envelope_field_pattern`` at path
    ``adcp_version`` -- "the release the seller actually served", release-precision
    ``^\d+\.\d+(-[a-zA-Z0-9.-]+)?$``. Advisory at 3.1, promoted at 3.2, MUST at 4.0.

    Stamped on the DICT rather than the model, and that is deliberate. No pinned response
    schema declares the field -- the storyboard narrative says so itself, "``additionalProperties:
    true`` makes the field invisible to them" -- and two of the fourteen responses are
    ``TaskResultEnvelope`` subclasses whose wrap serializer builds the body from the domain
    response and would drop an envelope field nobody projected. Stamping the body reaches all
    fourteen through one line; stamping the model would have reached twelve and needed a second
    edit for the other two.
    """
    body = response.model_dump(mode="json")
    body["adcp_version"] = SERVED_ADCP_VERSION
    return body
