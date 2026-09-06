"""Transport enum and TransportResult for multi-transport behavioral tests.

Defines the seven dispatch transports (IMPL, A2A, REST, MCP + E2E variants)
and a frozen result container that separates transport-specific envelope from
shared payload.

Usage::

    result = env.call_via(Transport.REST, creatives=[...])
    assert result.is_success
    assert result.payload.creatives[0].action == CreativeAction.created
"""

from __future__ import annotations

import functools
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from tests.helpers import pinned_schema


@functools.lru_cache(maxsize=1)
def _pinned_error_metadata() -> dict[str, dict[str, str]]:
    """code -> {recovery, suggestion} from the installed SDK's error-code enum.

    The SDK tree is the single source of truth for schema SHAPE
    (``tests/helpers/pinned_schema.py``). Sourcing this enum from it rather than
    from the vendored ``tests/fixtures/adcp_schemas_pinned/`` copy is a no-op on
    every field any consumer reads: measured 2026-08-12, the two trees carry the
    same 92 enum codes and 93 ``enumMetadata`` entries, with ZERO ``recovery``
    and ZERO ``suggestion`` divergences. They are not byte-identical — the
    ``$id`` differs, each naming its own tree — so the vendored copy is retained
    deliberately as an INDEPENDENT pin (docs/adcp-spec-version.md "Pinned schema
    sources"), not as a second source of shape.

    Only ``recovery`` is read here (see ``assert_wire_error``);
    ``extract_wire_suggestion`` below reads the WIRE's own suggestion text, not
    this metadata. Consumers that grade ``suggestion`` CONTENT
    (test_architecture_error_suggestion_enum_conformance.py) stay on the
    vendored fixture — see docs/adcp-spec-version.md "Pinned schema sources".
    """
    return pinned_schema.load("error-code.json")["enumMetadata"]


def is_pinned_error_code(code: str | None) -> bool:
    """Whether ``code`` is a canonical AdCP error code in the pinned enum.

    The guard an outcome-dispatch step needs BEFORE calling
    :meth:`TransportResult.assert_wire_error`: that method hard-fails on a code
    production cannot emit (a scenario-only code like ``DOMAIN_INVALID_FORMAT``),
    so a step whose scenarios can carry one must route those through a
    reconstructed-exception branch instead of the wire assertion.

    EMITTABILITY, not spec membership. The question is CODE_TABLE membership —
    "can production put this code on the wire at all" — not "is this code in the
    pinned spec enum". Those diverged when the code rewriters were deleted: the
    AdCP error vocabulary is OPEN (core/error.json: ``error.code`` is a wire-typed
    string, published codes are documentary, senders MAY emit codes outside the
    set), so a platform code like ``MEDIA_BUY_REJECTED`` now reaches the buyer
    unrewritten and IS assertable on the wire. Keeping the pinned-enum question
    here would silently route every platform-coded wire error to the lossy
    reconstruction branch. Same source as ``assert_wire_error``, so the two never
    disagree on what "emittable" means.
    """
    from src.core.errors.codes import CODE_TABLE

    return code is not None and code in CODE_TABLE


def extract_wire_suggestion(envelope: dict | None) -> str | None:
    """The buyer-facing ``suggestion`` from a two-layer AdCP wire error envelope.

    STRICT error.json conformance: ``suggestion`` is a top-level sibling of
    code/message/field/retry_after/recovery on the error object (in either the
    ``errors[0]`` or the envelope-level ``adcp_error`` layer). A suggestion
    buried in the free-form ``details`` dict is NOT at the protocol position
    and deliberately does not satisfy this lookup — emitters that bury it are
    conformance bugs the harness must surface, not mask (#1417).
    Single source of truth for both ``TransportResult.assert_wire_error`` and
    the BDD ``_wire_suggestion`` step (#1417). Returns ``None`` when
    there is no envelope (IMPL / no-wire).
    """
    if not envelope:
        return None
    errors = envelope.get("errors") or [{}]
    adcp_error = envelope.get("adcp_error") or {}
    return errors[0].get("suggestion") or adcp_error.get("suggestion")


