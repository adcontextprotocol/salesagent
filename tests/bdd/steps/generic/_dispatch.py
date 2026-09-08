"""Shared dispatch helper for BDD domain step definitions.

Provides a single implementation of the transport-aware dispatch pattern
used across UC-004, UC-011, and future domain step files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tests.harness.transport import NO_IDENTITY_OVERRIDE

if TYPE_CHECKING:
    from tests.harness.transport import TransportResult

# NOTE: NO_IDENTITY_OVERRIDE is IMPORTED, never re-declared. A local
# `_SENTINEL = object()` renamed into this name would be a SECOND distinct
# object wearing the canonical name, and `identity is not NO_IDENTITY_OVERRIDE`
# would then compare against the local one — so a caller passing the harness's
# real sentinel (meaning "no override") would be misread as HAVING overridden
# identity. One object, one name.


def _populate_ctx_from_result(ctx: dict, result: TransportResult) -> None:
    """Populate ctx's dispatch-result contract from a ``TransportResult``.

    Shared post-processing for every dispatch path (``dispatch_request`` via
    ``env.call_via``, ``dispatch_via_client`` via ``AdCPTestClient.call``) so
    they populate the identical ctx contract the wire-first Then steps
    (``then_error.py``'s ``_wire_code``/``_wire_suggestion``/``_wire_error_object``)
    read — ``ctx['result']`` is the only key with exactly one producer; leaving
    it unset silently downgrades those Then steps to the lossy reconstructed
    ``ctx['error']`` fallback (disease scan).

    That contract is deliberately NARROW: ``ctx['result']`` always, plus
    ``ctx['error']`` on the error path and ``ctx['wire_response']`` on the
    success path. The detached ``ctx['response']`` / ``ctx['wire_error_envelope']``
    / ``ctx['synthesized_error_envelope']`` copies are gone — see below.
    """
    # Expose the normalized TransportResult so Then-steps can use the
    # harness-provided, transport-independent assertions (result.assert_wire_error)
    # instead of hand-rolling envelope parsing.
    ctx["result"] = result
    if result.is_error:
        ctx["error"] = result.error
        # NO ctx envelope copies. Then steps read ctx["result"].error_envelope(),
        # which is the one place allowed to decide whether a synthesized value
        # may stand in for a wire. Copying the two fields into ctx created a
        # second spelling of that decision — and only this seam ever wrote the
        # keys, so a scenario dispatched through _call_via saw None even when
        # the envelope HAD been captured on the result.
    else:
        # NO ctx["response"]. A provenance-stripped copy of the payload cannot
        # tell a Then whether it is reading a wire fact or an in-process
        # reconstruction — which is how a self-grading transport stayed green.
        # Steps read ctx["result"] (the TransportResult, stashed above) through
        # the guarded accessors in _outcome_helpers.py instead.
        # Propagate the real serialized success-path wire body so Then steps
        # can assert on what the buyer actually receives (ctx["wire_response"]),
        # not the reconstructed typed payload (REST HTTP body; A2A/MCP artifact
        # only when the env routes through _run_a2a_handler/_run_mcp_client).
        # None on IMPL / non-stashing envs; the wire_field() helper guards
        # against silent tautologies (#1417). See tests/CLAUDE.md
        # "TransportResult.wire_response".
        ctx["wire_response"] = result.wire_response


def dispatch_request(ctx: dict, *, identity: Any = NO_IDENTITY_OVERRIDE, **kwargs: Any) -> None:
    """Dispatch a request through ctx['transport'] via call_via, or direct call_impl.

    Stores the TransportResult in ctx["result"]; ctx["error"] on failure.
    If ctx["transport"] is a Transport enum, uses call_via directly.
    If it's a string, maps to Transport enum first.
    If absent, falls back to call_impl.

    The ``identity`` kwarg overrides the default identity for multi-agent
    and no-auth scenarios. When provided, it flows through to call_via
    (which uses kwargs.setdefault, so an explicit identity won't be clobbered).
    Use ``identity=None`` for no-auth scenarios.
    """
    if identity is not NO_IDENTITY_OVERRIDE:
        kwargs["identity"] = identity

    transport = ctx.get("transport")
    env = ctx["env"]
    # BDD dispatches on a wire transport only (IMPL was dropped from the default
    # parametrization, #1417). A missing transport is a wiring bug, not
    # an IMPL fallback — fail loudly rather than silently bypassing the wire.
    if transport is None:
        raise RuntimeError(
            "dispatch_request: ctx['transport'] is unset. BDD scenarios must dispatch "
            "through a wire transport (a2a/mcp/rest); the IMPL call_impl fallback was removed."
        )

    from tests.harness.transport import Transport

    if isinstance(transport, Transport):
        pass  # Already a Transport enum — use as-is
    elif isinstance(transport, str):
        transport_map = {
            "MCP": Transport.MCP,
            "mcp": Transport.MCP,
            "A2A": Transport.A2A,
            "a2a": Transport.A2A,
            "REST": Transport.REST,
            "rest": Transport.REST,
        }
        if transport not in transport_map:
            raise RuntimeError(f"dispatch_request: unrecognized wire transport {transport!r}")
        transport = transport_map[transport]
    try:
        result = env.call_via(transport, **kwargs)
        _populate_ctx_from_result(ctx, result)
    except Exception as exc:
        ctx["error"] = exc


def dispatch_via_client(ctx: dict, tool: str, payload: dict[str, Any], *, identity: Any = NO_IDENTITY_OVERRIDE) -> None:
    """Dispatch through ``AdCPTestClient.call`` instead of ``env.call_via``.

    Additive alternative to ``dispatch_request`` for scenarios wired onto the
    transport-generic ``AdCPTestClient`` (``tests/harness/client.py``, whose
    module docstring states the design). Populates the identical ctx contract via
    ``_populate_ctx_from_result`` so every existing wire-first Then step works
    unmodified regardless of dispatch path.

    Deliberately does NOT wrap ``client.call()`` in a blanket
    ``except Exception`` the way ``dispatch_request`` does for
    ``env.call_via``: ``AdCPTestClient.call`` already converts ordinary
    transport errors into an error ``TransportResult`` internally, and
    re-raises ``NotImplementedError`` / lets ``NoAddressForTransport``
    propagate on purpose — a harness wiring gap must surface as a hard
    failure, not get silently downgraded into ``ctx["error"]`` where
    ``then_operation_fails`` would mistake it for a real AdCP rejection
    (client.py's own anti-vacuity comment on ``call()``).
    """
    client = ctx["client"]
    if identity is not NO_IDENTITY_OVERRIDE:
        result = client.call(tool, payload, ctx["transport"], identity=identity)
    else:
        result = client.call(tool, payload, ctx["transport"])
    _populate_ctx_from_result(ctx, result)
