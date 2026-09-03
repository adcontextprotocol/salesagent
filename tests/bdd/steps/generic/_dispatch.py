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

#: Opt-in: a Given sets this when the scenario's claim is about WEBHOOK CREDENTIALS
#: rather than about one request. The seller must then answer the same way at every
#: place the transport lets a buyer hand it credentials — see
#: ``BaseTestEnv.credential_registrations``. Opt-in rather than inferred from a
#: ``push_notification_config`` being present, because most scenarios that carry one
#: are about the WEBHOOK (its URL, its echo), not about the credential-registration
#: surface, and they must keep dispatching exactly one request.
GRADE_EVERY_CREDENTIAL_LOCATION = "grade_every_credential_location"

#: Where the per-location results land: ``((location, TransportResult), ...)``.
CREDENTIAL_REGISTRATIONS = "credential_registrations"


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
    else:
        _record_credential_registrations(ctx, transport, result, kwargs)


def _record_credential_registrations(ctx: dict, transport: Any, result: Any, kwargs: dict[str, Any]) -> None:
    """Ask the env for the seller's answer at EVERY credential location, not just this one.

    A DEPARTURE FROM "one request, one outcome", and it is deliberate: for the
    opted-in scenarios this one When puts more than one request on the wire,
    because on at least one transport a buyer has more than one way to hand the
    seller webhook credentials, and a claim about "registrations" that exercised
    only one of them is a claim about a surface nothing looked at. WHICH transport
    that is, and how many places it has, is not stated here and must not be — see
    the env.

    The step layer stays transport-blind through it: WHICH locations exist, and
    what each is called, is the env's answer (``credential_registrations``), and
    this function neither knows nor asks how many there will be. If a THIRD
    location ever appears it appears there, silently, and every opted-in scenario
    grades it.

    Off by default (``GRADE_EVERY_CREDENTIAL_LOCATION``), so no existing scenario
    changes its dispatch count.
    """
    if not ctx.get(GRADE_EVERY_CREDENTIAL_LOCATION):
        return
    # The REALIZATION, verbatim — never ``bool(...)``. ``signed`` is not a flag: it is
    # one of False / True / "malformed" / "tampered"
    # (tests.helpers.signing.SIGNATURE_REALIZATIONS), and ``bool("malformed")`` is
    # True, so collapsing it here would hand this frame a WELL-FORMED signature while
    # the operation dispatch above carried the malformed one. The scenario would then
    # grade an acceptance at the credential location it exists to grade a refusal at,
    # and pass. A second credential location is the epic's headline bypass surface, so
    # these are the frames that can least afford the collapse. WHICH transport has one
    # stays the env's business, here too: this comment names the hazard, not the leg.
    ctx[CREDENTIAL_REGISTRATIONS] = ctx["env"].credential_registrations(
        transport,
        kwargs.get("push_notification_config"),
        result,
        signed=kwargs.get("signed", False),
    )


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
    # The two dispatch paths converge on the same ctx contract but NOT on the
    # same credential-location grading: ``AdCPTestClient.call`` takes a single
    # ``payload`` and has no ``signed`` parameter, so this path cannot ask the
    # env for the seller's answer at every credential location. Silently
    # skipping ``_record_credential_registrations`` here would let an opted-in
    # scenario grade ONE location and pass — the exact vacuity that helper
    # exists to prevent. Fail loudly instead; no scenario wires both today.
    if ctx.get(GRADE_EVERY_CREDENTIAL_LOCATION):
        raise RuntimeError(
            "dispatch_via_client: scenario opted into "
            f"{GRADE_EVERY_CREDENTIAL_LOCATION!r}, which only dispatch_request grades. "
            "Dispatch through dispatch_request, or teach AdCPTestClient.call the "
            "credential-registration contract first."
        )
    client = ctx["client"]
    if identity is not NO_IDENTITY_OVERRIDE:
        result = client.call(tool, payload, ctx["transport"], identity=identity)
    else:
        result = client.call(tool, payload, ctx["transport"])
    _populate_ctx_from_result(ctx, result)