def _envelope_from_adcp_error(exc: Exception) -> dict[str, Any] | None:
    """Build a SYNTHESIZED envelope from an AdCPError instance.

    Used by ImplDispatcher (``tests/harness/dispatchers.py``) to populate the
    separate ``synthesized_error_envelope`` field — IMPL has no wire by
    definition and ``wire_error_envelope`` is reserved for real wire bytes
    captured by REST/MCP/A2A. Production code uses the same
    ``build_two_layer_error_envelope`` helper at the boundary, so the
    synthesized envelope matches what production would emit for the same
    exception. It does NOT verify that a regression in
    ``build_two_layer_error_envelope`` actually reaches the wire.

    ImplDispatcher is its ONLY caller, and deliberately so: no other transport
    may hand a rebuilt envelope to a test. It lives here rather than in
    ``dispatchers.py`` because this module is the dispatch-core both
    ``dispatchers.py`` and ``client.py`` import from; housing it in either would
    force the other to reach back across that boundary, which is exactly the
    mutual-lazy-import cycle this module breaks.

    A2A and REST tests asserting on ``result.wire_error_envelope`` see
    REAL wire bytes:
        - A2A: the artifact DataPart, carried VERBATIM on the ``WireError``
          that ``tests.harness._base`` raises, read back off ``.envelope``.
        - REST: the HTTP response body, captured directly by RestDispatcher.
        - MCP: the JSON string in ``ToolError``, parsed by McpDispatcher.
    """
    from src.core.exceptions import AdCPError, build_two_layer_error_envelope

    if isinstance(exc, AdCPError):
        return build_two_layer_error_envelope(exc)
    return None


def _wire_envelope_from_exception(exc: Exception) -> dict[str, Any] | None:
    """The REAL wire envelope stashed by the harness, or None. NEVER synthesized.

    When a wire dispatch fails, ``tests.harness._base`` raises ``WireError``
    carrying the envelope the buyer received VERBATIM, reachable as
    ``.envelope`` (A2A's failed-Task artifact DataPart, REST's >=400 body).
    Those real bytes are the only thing this helper will hand out. It used to
    read a ``_wire_error_envelope`` attribute stashed by
    ``_base._envelope_to_adcp_error``; that helper rebuilt a production
    exception class from wire bytes and is deleted, so the attribute has no
    producer left and reading it returns ``None`` on every real A2A and MCP
    error.

    It used to fall back to ``_envelope_from_adcp_error`` above, the same builder
    production calls, and return the result under ``wire_error_envelope`` — the
    field named for what actually crossed the wire. A scenario asserting on that
    field then graded the harness rebuilding an envelope from the exception it
    had just caught, which passes whether or not production emitted anything at
    all. Making the synthesized field private did not close
    that channel: the laundered copy arrives under the name of the thing it is
    impersonating.

    ``None`` is the honest answer when nothing crossed the wire. A transport that
    genuinely has no wire says so through ``has_wire=False`` and offers
    ``_synthesized_error_envelope`` under its OWN name, as ImplDispatcher does.
    Do not reintroduce the fallback here; pinned by
    ``tests/unit/test_harness_mcp_never_synthesizes.py``.
    """
    real_wire = getattr(exc, "envelope", None)
    return real_wire if isinstance(real_wire, dict) else None


def _envelope_from_mcp_error(exc: Exception) -> dict[str, Any] | None:
    """Extract the wire envelope from an MCP ToolError's JSON string."""
    from fastmcp.exceptions import ToolError

    if not isinstance(exc, ToolError):
        return None
    try:
        envelope = json.loads(str(exc))
        if isinstance(envelope, dict) and "errors" in envelope:
            return envelope
    except (json.JSONDecodeError, TypeError):
        pass
    return None


class Transport(StrEnum):
    """Dispatch transports for behavioral tests."""

    IMPL = "impl"  # Direct _impl() call
    A2A = "a2a"  # the A2A handler
    REST = "rest"  # FastAPI TestClient → route → invoke_tool() → _impl()
    MCP = "mcp"  # Mock Context → MCP wrapper → _impl()
    E2E_REST = "e2e_rest"  # Real HTTP via httpx → nginx → server
    E2E_MCP = "e2e_mcp"  # Real MCP via httpx → nginx → server (placeholder)
    E2E_A2A = "e2e_a2a"  # Real A2A via httpx → nginx → server (placeholder)


# Maps Transport → ResolvedIdentity.protocol value
TRANSPORT_PROTOCOL: dict[Transport, str] = {
    Transport.IMPL: "mcp",  # _impl doesn't inspect protocol; keep default
    Transport.A2A: "a2a",
    Transport.REST: "rest",
    Transport.MCP: "mcp",
    Transport.E2E_REST: "rest",
    Transport.E2E_MCP: "mcp",
    Transport.E2E_A2A: "a2a",
}


# The ONE identity-argument omission sentinel for the whole dispatch core
# (tests/harness/client.py, dispatchers.py, _base.py, _mixins.py — plus
# tests/helpers/mcp_envelope_capture.py, which carries the same distinction
# outside tests/harness/). Distinguishes "the caller did not pass identity="
# (fall back to whatever default THAT call site uses — env.identity_for(),
# self.identity, delegate-by-omission, PrincipalFactory.make_identity(), ...)
# from an EXPLICIT identity=None (deliberately unauthenticated dispatch).
# Previously reimplemented as a private object() in seven different function
# bodies plus two other module-level sentinels (client.py, mcp_envelope_
# capture.py) — this is the one shared object identity every comparison uses;
# each call site keeps its OWN fallback logic when it detects the sentinel,
# never folded into this constant. Scoped to the identity-argument omission
# disease specifically — other object()-as-sentinel uses in tests/harness/
# for unrelated fields (e.g. media_buy_create.py's OMIT_IDEMPOTENCY_KEY) are
# a different sentinel family and are not consolidated here.
NO_IDENTITY_OVERRIDE = object()


class MissingToolNameError(NotImplementedError):
    """A legacy ``env.call_via(transport, **kwargs)`` E2E dispatch had no way to
    derive the tool/skill name (no ``tool_name=`` kwarg, no per-env attribute
    to introspect it from).

    The ONE exception type for this failure mode, replacing what used to be a
    per-dispatcher fork (``TypeError`` in one, ``NotImplementedError`` in the
    other). Subclasses ``NotImplementedError`` deliberately: that is the one
    exception ``AdCPTestClient.call()`` re-raises as a hard wiring failure
    instead of downgrading into an error ``TransportResult`` — a missing tool
    name is a harness bug, not a simulated AdCP rejection.
    """


@dataclass(frozen=True)
class E2EConfig:
    """Configuration for E2E transport dispatch.

    Attributes:
        base_url: Docker stack URL (e.g., ``http://localhost:8092``). Stays
            PLAINTEXT — 487 bdd_e2e and 95 e2e tests target it and do not move.
        postgres_url: Docker PostgreSQL URL for factory data writes.
        tls_base_url: The SECOND origin the same stack serves, over real TLS at a
            dotted host (e.g. ``https://proxy.adcp.test:8443``). ``None`` when the
            stack publishes no TLS listener. Additive: only scenarios that need a
            real handshake read it (#1291).
        ca_bundle: ABSOLUTE path to the CA that signed the stack's leaf. Absolute
            because pytest does not always run from the repo root. ``None`` when
            there is no TLS listener to verify.
    """

    base_url: str
    postgres_url: str
    tls_base_url: str | None = None
    ca_bundle: str | None = None


# Fields `_serialize_for_a2a` adds to an A2A artifact DataPart. They are
# populated by the PROTOCOL layer (the pin's Protocol Envelope arm) and are not
# declared on any Pydantic response model, so they must come off before a body
# is validated — under extra="forbid" they are a hard ValidationError. The
# captured `wire_response` keeps them: siblings assert on the full envelope.
A2A_PROTOCOL_ENVELOPE_FIELDS = ("message", "success")


def strip_a2a_protocol_fields(data: dict[str, Any]) -> dict[str, Any]:
    """A copy of *data* without the A2A protocol-envelope fields.

    One definition, three call sites (``_run_a2a_handler``, the client's
    ``_deliver_a2a``, and ``BaseTestEnv._deliver_via_client``). Each used to
    spell the same two ``pop`` calls itself, so adding a third protocol field
    would have needed finding all of them.
    """
    return {k: v for k, v in data.items() if k not in A2A_PROTOCOL_ENVELOPE_FIELDS}


# The two values TransportResult.envelope["status"] may take. A DERIVED enum,
# never a synthesized HTTP status_code: fabricating an integer for MCP/A2A would
# turn today's silent no-op into a loud tautology — the harness asserting != 500
# against a number the harness itself invented.
DERIVED_STATUS_ADCP_ERROR = "adcp_error"
DERIVED_STATUS_TRANSPORT_FAULT = "transport_fault"


def derive_error_status(wire_error_envelope: dict[str, Any] | None) -> str:
    """Did the seller answer with a structured AdCP envelope, or fault?

    Reads each transport's OWN authentic evidence, because that is exactly what
    ``wire_error_envelope`` is built from — REST's real HTTP body, A2A's failed
    Task artifact DataPart, MCP's ToolError JSON. Recovering an envelope from any
    of them means the seller produced a structured AdCP rejection; recovering
    none means the request died as a transport fault before any envelope existed.

    This is the signal the storyboard Then actually means by "not a 500 or
    non-AdCP error shape", expressed so it grades on all three transports instead
    of only the one that happens to carry an HTTP status.
    """
    return DERIVED_STATUS_ADCP_ERROR if wire_error_envelope else DERIVED_STATUS_TRANSPORT_FAULT


@dataclass(frozen=True)
class DeliverResult:
    """What one transport delivery produced: the parsed payload AND its wire bytes.

    The harness used to carry these on two different channels — the payload came
    back as the return value of ``env.call_mcp``/``call_a2a``, while the wire was
    stashed on ``env._last_wire_response`` and read back ACROSS the object
    boundary by the dispatchers. Two channels for one delivery is what let a
    second writer appear (six sites on BaseTestEnv, three more in client.py) and
    what let the wire silently go stale, since nothing tied a stash to the call
    that produced it.

    One return value closes that structurally: there is no attribute for a second
    writer to write. ``wire_response`` is None where no wire exists (IMPL) or
    where the dispatch path does not observe one (the legacy
    ``_run_mcp_wrapper``).

    The #1858 round-2 remediation;
    pinned by ``test_architecture_harness_single_dispatch``.
    """

    payload: Any
    wire_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class TransportResult:
    """Normalized result from any transport dispatch.

    Attributes:
        payload: Pydantic response model (shared assertions target this).
        envelope: Transport-specific metadata (HTTP status, ToolResult, etc.).
        error: Exception raised during dispatch, if any.
        raw_response: Unprocessed transport response (httpx.Response, ToolResult, etc.).
        wire_response: Serialized success-path response body as a dict, captured
            from the real wire (REST HTTP JSON body, MCP structured_content, A2A
            artifact DataPart). ``None`` on error and on IMPL (no wire — serialize
            the typed ``payload`` instead). Lets success-path tests assert the
            actual serialized shape (e.g. the v3.1 format_id federation contract).
        wire_error_envelope: Raw two-layer error envelope dict captured from
            the actual wire bytes (REST HTTP body, MCP ToolError content text,
            A2A failed-Task artifact DataPart). ``None`` on success or on the
            IMPL transport, which has no wire. This is the canonical field
            for error verification — see ``tests/CLAUDE.md`` § Error
            Verification Policy.
        has_wire: Whether these bytes crossed a REAL wire, declared by the
            dispatcher AT CONSTRUCTION. Positive and required — never inferred
            at a read site from which transport enum happens to be in play,
            because that inference breaks (or, worse, silently reclassifies)
            the day ``Transport.IMPL`` is removed.

            REQUIRED and keyword-only, deliberately: a default would make
            omission mean "no wire", so a forgetful new dispatcher would send
            readers down the re-serialize path and a wire-shape assertion would
            pass green against a ``model_dump`` — the silent tautology the wire
            readers exist to raise on. Omitting it is a ``TypeError`` instead.

            Declared PER SITE, not per transport class: it is True only where
            the construction is downstream of an actual send/receive. A wire
            dispatcher's "missing config" guard constructs a result for a request
            that never left. Its catch-all ``except`` arm is a STRADDLE — it may
            fire before OR after bytes moved, and cannot tell which — so it
            declares False, because claiming a wire that may not exist is the
            failure mode that matters here: it would send a reader looking for a
            capture nothing produced.

            ``has_wire=True`` with ``wire_response is None`` on a success path
            means the env failed to STASH the wire. That is a harness bug to
            raise on loudly; it must never fall back to serializing the typed
            payload, which would assert nothing about the wire.

            SCOPE — this predicate governs the SUCCESS path only, and
            deliberately does NOT feed ``assert_wire_error``'s no-envelope
            diagnostic (which the lane in #1802 originally specified).
            The reason is concrete: a dispatcher's catch-all arm declares
            ``has_wire=False`` because it may fire before anything was sent, yet
            it can still derive a ``wire_error_envelope`` from the exception —
            ``A2ADispatcher``'s does exactly that. Wiring ``has_wire`` into that
            diagnostic would therefore report a genuine wire rejection as "no
            wire", which is worse than the message it replaces. Error-path
            wire-presence needs its own per-site declaration; that is not this
            lane's, and inventing one here would be the same identity-inference
            mistake in a new spelling.
        _synthesized_error_envelope: Two-layer envelope produced by
            ``build_two_layer_error_envelope`` against the IMPL-caught
            ``AdCPError`` — what production WOULD emit at the boundary.
            ``None`` on success and on REST/MCP/A2A (those expose the real
            wire envelope above instead). PRIVATE: read it through
            :meth:`error_envelope`, which is the only place allowed to decide
            that this value may stand in for a wire. A test that reads it
            directly verifies the envelope-builder contract against itself —
            production and the harness compute it from the same in-memory
            exception — so a regression in the boundary translator cannot be
            caught that way. Use REST/MCP/A2A for wire-shape regressions.
    """

    payload: BaseModel | None = None
    envelope: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None
    raw_response: Any = None
    wire_response: dict[str, Any] | None = None
    wire_error_envelope: dict[str, Any] | None = None
    _synthesized_error_envelope: dict[str, Any] | None = None
    has_wire: bool = field(kw_only=True)

    @property
    def is_success(self) -> bool:
        return self.error is None and self.payload is not None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def wire_error_object(self) -> dict[str, Any] | None:
        """The payload-layer error object (``errors[0]``) from the captured wire.

        The sanctioned READER for the error region. It exists because the harness
        previously published only assertions plus a raw envelope dict, leaving a
        step that needed the code, message or details with nothing to call — so
        every module hand-rolled ``(envelope.get("errors") or [{}])[0]`` its own
        way. Resolves through the single locator in
        ``tests/helpers/envelope_assertions.py``, so reader and assertion can
        never disagree about where the spec puts a field.

        Tolerant: ``None`` when no wire envelope was captured. Callers that must
        NOT tolerate that use :meth:`assert_wire_error` or
        :meth:`wire_error_details`.
        """
        from tests.helpers import locate_envelope_error

        return locate_envelope_error(self.wire_error_envelope)

    def error_code(self) -> str | None:
        """The error code for THIS result, whatever transport produced it.

        The wire envelope when there is one; otherwise the in-process exception's own
        ``error_code``. Both are legitimate: on a wire transport the envelope is what
        the buyer received, and on IMPL there is no wire at all -- the raised
        ``AdCPSalesAgentError`` IS the product, and its code comes from CODE_TABLE.

        What this deliberately does NOT do is rebuild a production error class from
        wire bytes to make the two look alike; that reconstruction is gone
        (salesagent-3dawm.15). Use this where a test is parametrized ACROSS
        transports including IMPL; use ``assert_wire_error`` where the scenario is
        specifically about the buyer-facing envelope.
        """
        wire = self.wire_error_code()
        if wire is not None:
            return wire
        code = getattr(self.error, "error_code", None)
        return str(code) if code is not None else None

    def wire_error_code(self) -> str | None:
        """``errors[0].code`` from the captured wire, or ``None`` with no wire."""
        error = self.wire_error_object()
        return error.get("code") if error else None

    def wire_error_details(self, code: str, *, recovery: str | None = None) -> Mapping[str, Any]:
        """The ``errors[0].details`` block, AFTER asserting the envelope carries ``code``.

        The escape hatch for oracles that cannot be expressed as an equality
        subset (non-empty array; every entry matches a regex; membership) — and
        it is deliberately STRONGER than the ``details=`` kwarg, not a way around
        it: taking the expected ``code`` means a details block from the wrong
        error is unreadable. Without that, an oracle grades the details of
        whatever envelope happened to be captured.

        Required-not-optional: raises if there is no wire envelope or no details
        block, so a caller never has to ``None``-check what the spec guarantees.
        """
        self.assert_wire_error(code, recovery=recovery)
        error = self.wire_error_object() or {}
        details = error.get("details")
        assert isinstance(details, dict), (
            f"expected a details object at errors[0].details for {code}, got {details!r}: {self.wire_error_envelope}"
        )
        return details

    def wire_error_issues(self, code: str, *, recovery: str | None = None) -> list[Mapping[str, Any]]:
        """The ``errors[0].issues`` array, AFTER asserting the envelope carries ``code``.

        Sibling of :meth:`wire_error_details`, for the channel the pin defines for
        field-level rejection: "``field`` (singular) cannot carry the full pointer
        map" (v3.1.1 core/error.json). Takes the expected ``code`` for the same
        reason -- an issues array from the wrong error is unreadable.

        Required-not-optional: raises when the array is absent, so a caller never
        None-checks a channel the scenario says must be there.
        """
        self.assert_wire_error(code, recovery=recovery)
        error = self.wire_error_object() or {}
        issues = error.get("issues")
        assert isinstance(issues, list) and issues, (
            f"expected a non-empty issues array at errors[0].issues for {code}, "
            f"got {issues!r}: {self.wire_error_envelope}"
        )
        return issues

    def error_envelope(self) -> dict[str, Any]:
        """The two-layer error envelope this dispatch produced. Raises if there is none.

        Three branches, spelled out because getting them wrong is this lane's
        whole subject:

        1. a captured wire envelope is present -> return it;
        2. no wire was captured AND the dispatcher declared no wire AND a
           synthesized envelope exists -> return the synthesized one;
        3. otherwise -> RAISE.

        Branch 2 is reachable only on IMPL, and NOT because ``has_wire`` says
        so. ``has_wire`` is ``False`` on every A2A, MCP and IMPL error — a
        catch-all may fire before anything was sent — so keying on it alone
        would hand back a rebuilt envelope on transports that HAVE a wire, and
        on A2A and MCP it would discard a real captured one. What actually
        isolates IMPL is that IMPL is the only dispatcher that populates the
        synthesized field at all. That single-producer invariant is the load
        bearing one, and it is pinned by
        ``tests/unit/test_harness_mcp_never_synthesizes.py``.

        Branch 3 covers the case every operand is ``None`` — an A2A catch-all
        that derived nothing. Falling back to re-serializing the typed payload
        there would assert nothing about the wire while looking green, which is
        the tautology this reader exists to prevent.
        """
        envelope = self.error_envelope_or_none()
        assert envelope is not None, (
            "Expected an error envelope, but none was captured "
            f"(is_error={self.is_error}, payload={self.payload!r}). The operation either "
            "succeeded or errored before reaching a transport."
        )
        return envelope

    def error_envelope_or_none(self) -> dict[str, Any] | None:
        """:meth:`error_envelope`, returning ``None`` instead of raising.

        For the callers that branch on envelope-presence as CONTROL FLOW rather
        than reading it — an MCP dispatch can fail with a ``ToolError`` that is
        genuinely not an AdCP envelope, and collapsing that branch would turn a
        correct assertion into an error. The success path already ships this
        same pair: ``_wire_or_none`` returns ``None`` for a declared no-wire
        while ``wire_field``/``wire_dict`` raise. Prefer the raising one.
        """
        if isinstance(self.wire_error_envelope, dict):
            return self.wire_error_envelope
        if not self.has_wire and isinstance(self._synthesized_error_envelope, dict):
            return self._synthesized_error_envelope
        return None

    def require_wire(self) -> dict[str, Any]:
        """The success-path body the buyer actually received, or a loud failure.

        The success-side counterpart of :meth:`assert_wire_error`, and for the same
        reason: the guarded read belongs on the object that HOLDS the wire, so every
        caller gets the same guard instead of re-deriving it. Three copies of this
        check had grown across the suite, and a fourth partial one — each free to
        drift, and each a place where a missing ``wire_response`` could fall through
        to a harness-side reconstruction and assert nothing.

        Two failures are distinguished because they mean different things: an error
        result was never going to have a success body, while a success result with no
        stashed body means the dispatch bypassed the real pipeline — the silent
        tautology this guard exists to make loud.
        """
        assert self.is_success, f"expected a success wire body, got error {self.error!r}"
        assert self.wire_response is not None, (
            "wire_response is None on a successful call — no wire body was stashed, so the "
            "dispatch bypassed the real pipeline and any assertion on it would grade a "
            "harness reconstruction rather than what the buyer received"
        )
        return self.wire_response

    def assert_wire_error(
        self,
        code: str,
        *,
        recovery: str | None = None,
        require_suggestion: bool = False,
        field: str | None = None,
        details: Mapping[str, Any] | None = None,
        issues: Sequence[Mapping[str, Any]] | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Assert this result carries the AdCP two-layer wire error ``code``.

        Transport-independent: reads the normalized ``wire_error_envelope`` the
        dispatcher captured for whatever transport produced this result, so the
        same call holds on a2a/mcp/rest. Recovery defaults to the PINNED AdCP
        enum's classification for ``code`` (pin-wins), making the assertion
        non-vacuous without per-scenario duplication. This is the single
        harness-provided way to verify an error on the wire — step definitions
        must not hand-roll envelope parsing.

        ``field`` pins ``errors[0].field``, the error.json pointer naming WHICH
        request field was rejected, ``details`` subset-checks
        ``errors[0].details``, and ``issues`` does the same per ENTRY of
        ``errors[0].issues`` -- the pin's field-level rejection map, which
        ``field`` (singular) cannot carry. They are kwargs here rather than
        separate wire_error_field()/wire_error_details()/wire_error_issues()
        assertions on purpose: one sanctioned error surface means a step never
        has to decide which mechanism to reach for. All three forward to
        ``assert_envelope_shape``; this method adds only the CODE_TABLE recovery
        default and the no-envelope diagnosis, never a second shape check.
        """
        from src.core.errors.codes import CODE_TABLE
        from tests.helpers import assert_envelope_shape

        entry = CODE_TABLE.get(code)
        assert entry is not None, (
            f"{code!r} is not an emittable error code (absent from CODE_TABLE, so no raise site "
            "can put it on the wire). Reconcile the feature to a code production can emit."
        )
        # CODE_TABLE, not the pinned spec enum: the vocabulary is OPEN and platform codes reach
        # the buyer unrewritten, so the default must come from the one table that classifies
        # every emittable code rather than from the spec subset.
        expected_recovery = recovery if recovery is not None else entry.recovery.value

        envelope = self.wire_error_envelope
        assert envelope is not None, (
            f"Expected a wire rejection with {code}, but no wire_error_envelope was captured "
            f"(is_error={self.is_error}, payload={self.payload!r}, "
            f"error={type(self.error).__name__ if self.error else None}: {self.error!r}). "
            "The operation either succeeded or errored before reaching a transport. "
            "When `error` is set but the envelope is not, the transport swallowed a typed "
            "error instead of framing it — name THAT, not the missing envelope."
        )
        assert_envelope_shape(
            envelope,
            code,
            recovery=expected_recovery,
            field=field,
            details=details,
            issues=issues,
            retry_after=retry_after,
        )
        if require_suggestion:
            # Presence, not equality: error.json defines `suggestion` as free-form
            # remediation text with no enumMetadata tie — unlike its sibling
            # `recovery`, whose enum relationship the schema does spell out. The
            # spec's own worked examples emit site-specific wording that differs
            # from the enum default, so pinning the text would grade the emitter's
            # prose rather than the contract.
            #
            # BOTH mirrored layers by name (#1547 item 3): an either-layer check
            # (`errors[0].get(...) or adcp_error.get(...)`) lets an emitter that
            # populates one layer satisfy every call site in the suite, making the
            # only defect this assertion exists to catch — the mirror breaking —
            # invisible.
            for layer, error in (("adcp_error", envelope["adcp_error"]), ("errors[0]", envelope["errors"][0])):
                assert error.get("suggestion"), (
                    f"{layer} carries no buyer-facing suggestion for {code}; the spec places the "
                    f"hint at the top level of the error object: {envelope}"
                )
