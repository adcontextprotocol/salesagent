"""AdCP exception hierarchy for typed error handling across transport layers.

Business logic raises these exceptions. Transport layers (A2A, MCP, REST)
translate them to their protocol's error format via registered handlers.

Exception classes define the error vocabulary — transport layers format them.
Each exception carries a recovery classification (transient/correctable/terminal)
to help buyer agents decide whether to retry, fix, or abandon a request.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, ClassVar, cast

from adcp.server.helpers import adcp_error
from adcp.types import ErrorCode
from pydantic import BaseModel, ValidationError

from src.core.errors.codes import CODE_TABLE, AppErrorCode, ErrorCodeT, Recovery
from src.core.errors.details import (
    AccountSetupDetails,
    AdapterFailureDetails,
    BudgetDetails,
    CapabilityRefusalDetails,
    ConfigurationDetails,
    ConflictDetails,
    CreativeRejectionDetails,
    EntityRefDetails,
    ErrorDetails,
    InvalidStateDetails,
    ProductRefDetails,
    RejectionReasonDetails,
    ValidationDetails,
    VersionUnsupportedDetails,
)
from src.core.errors.issues import ErrorIssue, issues_from_validation_error, pointer_to_field

if TYPE_CHECKING:
    from collections.abc import Iterator

    from adcp.types import ContextObject

logger = logging.getLogger(__name__)

# The recovery vocabulary is the ``Recovery`` StrEnum in src/core/errors/codes.py
# -- one transcription of the wire schema's three values, not two. The parallel
# ``RecoveryHint`` Literal this module used to declare was a second copy of the
# same closed set, bridged to the enum by unchecked casts; it is deleted so the
# two cannot disagree.

# ---------------------------------------------------------------------------
# Error codes on the wire
# ---------------------------------------------------------------------------
# There is ONE classifier: ``CODE_TABLE`` in src/core/errors/codes.py, loaded from
# the pinned enums/error-code.json (92 published codes) plus this platform's own
# ``AppErrorCode`` members. The SDK's ``STANDARD_ERROR_CODES`` is a
# cross-check, never the authority, and is consulted only as a message fallback.
#
# Every code a raise site declares reaches the buyer VERBATIM: the AdCP error
# vocabulary is OPEN, so there is no translation at the transport boundary and no
# server-only set. Message, recovery and suggestion are all functions of the code
# (see docs/decisions/adr-010-graded-wire-fields-are-functions-of-the-code.md), so a
# raise site cannot make one of them disagree with the pin.
#
# That openness is the PIN's own words, not this module's preference. AdCP 3.1.1
# ``core/error.json`` types ``error.code`` as a bare ``string`` (minLength 1,
# maxLength 64) and states: "the standard codes published in
# ``enums/error-code.json`` are documentary, and senders MAY emit codes outside
# that set ... Receivers MUST decode unknown codes — treat the response as
# well-formed, read ``error.recovery`` for the recovery classification".
#
# Reconciliation note (merge of origin/main's #1858 storyboard-conformance work).
# origin/main answered the same problem with a different apparatus, all of which
# ``CODE_TABLE`` SUBSUMES, so none of it is carried here:
#
#   * ``RECOVERY_BY_WIRE_CODE`` / ``_load_pinned_recovery()`` — read ``recovery``
#     out of the pinned ``enums/error-code.json`` ``enumMetadata``. ``CODE_TABLE``
#     reads the same normative block of the same file and carries recovery
#     ALONGSIDE suggestion, message and status, so re-adding it would be a second
#     load of one file answering a question this one already answers.
#   * ``_SPEC_SUPPLEMENT_CODES`` (CREATIVE_NOT_FOUND, CONFIGURATION_ERROR) and
#     ``_SPEC_DEMOTED_CODES`` (NOT_SUPPORTED) — both existed to reconcile the SDK
#     helper's 38-code list against the pin. Loading the pin directly makes the
#     reconciliation unnecessary: the table classifies the two supplements and does
#     not contain the demoted one.
#   * ``WIRE_STANDARD_CODES`` / ``INTERNAL_CODES`` / ``ERROR_CODE_MAPPING`` /
#     ``translate_error_code`` / ``to_wire_error_code`` — a closed wire set plus a
#     boundary translator. The pin quoted above forbids the premise: a code outside
#     the published 92 is legal, and a receiver is REQUIRED to decode it from
#     ``recovery``. Collapsing MEDIA_BUY_REJECTED to POLICY_VIOLATION destroyed
#     information the spec says the buyer may consume.
#   * ``wire_advisory()`` — the one constructor for an ``errors[]`` advisory, which
#     derived recovery from the pin. ``build_error_object()`` below derives recovery
#     AND message AND suggestion from the same pin, and takes the typed exception
#     rather than a loose (code, message) pair, so a code and its details cannot
#     be paired wrongly at the call site.
#
# What DID come across from origin/main, because nothing here subsumed it:
# ``RETRY_AFTER_MAX`` / :func:`clamp_retry_after` below, and the two-families
# reading of :class:`AdCPConfigurationError`.


def _serialize_context(
    context: ContextObject | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Serialize an AdCP ContextObject (or dict) into a JSON-safe dict.

    Single source of truth for context serialization, so the envelope builder and
    every other reader emit byte-identical context payloads.

    Behavior:
        - ``None`` → ``None`` (caller decides whether to omit the key).
        - ``dict`` → shallow copy. Prevents aliasing footguns when one
          serialization layer mutates its copy and accidentally mutates
          the source context still held on the exception.
        - ``ContextObject`` → ``model_dump(mode="json", exclude_none=True)``.
          ``mode="json"`` coerces datetimes/UUIDs/etc. to JSON-serializable
          primitives; ``exclude_none=True`` matches the spec's emit-only-
          populated-fields norm.
        - anything else → log a warning and return ``None``. This is reached
          from ``build_two_layer_error_envelope``, which runs inside exception
          handlers — raising here would shadow the original exception and the
          boundary translator would fail open with no envelope. A malformed
          context drops to ``None`` instead.
    """
    if context is None:
        return None
    if isinstance(context, dict):
        return dict(context)
    if not isinstance(context, BaseModel):
        logger.warning(
            "_serialize_context expected dict or BaseModel, got %s; dropping context", type(context).__name__
        )
        return None
    return context.model_dump(mode="json", exclude_none=True)


# The pinned spec bounds retry_after: AdCP 3.1.1 ``core/error.json`` →
# ``retry_after`` is ``{"type": "number", "minimum": 1, "maximum": 3600}`` and its
# description reads "Sellers MUST return values between 1 and 3600. Clients MUST
# clamp values outside this range." Never emit more even when the underlying wait
# is longer. A spec constant, not an operational knob — deliberately not
# env-tunable.
RETRY_AFTER_MAX = 3600


def clamp_retry_after(seconds: float) -> int:
    """Clamp a raw retry_after to the spec Error model's [1, RETRY_AFTER_MAX] bound.

    The single home for the floor/ceiling every emitter shares — the idempotency
    policy's rejection branches and the egress seam's Retry-After passthrough.
    Callers layer any context-specific cap (e.g. an insert-rate window) on top.

    It lives here rather than beside either caller because this module already
    owns ``AdCPSalesAgentError.retry_after`` and the spec Error shape, so neither
    emitter ends up importing the other.
    """
    return min(max(1, math.ceil(seconds)), RETRY_AFTER_MAX)


def _rebuild_error(cls: type[AdCPSalesAgentError], code: ErrorCodeT) -> AdCPSalesAgentError:
    """Reconstruct a pickled or copied error.

    The ``hasattr`` branch is load-bearing: a class-coded subclass IS its code, so
    naming it again would trip ``AdCPSalesAgentError.__new__``'s "already names a code" refusal.
    ``__dict__`` restoration then repopulates ``_error_code`` and the rest.
    """
    return cls() if hasattr(cls, "_code") else cls(error_code=code)


def _details_to_wire(details: ErrorDetails | None) -> dict[str, Any] | None:
    """Render a details block for the wire.

    The construction API is a class; the wire slot is an object. This is the one
    place that conversion happens, so no caller reaches for ``model_dump()`` on
    its own and no raise site has to think about it.

    The ``Mapping`` branch that used to be here was migration scaffolding, for
    the window where some ``self.details`` were still plain dicts. All 177 sites
    now pass a declared class, so the branch is gone and a dict no longer has a
    path to the wire: ``AdCPSalesAgentError`` is generic in its detail type, so mypy
    refuses one at the raise site.
    """
    if details is None:
        return None
    return details.to_wire()


class AdCPSalesAgentError[DetailsT: ErrorDetails](Exception):
    """Base exception for all AdCP errors.

    Parameterized on the detail shape it carries. Parameterizing rather than
    overriding ``__init__`` on each of the 32 error classes that carry details
    is what keeps the narrowing free of boilerplate: one ``__init__`` signature
    here, typed ``DetailsT | None``, gives every subclass its own exact detail
    type. mypy then rejects both a dict and a foreign detail class at every
    raise site, and reading ``exc.details`` back is typed without a cast.

    Class-level identity is ``_code`` and nothing else, declared with
    ``ClassVar`` per PEP 526. The public ``error_code``, ``message``,
    ``recovery``, ``suggestion`` and ``status_code`` are read-only properties
    over ``_error_code`` — functions of the code, resolved from
    ``CODE_TABLE`` at every read, so no instance can carry a value that
    disagrees with the table by any route, assignment included.

    ``status_code`` joined that list in salesagent-pssfi. It used to be a
    per-class ``_default_status_code`` slot, which let a class redeclare its
    ``_code`` and keep a status inherited from a parent that meant something
    else — ``SimulationError`` emitted INVALID_REQUEST with
    ``AdCPNotFoundError``'s 404 — and forced the plain-``ToolError`` boundary to
    reconstruct a code → status table by walking ``__subclasses__()``, whose
    answer for INVALID_REQUEST was 400 or 404 depending on the import set. There
    is now no per-class slot to disagree with, and nothing to walk.

    Code that needs class-level identity reads ``cls._code`` directly. Instance
    code reads ``self.error_code`` etc. as before.

    Attributes:
        message: Human-readable error description (read-only, from CODE_TABLE).
        status_code: HTTP status for REST/FastAPI responses (read-only, from
            CODE_TABLE).
        error_code: Machine-readable error code string (read-only).
        recovery: Recovery classification for buyer agents (read-only, from
            CODE_TABLE).
        details: Optional structured error details.
        field: Optional field name that caused the error.
        suggestion: Correction hint for buyer agents (read-only, from
            CODE_TABLE).
        context: Optional AdCP ContextObject (or dict) echoed in the
            envelope so buyer agents can correlate failures to the
            request that produced them (spec 3.0.0 normative).
        internal_detail: Optional NON-WIRE diagnostic payload — the raw
            third-party exception (or free text) that caused this error.
            NEVER serialized: ``build_two_layer_error_envelope`` ignores it. It
            exists so a raise site has a sanctioned destination for text whose
            provenance we do not control, instead of interpolating it into
            ``message``.
            See the class note below.

    Message provenance (AdCP 3.1.1 ``transport-errors.mdx`` § Security
    Considerations / Seller Requirements, lines 659-670): "Error responses
    flow through LLM context. Every field is client-facing. Implementations
    MUST NOT include: internal service names, hostnames, or IP addresses;
    database error text …; stack traces or file paths; upstream API responses
    from internal services; credentials, tokens, or session identifiers."

    ``adcp_error_for()`` returns an already-typed ``AdCPSalesAgentError``
    unchanged, so for a typed error THE RAISE SITE IS THE WIRE — there is no
    downstream sanitization point. That is why ``message`` is no longer
    authored at all: it is a read-only property returning
    ``CODE_TABLE[code].message``, and ``__init__`` takes no ``message``
    parameter, so the prohibited categories above cannot be interpolated into
    buyer-facing text even by accident. The trust decision is made once, in the
    table, instead of per raise site.

    Where the spec POSITIVELY requires request-specific content — version
    negotiation must name the buyer's requested version and the seller's
    supported set — that content goes in ``details``, which is exactly where
    the spec reads it from: see ``AdCPVersionUnsupportedError`` below, whose
    recovery is "re-pin to a release in the returned
    ``error.details.supported_versions``". Structured values in ``details``,
    third-party text in ``internal_detail`` (logged server-side by
    ``adcp_error_for()``, never emitted), and nothing at all in
    ``message``.
    """

    #: The code this class IS. Annotation only on the base: a class that declares
    #: none cannot be constructed (see ``__new__``), so a code is identity rather
    #: than a default anyone can fall through to.
    #:
    #: There is NO class-level recovery or suggestion knob. Both existed as
    #: ``_default_recovery``/``_default_suggestion`` overrides until it was
    #: measured that zero subclasses used either — the table owned every value
    #: in practice, so the knobs were only a route by which a class could come
    #: to disagree with the pin. They were deleted rather than guarded.
    _code: ClassVar[ErrorCodeT]

    # Instance attributes — set in __init__.
    # ``error_code``, ``message``, ``recovery`` and ``suggestion`` are NOT
    # here: they are read-only properties over ``_error_code``, so none of
    # those slots can be written after construction.
    _error_code: ErrorCodeT
    internal_detail: BaseException | str | None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Refuse, at class creation, a subclass whose code the table does not classify.

        ``CODE_TABLE`` is the single classifier: every code carries its
        recovery, suggestion and message there, so a class naming a code
        outside it could never resolve those three. Failing here moves that
        contradiction from the first raise (a ``KeyError`` deep in an error
        path) to import time, where the class definition itself is the error.
        """
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_code") and cls._code not in CODE_TABLE:
            raise TypeError(
                f"{cls.__name__} declares _code {cls._code!r}, which CODE_TABLE does not "
                "classify. Declare a code the table knows, or add the entry."
            )

    def __new__(cls, *args: Any, **kwargs: Any) -> AdCPSalesAgentError:
        """Refuse to build an error whose code is absent, or doubly named.

        The invariant is: an error names a code, by its class OR explicitly. Both
        halves are refused here, so neither can be expressed.

        ``_code`` is annotation-only on the base, so ``hasattr`` is False here and
        True on every subclass that declares one. This is the check
        ``object.__new__`` performs for an abstract class and that
        ``BaseException.__new__`` does not: ABC is a runtime no-op for exception
        classes, so without this a bare ``AdCPSalesAgentError()`` would construct and put a
        null code on the buyer's wire.

        The second branch is why there is no ``synthesize()``: a boundary that needs
        a code the class hierarchy does not model names it on the base, and a class
        that already IS a code cannot be overridden into disagreeing with itself.
        Nothing scans for either violation; neither can be constructed.
        """
        has_class_code = hasattr(cls, "_code")
        named = kwargs.get("error_code") is not None
        if has_class_code and named:
            raise TypeError(f"{cls.__name__} already names a code; do not override it")
        if not has_class_code and not named:
            raise TypeError(f"{cls.__name__} declares no _code and none was named")
        return cast("AdCPSalesAgentError", super().__new__(cls, *args, **kwargs))

    def __init__(
        self,
        *,
        error_code: ErrorCodeT | None = None,
        details: DetailsT | None = None,
        issues: list[ErrorIssue] | None = None,
        field: str | None = None,
        retry_after: int | None = None,
        context: ContextObject | dict[str, Any] | None = None,
        internal_detail: BaseException | str | None = None,
    ) -> None:
        # There is no ``message`` parameter. Buyer-facing text comes from CODE_TABLE
        # via the read-only ``message`` property, so no raise site can author it and
        # no caught exception's text can reach the wire. Provenance-bearing text goes
        # to ``internal_detail`` (server log only); values go to ``field``/``details``.
        #
        # Assigned FIRST: every derived property keys on it.
        self._error_code = error_code if error_code is not None else type(self)._code
        # A class-coded error's membership is already settled at class creation
        # (``__init_subclass__``); a NAMED code is checked here, so an
        # out-of-table code cannot outlive construction on either path.
        # ``message``/``recovery``/``suggestion`` need no assignment at all:
        # they are read-only properties resolving from CODE_TABLE per read.
        if self._error_code not in CODE_TABLE:
            raise TypeError(
                f"error_code {self._error_code!r} is not classified by CODE_TABLE; "
                "name a code the table knows, or add the entry."
            )
        self.details = details
        self.issues = issues
        # The pin's MUST: when issues[] is present, `field` is populated from
        # issues[0].pointer, translated to the JSONPath-lite spelling. Derived
        # HERE rather than at the emit site, so every reader of the error sees one
        # value -- the same reason _serialize_context lives in one place. An
        # explicitly passed field wins, so a caller can still point at something
        # other than issues[0].
        if field is None and issues:
            field = pointer_to_field(issues[0].pointer)
        self.field = field
        self.retry_after = retry_after
        self.context = context
        # NON-WIRE. Deliberately absent from
        # build_two_layer_error_envelope(); emitted only to the server-side log
        # by adcp_error_for(). Never add it to a serializer.
        self.internal_detail = internal_detail
        # args stays EMPTY: BaseException.__reduce__ replays ``cls(*args)``, and this
        # constructor takes none. ``__reduce__`` below replays the keyword form instead,
        # and ``__str__`` reads the property, so str(e) and .message cannot diverge.
        super().__init__()

    @property
    def error_code(self) -> ErrorCodeT:
        """The code this error carries. Read-only: a code cannot be swapped after the
        fact, so ``str(e)``, ``.message``, ``recovery`` and ``status_code`` cannot drift
        apart from it, and an out-of-table value cannot be introduced post-construction.
        """
        return self._error_code

    @property
    def message(self) -> str:
        """Buyer-facing text, derived from the code. There is no setter and no
        parameter: the text is a function of the code, not of the raise site.
        """
        return CODE_TABLE[self._error_code].message

    @property
    def recovery(self) -> Recovery:
        """The pinned recovery classification for this code. Read-only for the
        same reason as ``message``: recovery is the one field a receiver MUST
        read to decode an unknown code, so no instance may carry one that
        disagrees with the table. A :class:`Recovery` StrEnum member -- it
        compares and serializes as its wire string.
        """
        return CODE_TABLE[self._error_code].recovery

    @property
    def suggestion(self) -> str:
        """The pinned correction hint for this code, derived like ``message``."""
        return CODE_TABLE[self._error_code].suggestion

    @property
    def status_code(self) -> int:
        """The HTTP status this error is signalled with, derived like ``message``.

        No setter and no constructor parameter: two errors carrying one wire code
        cannot be answered with two different statuses, because there is nowhere
        left to say so. That is the whole fix for salesagent-pssfi — the old
        per-class slot was writable by inheritance, so a subclass could re-code
        itself and silently keep its parent's status.
        """
        return CODE_TABLE[self._error_code].status

    def __str__(self) -> str:
        return self.message

    def __reduce__(self) -> tuple[Any, ...]:
        # ``BaseException.__reduce__`` would replay ``cls(*args)``; args is empty and
        # this constructor is keyword-only, so the default breaks pickle and copy.
        return (_rebuild_error, (type(self), self._error_code), self.__dict__)

    @classmethod
    def iter_concrete_subclasses(cls) -> Iterator[type[AdCPSalesAgentError]]:
        """Yield every transitive *concrete* subclass of ``cls`` exactly once.

        Single source of truth for the subclass walk that backs the
        error-code compliance tests. (It also built the wire-code → HTTP-status
        table, until that table stopped existing: a status is now read from
        ``CODE_TABLE`` by code, so nothing has to be aggregated over whichever
        subclasses an import happened to define.) Yields descendants only — not
        ``cls`` itself — deduplicates so a class reachable by more than one
        path is visited once, and skips abstract bases (their descendants are
        still walked) so the name's "concrete" promise holds.
        """
        import inspect

        seen: set[type] = set()
        stack: list[type] = list(cls.__subclasses__())
        while stack:
            sub = stack.pop()
            if sub in seen:
                continue
            seen.add(sub)
            stack.extend(sub.__subclasses__())
            if not inspect.isabstract(sub):
                yield sub


class AdCPValidationError(AdCPSalesAgentError[ValidationDetails]):
    """Invalid parameters or request data (400)."""

    _code: ClassVar[ErrorCodeT] = ErrorCode.VALIDATION_ERROR


class AdCPVersionUnsupportedError(AdCPSalesAgentError[VersionUnsupportedDetails]):
    """Buyer pinned an adcp_version/adcp_major_version this seller doesn't support (400).

    Recovery is correctable per v3.1.1 error-code.json enumMetadata: re-pin to
    a release in the returned error.details.supported_versions and retry.

    The class is the authority on the code; ``VersionUnsupportedDetails`` is a
    shape and names none, so it stays reusable.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.VERSION_UNSUPPORTED


class AdCPInvalidRequestError(AdCPValidationError):
    """A structurally invalid request graded as INVALID_REQUEST by the storyboard (400).

    Distinct from operation-level VALIDATION_ERROR failures. The AdCP storyboard
    defines the code per operation, so callers must use the exception class graded
    for that scenario rather than inferring the code from validation phase alone.
    Inherits 400 + correctable from AdCPValidationError.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.INVALID_REQUEST


# v3.1.1 error-code.json deprecates the single AUTH_REQUIRED code in favor of
# a split: AUTH_MISSING (no credentials presented; correctable — provide
# credentials and retry) vs AUTH_INVALID (credentials presented but rejected;
# terminal — do not auto-retry, rotate/escalate). AUTH_REQUIRED itself is
# retained by the spec only as a deprecated backward-compat alias. See
# salesagent-mkso for the migration; distinct suggestion strings per code
# since "provide valid credentials" reads as invalid-framing for the
# genuinely-absent-credential sites.


class AdCPAuthenticationError(AdCPSalesAgentError[EntityRefDetails]):
    """Presented-but-invalid authentication credentials (401, AUTH_INVALID).

    Emits ``AUTH_INVALID`` per the v3.1.1 error-code enum: "Credentials were
    presented but rejected — revoked, malformed signature, or a key no longer
    in the seller's keystore ... Recovery: terminal." This is the base class
    for the presented-but-rejected case; ``AdCPAuthRequiredError`` below
    overrides to ``AUTH_MISSING`` for the genuinely-absent-credential case.

    Recovery is ``terminal`` — the buyer MUST NOT blindly auto-retry
    (rejected credentials, retried unmodified, will be rejected again);
    rotate/refresh once if applicable, otherwise escalate to a human.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.AUTH_INVALID


class AdCPAuthRequiredError(AdCPAuthenticationError):
    """No authentication context present (401, AUTH_MISSING).

    Raised when the request contains no auth token / identity at all. Per
    the v3.1.1 error-code enum: "No credentials were presented ... Recovery:
    correctable (provide credentials via the auth header and retry)."
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.AUTH_MISSING


class AdCPAuthorizationError(AdCPSalesAgentError[EntityRefDetails]):
    """Authenticated but not authorized for this resource (403).

    Emits ``PERMISSION_DENIED`` with ``correctable`` recovery per the v3.1.1
    error-code enum: "The authenticated caller is not authorized for the
    requested action under the seller's own policies." Distinct from
    ``AUTHORIZATION_REQUIRED`` (a downstream-platform-connection gap, not this
    class's shape) — migrated off the deprecated AUTH_REQUIRED alias
    (salesagent-otc5, completing salesagent-mkso for this axis).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.PERMISSION_DENIED


class AdCPPolicyViolationError(AdCPAuthorizationError):
    """Request content blocked by an advertising/content policy (403, POLICY_VIOLATION).

    Refines ``AdCPAuthorizationError`` (still a 403, still ``isinstance`` of it):
    the caller is permitted to call the tool, but the *content* of the request
    (brief, brand, targeting) violates a publisher policy. Carries the distinct
    ``POLICY_VIOLATION`` wire code, and the buyer can revise and retry, so
    recovery is ``correctable`` rather than the parent's ``terminal``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.POLICY_VIOLATION


class AdCPNotFoundError[D: ErrorDetails](AdCPSalesAgentError[D]):
    """Requested resource does not exist (404, REFERENCE_NOT_FOUND).

    Emits the PUBLISHED ``REFERENCE_NOT_FOUND`` rather than a minted generic
    ``NOT_FOUND``. error-handling.mdx: "Fall back to ``REFERENCE_NOT_FOUND`` for
    resource types without a dedicated code" and "Typed parameters that lack a
    dedicated standard code MUST use ``REFERENCE_NOT_FOUND`` rather than minting a
    custom ``*_NOT_FOUND`` code." A bare ``NOT_FOUND`` is exactly such a mint.

    Recovery=correctable, unchanged: ``REFERENCE_NOT_FOUND``'s pinned enumMetadata
    classifies it correctable, the same class the retired code carried.

    Subclasses that DO have a dedicated standard code (account, media buy,
    package, ...) override ``_code`` and are unaffected — the spec's not-found
    precedence prefers the resource-specific code when the resolved type is known
    from the request, and this base is only the fallback.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.REFERENCE_NOT_FOUND


class AdCPAdapterResourceNotFoundError(AdCPNotFoundError[AdapterFailureDetails]):
    """An ad server says a resource it owns does not exist (404, REFERENCE_NOT_FOUND).

    A GAM ad unit, order or line item; a Broadstreet advertiser or campaign. The
    resource belongs to the SELLER's ad server, so none of the entity-specific
    not-found codes (account, media buy, package, product, creative, format, task)
    describes it and the pin forbids minting a new one: error-handling.mdx says a
    type "without a dedicated code" MUST fall back to ``REFERENCE_NOT_FOUND``.

    Distinct from the base ``AdCPNotFoundError`` only in carrying a typed identity,
    which is what the no-base-raise guard exists to require, and in taking
    ``AdapterFailureDetails`` so the failing upstream call is nameable.

    Inherits ``REFERENCE_NOT_FOUND`` and recovery=correctable from the base: the
    buyer CAN act, by correcting the reference they supplied.
    """


class AdCPAccountNotFoundError(AdCPNotFoundError[EntityRefDetails]):
    """Account not found by ID or natural key (404, ACCOUNT_NOT_FOUND).

    Recovery=terminal per the pinned enumMetadata for ACCOUNT_NOT_FOUND —
    declared explicitly (the AdCPNotFoundError parent is correctable to
    match its INVALID_REQUEST wire code).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_NOT_FOUND


class AdCPAccountSetupRequiredError(AdCPSalesAgentError[AccountSetupDetails]):
    """Account exists but requires setup before use (422, ACCOUNT_SETUP_REQUIRED)."""

    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_SETUP_REQUIRED


class AdCPAccountSuspendedError(AdCPSalesAgentError[EntityRefDetails]):
    """Account is suspended and cannot be used (403, ACCOUNT_SUSPENDED).

    Recovery=terminal per the pinned enumMetadata — declared explicitly
    (the base default is transient to match its SERVICE_UNAVAILABLE wire code).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_SUSPENDED


class AdCPAccountPaymentRequiredError(AdCPSalesAgentError[EntityRefDetails]):
    """Account has outstanding payment requirements (402, ACCOUNT_PAYMENT_REQUIRED).

    Recovery=terminal: from the sales agent's perspective there is
    no in-band remediation — the buyer must settle the outstanding balance
    externally before resubmitting. Matches the BDD storyboard contract for
    UC-002 account-reference partition/boundary rows. Declared explicitly
    (the base default is transient to match its SERVICE_UNAVAILABLE wire code).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_PAYMENT_REQUIRED


class AdCPConflictError(AdCPSalesAgentError[ConflictDetails]):
    """Resource conflict, e.g. duplicate idempotency key (409).

    Recovery=transient per the pinned error-code.json enumMetadata (CONFLICT):
    a generic resource conflict (e.g. concurrent modification) is resolved by
    retrying with backoff. Subclasses whose specific code the enum classifies as
    correctable (ACCOUNT_AMBIGUOUS, IDEMPOTENCY_CONFLICT, IDEMPOTENCY_EXPIRED)
    override this (#1417).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.CONFLICT


class AdCPAccountAmbiguousError(AdCPConflictError):
    """Natural key matches multiple accounts (409, ACCOUNT_AMBIGUOUS)."""

    _code: ClassVar[ErrorCodeT] = ErrorCode.ACCOUNT_AMBIGUOUS
    # ACCOUNT_AMBIGUOUS is correctable per the enum (the buyer disambiguates with
    # an explicit account_id) — override the transient CONFLICT parent (#1417).


class AdCPGoneError(AdCPSalesAgentError[InvalidStateDetails]):
    """Resource previously existed but is no longer available (410).

    Recovery=correctable: the resource itself is gone, but the buyer can
    recover by referencing a different resource (a fresh proposal, a new
    media buy) and re-issuing the request.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.INVALID_STATE


class AdCPBudgetExhaustedError(AdCPSalesAgentError[BudgetDetails]):
    """Budget or spend limit has been reached (422).

    Recovery=terminal per the pinned error-code.json enumMetadata (BUDGET_EXHAUSTED):
    an exhausted budget cannot be recovered autonomously — an operator must add
    budget — so the buyer agent must not retry (#1417).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.BUDGET_EXHAUSTED


class AdCPRateLimitError(AdCPSalesAgentError[AdapterFailureDetails]):
    """Too many requests (429)."""

    _code: ClassVar[ErrorCodeT] = ErrorCode.RATE_LIMITED


class AdCPAdapterError(AdCPSalesAgentError[AdapterFailureDetails]):
    """External adapter (GAM, etc.) failure.

    Answered 503, like everything else emitting SERVICE_UNAVAILABLE: the status
    follows the code the buyer reads, and this class declared 502 against that
    code until salesagent-pssfi. An ad-server call that actually failed has its
    own 502 codes -- AD_SERVER_CREATE_FAILED / AD_SERVER_UPDATE_FAILED.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.SERVICE_UNAVAILABLE


class AdCPConfigurationError(AdCPSalesAgentError[ConfigurationDetails]):
    """Server-side configuration is broken (500).

    Two families of raise site, one meaning — this deployment is pointed at
    something wrong, and only an operator can repoint it:

    * local config: encrypted secrets that cannot be decrypted (key rotation,
      corruption, missing ENCRYPTION_KEY), a missing API key.
    * a REMOTE endpoint that is operator configuration — a registered creative
      or signals agent — refusing us, rejecting us with a terminal 4xx, or
      answering with something unparseable. The address came from this
      deployment, not from the buyer, so the buyer has no lever either way.

    Callers should NOT silently fall back — the configuration needs admin
    intervention, so recovery is ``terminal``: the buyer has no lever to fix
    server config and per the pinned enum "MUST NOT auto-retry". Choosing this
    class IS how a raise site says terminal; there is no ``recovery=`` knob to
    say it with, because recovery is a function of the code (ADR-010).
    CONFIGURATION_ERROR is a code the pinned table classifies — it reaches the
    wire untranslated (#1430 review).

    NOT for a buyer-supplied URL: that is :class:`AdCPUrlNotAllowedError`.
    Telling a buyer the SELLER is misconfigured about an address they chose
    inverts the provenance.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.CONFIGURATION_ERROR


class AdCPPersistedStateError(AdCPConfigurationError):
    """A persisted value is outside the vocabulary its column may hold (500).

    Raised wherever a persisted value cannot be published or stored: the ``status``
    write door refuses a value that would enter the column, the ``status`` read door
    refuses a value already in it, and the ``revision`` read door refuses an integer
    below the pinned minimum. The last is a bound rather than a vocabulary, and it
    reaches the buyer in both envelope layers — the pinned ``CONFIGURATION_ERROR``
    metadata permits that payload, so the contract is wider than "two doors of
    status" and this docstring says so rather than describing the narrower case it
    was written for.
    All are SELLER-side store defects — the buyer neither supplied the value nor can
    correct it — so this inherits ``CONFIGURATION_ERROR`` / ``terminal`` from
    ``AdCPConfigurationError`` rather than restating them. That is also what the
    pinned 3.1.1 ``enums/error-code.json`` metadata selects: ``VALIDATION_ERROR`` is
    ``correctable`` and advises "review error details and fix field values", advice
    the buyer cannot act on for data it does not own, and an invitation to retry a
    call that will fail identically.

    The message names the buy, the column and the legal member set, because that is
    what makes the defect actionable for the seller's operator, who is the only party
    who can fix it.

    It does NOT say the buyer never sees it — this docstring said that twelve lines
    above its own statement that the message reaches the buyer in both envelope
    layers. Both are true of the same string: it is written for the operator and it is
    delivered to the buyer, which is exactly why it names a column rather than a
    stack frame.
    """


class AdCPServiceUnavailableError(AdCPSalesAgentError[AdapterFailureDetails]):
    """Service or product temporarily unavailable (503).

    503 indicates a temporary outage in a downstream service the sales
    agent depends on. Recovery=transient so buyer agents retry rather
    than mutate the request.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.SERVICE_UNAVAILABLE


class AdCPInternalError(AdCPSalesAgentError[EntityRefDetails]):
    """The seller's own state is inconsistent, so the request cannot be completed (500).

    Distinct from AdCPServiceUnavailableError, which names a downstream outage, and from
    AdCPValidationError, which says the buyer's request is at fault. This says neither: the
    request was well formed and no dependency is down, but an invariant this seller relies
    on did not hold. The buyer cannot fix it by changing anything, and recovery is transient
    because the inconsistency may be a race that a retry resolves.

    INTERNAL_ERROR is a platform code (AppErrorCode), legal on the wire because AdCP 3.1.1's
    code vocabulary is open, and classified in CODE_TABLE like every other code this seller
    emits.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.INTERNAL_ERROR


class AdCPUrlNotAllowedError(AdCPValidationError):
    """A buyer-supplied URL names a host this seller will not contact (400).

    Emits the PUBLISHED ``VALIDATION_ERROR``, not a platform code. This class briefly
    carried a minted ``URL_NOT_ALLOWED`` on the reasoning that VALIDATION_ERROR "tells a
    buyer nothing they can act on differently". That reasoning does not survive the pin:
    malformed-vs-value-refused is already the published INVALID_REQUEST / VALIDATION_ERROR
    split (INVALID_REQUEST is "malformed, missing required fields, or violates schema
    constraints"; VALIDATION_ERROR is "invalid field values or violates business rules
    beyond schema validation"), and a schema-valid https URI refused by a deny-list is the
    second. The pinned spec then applies it to this exact vector:
    ``dist/docs/3.1.0/learning/specialist/security.mdx:84`` has the practitioner register
    ``https://169.254.169.254/latest/meta-data/`` and "observe that the agent refuses it
    synchronously with a ``VALIDATION_ERROR`` on ``notification_configs[].url``".

    The open vocabulary permits minting a code the spec has NOT defined; it does not make
    a private synonym of a published member a good idea, because a buyer switching on
    ``error.code`` across sellers loses the ability to handle this uniformly.

    The class survives the code change on purpose: the A2A boundary catches it BY TYPE to
    select ``InvalidParamsError``, which a bare ``AdCPValidationError`` could not express
    without also catching every other validation failure. Being a SUBCLASS costs nothing
    there — ``isinstance`` still discriminates the URL refusal exactly.

    It is a subclass rather than a sibling because two fail-closed handlers depend on the
    subsumption, and both are load-bearing rather than incidental:
    ``src/services/delivery_webhook_scheduler.py`` and ``src/core/context_manager.py`` each
    wrap the registration gate (``webhooks/registration.py`` →
    ``reject_unsafe_webhook_registration_url``) in ``except AdCPValidationError`` precisely
    so a refused registration becomes a logged non-delivery instead of an exception that
    kills the scheduler loop or fails a status transition. As a direct
    ``AdCPSalesAgentError`` subclass — which is how this branch declared it — an SSRF
    refusal escapes both. The parent's ``ValidationDetails`` replaces the
    ``ValueRejectionDetails`` this class was parameterized on; no raise site in the tree
    passes ``details=`` to it, so that parameter was carrying nothing.

    The buyer's actionable signal is the CODE plus ``field`` (which URL was refused). The
    rejection REASON never reaches the buyer -- the spec's Security Considerations forbid
    disclosing internal service names, hostnames or IP addresses, so the cause rides
    ``internal_detail`` (server log only). Deliberate loss in the switch: the retired
    entry's suggestion enumerated the refused host classes, where VALIDATION_ERROR's is
    the generic "review error details and fix field values". A per-class override is NOT
    the fix -- it would make the suggestion a function of the class rather than the code,
    which ADR-010 forbids (the override knob that once allowed it is deleted).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.VALIDATION_ERROR


# ---------------------------------------------------------------------------
# Typed subclasses for spec-compliant error codes.
# ---------------------------------------------------------------------------
# Each subclass pins its wire error_code to a CODE_TABLE entry (the pinned
# enums/error-code.json plus this platform's own AppErrorCode members), so
# raise sites can use semantic names (AdCPMediaBuyNotFoundError) instead of
# constructing Error(code="MEDIA_BUY_NOT_FOUND") inline. The boundary
# translator runs build_two_layer_error_envelope() on the raised exception.


class AdCPMediaBuyNotFoundError(AdCPNotFoundError[EntityRefDetails]):
    """Media buy lookup failed (404, MEDIA_BUY_NOT_FOUND).

    Recovery=correctable: the buyer can correct by supplying the right
    media_buy_id (typo, wrong tenant, stale reference). Overrides the
    ``AdCPNotFoundError`` ``terminal`` default — for this specific not-found
    case the buyer's own request is the lever for recovery.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.MEDIA_BUY_NOT_FOUND


class AdCPPackageNotFoundError(AdCPNotFoundError[EntityRefDetails]):
    """Package lookup failed within a media buy (404, PACKAGE_NOT_FOUND).

    Recovery=correctable: the buyer can correct by supplying the right
    package_id. Overrides the ``AdCPNotFoundError`` ``terminal`` default for
    the same reason as ``AdCPMediaBuyNotFoundError``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.PACKAGE_NOT_FOUND


class AdCPProductNotFoundError(AdCPNotFoundError[ProductRefDetails]):
    """Requested product does not exist (404, PRODUCT_NOT_FOUND).

    Recovery=correctable: the buyer can correct by supplying a valid
    product_id (discoverable via get_products). Overrides the
    ``AdCPNotFoundError`` ``terminal`` default for the same reason as
    ``AdCPMediaBuyNotFoundError`` — the buyer's own request is the lever
    for recovery. PRODUCT_NOT_FOUND is a standard SDK code (passthrough,
    emitted as itself).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.PRODUCT_NOT_FOUND


class AdCPContextNotFoundError(AdCPNotFoundError[EntityRefDetails]):
    """Buyer-supplied context_id does not resolve (404, SESSION_NOT_FOUND).

    A ``context_id`` that does not map to a persistent context is a not-found
    condition, not a gone/expired one: ``Context`` rows have no TTL, expiry, or
    delete path anywhere in ``src/``, so a non-resolving id never existed. That
    rules out ``AdCPGoneError`` (``INVALID_STATE``) — the correct wire code is
    ``SESSION_NOT_FOUND``, the standard SDK code for an unresolvable
    session/context (emitted as itself).

    Recovery=correctable: the buyer can correct by supplying a valid context_id
    or omitting it to start a fresh context. Overrides the ``AdCPNotFoundError``
    ``terminal`` default for the same reason as ``AdCPMediaBuyNotFoundError``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.SESSION_NOT_FOUND


class AdCPCreativeNotFoundError(AdCPNotFoundError[EntityRefDetails]):
    """Requested creative does not exist (404, wire CREATIVE_NOT_FOUND).

    ``CREATIVE_NOT_FOUND`` is a pinned-spec wire code (enums/error-code.json @
    04f59d2d5): correctable, and MANDATED uniformly for any creative_id not
    owned by the calling account — never distinguish "exists under another
    principal/tenant" from "does not exist" (anti-enumeration). It reaches the
    wire untranslated: CODE_TABLE classifies it.

    Recovery=correctable: the buyer can correct by supplying a valid creative_id
    (discoverable via list_creatives / sync_creatives).
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.CREATIVE_NOT_FOUND


class AdCPFormatNotFoundError(AdCPNotFoundError[EntityRefDetails]):
    """Requested creative format does not exist on the agent (404, REFERENCE_NOT_FOUND).

    Emits the PUBLISHED ``REFERENCE_NOT_FOUND``, not a minted ``FORMAT_NOT_FOUND``.
    The pinned spec forbids the latter by name: release-notes.mdx (#2704) lists
    ``FORMAT_NOT_FOUND`` among eleven custom codes that "collapse to
    ``REFERENCE_NOT_FOUND`` with ``error.field`` naming the failed parameter" and
    closes "Sellers returning any of the 11 collapsed codes today MUST switch to
    ``REFERENCE_NOT_FOUND``". error-handling.mdx restates it generally: "Typed
    parameters that lack a dedicated standard code MUST use ``REFERENCE_NOT_FOUND``
    rather than minting a custom ``*_NOT_FOUND`` code".

    This is NOT the open-vocabulary allowance. An open vocabulary permits a code
    the spec has not defined; it does not permit one the spec explicitly REMOVED
    and replaced under a MUST.

    ``field="format_id"`` is retained deliberately. The uniform-response rule
    requires a type-NEUTRAL field when naming it would leak a polymorphic
    parameter's resolved type, but creative/specification.mdx names this exact
    case the other way: "``REFERENCE_NOT_FOUND``: Requested format does not exist
    or is not accessible (``error.field`` identifies the ``format_id``)".
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.REFERENCE_NOT_FOUND


class AdCPTaskNotFoundError(AdCPNotFoundError[EntityRefDetails]):
    """Requested workflow task/step does not exist (404, REFERENCE_NOT_FOUND).

    ``TASK_NOT_FOUND`` is not among the eight resource-specific not-found codes
    the pinned spec enumerates (PRODUCT/PACKAGE/MEDIA_BUY/CREATIVE/SIGNAL/SESSION/
    ACCOUNT/PLAN), so error-handling.mdx's general MUST applies: "Typed parameters
    that lack a dedicated standard code MUST use ``REFERENCE_NOT_FOUND`` rather
    than minting a custom ``*_NOT_FOUND`` code -- the vocabulary grows by upstream
    spec change, not by per-seller inflation."

    Positively graded upstream: the get_products_async storyboard step
    ``get_products_task_status_wrong_account`` expects ``REFERENCE_NOT_FOUND``, and
    ``get_task_status`` is a registered MCP tool, so this envelope is buyer-facing.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.REFERENCE_NOT_FOUND


class AdCPBudgetTooLowError(AdCPSalesAgentError[BudgetDetails]):
    """Requested budget falls below product minimum (422, BUDGET_TOO_LOW)."""

    _code: ClassVar[ErrorCodeT] = ErrorCode.BUDGET_TOO_LOW


class AdCPCapabilityNotSupportedError(AdCPSalesAgentError[CapabilityRefusalDetails]):
    """Requested capability is not supported by this seller (422, UNSUPPORTED_FEATURE).

    .. note::
        **Spec-conformant.** The pinned AdCP error-code enum classifies
        ``UNSUPPORTED_FEATURE`` as ``correctable`` ("check
        get_adcp_capabilities and remove unsupported fields"), and we emit
        ``correctable`` — so this matches the spec, it is not a divergence.
        The buyer holds the recovery lever: they can fix the request by
        dropping the unsupported feature (e.g. removing ``property_list``
        targeting against an adapter that doesn't compile it).

        Only the adcp SDK's ``STANDARD_ERROR_CODES`` table classifies it
        ``terminal``; the SDK is not authoritative (the pinned spec enum is),
        so its table diverges from the spec here. If the SDK runtime ever
        starts enforcing ``terminal`` at the wire (rejecting our spec-correct
        ``correctable`` hint), reconcile with the SDK then.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.UNSUPPORTED_FEATURE


class AdCPIdempotencyConflictError(AdCPConflictError):
    """idempotency_key reused with a different request payload (409, IDEMPOTENCY_CONFLICT).

    Recovery=correctable: the buyer can fix this and resend — either replay the
    ORIGINAL bytes under the same key, or mint a fresh idempotency_key for the
    new payload. This matches the AdCP 3.0.1 prose example envelope and the
    conformance storyboard's stated expectation. The SDK's
    ``STANDARD_ERROR_CODES`` table classifies the code ``terminal``, but that
    table is only a default applied when no recovery is supplied — an explicit
    recovery always wins, and nothing in the SDK or the storyboard's machine
    validations grades the value.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.IDEMPOTENCY_CONFLICT


class AdCPIdempotencyExpiredError(AdCPConflictError):
    """idempotency_key seen before, but its replay window has expired (409, IDEMPOTENCY_EXPIRED).

    Raised when a same-key buy exists but outlived the advertised replay TTL
    (``get_adcp_capabilities.adcp.idempotency.replay_ttl_seconds``): per
    security.mdx#idempotency rule 6, a request arriving after eviction with a
    key the seller has seen SHOULD be rejected with ``IDEMPOTENCY_EXPIRED``
    rather than silently treated as new or answered with another buy's data.

    Recovery=correctable, matching the sibling ``IDEMPOTENCY_CONFLICT``: the
    buyer agent recovers autonomously — a natural-key existence check (e.g.
    ``get_media_buys`` by ``context.internal_campaign_id``) to learn whether the
    original request succeeded, then either accept that result or mint a fresh
    idempotency_key for a new attempt. The 3.0.1 ``error-code.json`` enum
    description classifies the code ``correctable`` (that buyer-recovery path),
    and the recovery taxonomy reserves ``terminal`` for conditions requiring
    HUMAN action (account suspended, payment required) — not an agent-resolvable
    retry. The SDK's ``STANDARD_ERROR_CODES`` default table lists it ``terminal``,
    but that default applies only when no recovery is supplied; an explicit
    recovery wins, exactly as for ``IDEMPOTENCY_CONFLICT``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.IDEMPOTENCY_EXPIRED


class AdCPCreativeRejectedError(AdCPSalesAgentError[CreativeRejectionDetails]):
    """Creative failed policy or technical validation (422, CREATIVE_REJECTED)."""

    _code: ClassVar[ErrorCodeT] = ErrorCode.CREATIVE_REJECTED


class AdCPBudgetExceededError(AdCPSalesAgentError[BudgetDetails]):
    """Requested budget exceeds tenant or product ceiling (422, BUDGET_EXCEEDED)."""

    _code: ClassVar[ErrorCodeT] = ErrorCode.BUDGET_EXCEEDED


class AdCPProductUnavailableError(AdCPSalesAgentError[EntityRefDetails]):
    """Product is offline, sold out, deactivated, or otherwise unavailable (422).

    Emits the PUBLISHED ``PRODUCT_UNAVAILABLE``, whose pinned description covers
    the whole condition: "The requested product is sold out or no longer
    available."

    This absorbed ``AdCPInventoryUnavailableError``, which was the same error
    under a second name: same 422, same ``PRODUCT_UNAVAILABLE``, same
    correctable recovery, and nothing anywhere caught or ``isinstance``-checked
    the two apart. Two classes emitting one code with identical handling give a
    buyer no distinction to switch on and give a raise site a coin to flip. The
    distinction that DOES matter -- which product, and why -- belongs in
    ``details``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.PRODUCT_UNAVAILABLE


# ---------------------------------------------------------------------------
# Adapter-taxonomy subclasses.
# ---------------------------------------------------------------------------
# These extend AdCPAdapterError to carry a failure taxonomy as the class identity
# instead of smuggling it through ``details["internal_code"]`` (which is
# buyer-visible). Each class's ``error_code`` now reaches the buyer AS ITSELF: the
# AdCP vocabulary is open, so a specific platform code plus its recovery tells the
# buyer more than a collapse onto SERVICE_UNAVAILABLE did.


class AdCPWorkflowError(AdCPAdapterError):
    """Workflow-step orchestration failed inside an adapter (WORKFLOW_CREATION_FAILED, 502).

    Carries the WORKFLOW_CREATION_FAILED taxonomy as the class identity, and
    that code is what reaches the buyer -- so 502 is its status, read from the
    code like every other. Recovery=transient: the workflow subsystem may
    succeed on retry.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.WORKFLOW_CREATION_FAILED


class AdCPLineItemError(AdCPAdapterError):
    """Adapter line-item creation failed (SERVICE_UNAVAILABLE, 503).

    The one adapter-taxonomy subclass that declares no code of its own: it
    inherits ``AdCPAdapterError``'s SERVICE_UNAVAILABLE, and therefore that
    code's 503. It read 502 until salesagent-pssfi gave the code the status.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.AD_SERVER_CREATE_FAILED


class AdCPBulkUpdateError(AdCPAdapterError):
    """A bulk update partially failed — N operations attempted, M failed (PARTIAL_FAILURE, 502).

    Unifies the cross-adapter partial-failure event under one class and one
    status so REST clients filtering on HTTP status don't fork by adapter
    (previously broadstreet raised 502, GAM raised 503 for the same semantic
    event). Carries the PARTIAL_FAILURE taxonomy as the class
    identity; per-operation detail (failed IDs, counts) belongs in ``details``
    as data. Recovery=transient (inherited): failed operations may succeed
    on retry.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.PARTIAL_FAILURE


class AdCPActivationWorkflowError(AdCPAdapterError):
    """Adapter order/line-item activation workflow failed (ACTIVATION_WORKFLOW_FAILED, 502).

    Distinct from ``AdCPWorkflowError`` (creation): this is the activation step
    of an existing order. Carries the ACTIVATION_WORKFLOW_FAILED taxonomy as the
    class identity; same wire mapping as the other adapter-workflow failures.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.ACTIVATION_WORKFLOW_FAILED


class AdCPGamUpdateError(AdCPAdapterError):
    """A GAM line-item update API call failed (AD_SERVER_UPDATE_FAILED, 502).

    Carries the GAM_UPDATE_FAILED taxonomy as the class identity; per-operation
    detail (package_id, line_item_id) belongs in ``details`` as data.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.AD_SERVER_UPDATE_FAILED


class AdCPMediaBuyRejectedError(AdCPSalesAgentError[RejectionReasonDetails]):
    """The seller declined the media buy (422 → POLICY_VIOLATION).

    A business rejection, not a server failure: recovery=correctable so the
    buyer can adjust the request and resubmit. Carries the MEDIA_BUY_REJECTED
    taxonomy as the class identity; the wire code is the standard POLICY_VIOLATION.
    """

    _code: ClassVar[ErrorCodeT] = AppErrorCode.MEDIA_BUY_REJECTED


def build_error_object(exc: AdCPSalesAgentError) -> dict[str, Any]:
    """The single per-error object for an advisory list (``errors[]`` entries).

    Same derivation as ``build_two_layer_error_envelope``, which is the point: a second
    place that turns a code into buyer-facing text will disagree with this one, and did —
    a tools-layer copy keyed the message off the WIRE code while this keys it off the RAW
    code, so 10 of 41 subclasses produced two different sentences for one failure.
    """
    return dict(build_two_layer_error_envelope(exc)["errors"][0])


def build_two_layer_error_envelope(exc: AdCPSalesAgentError) -> dict[str, Any]:
    """Build the AdCP spec-compliant two-layer error envelope from an exception.

    Wraps the stable ``adcp_error()`` SDK helper for the payload half
    (``errors[]``), then mirrors the single error object at envelope level
    as ``adcp_error`` so the storyboard runner can read either path. Echoes
    ``exc.context`` when present.

    Returns:
        Plain dict with shape::

            {
                "adcp_error": {"code": "...", "message": "...", "recovery": "...", ...},
                "errors": [{"code": "...", "message": "...", "recovery": "...", ...}],
                "context": {...},     # only when exc.context is set
            }

    Both layers carry ``exc.error_code`` VERBATIM. There is no translation step: the
    AdCP error vocabulary is OPEN (core/error.json -- ``error.code`` is a wire-typed
    string, the published codes are documentary, senders MAY emit codes outside that
    set, and receivers MUST decode an unknown code by reading ``error.recovery``), so
    a platform code reaches the buyer as the raise site declared it.
    """
    payload = adcp_error(
        exc.error_code,
        exc.message,
        recovery=exc.recovery,
        field=exc.field,
        suggestion=exc.suggestion,
        retry_after=exc.retry_after,
        details=_details_to_wire(exc.details),
    )
    # issues[] is injected into the payload BEFORE the mirror is copied below.
    # It cannot ride adcp_error(): that helper has no `issues` parameter, and its
    # `details` is typed flat-scalars-only, so the array fits through neither.
    # Injecting after the copy would put issues on errors[0] and NOT on the
    # envelope-level adcp_error -- the two-layer divergence the comment below
    # exists to prevent.
    if exc.issues:
        payload["errors"][0]["issues"] = [issue.to_wire() for issue in exc.issues]
    # Copy errors[0] for the envelope-level mirror so callers that mutate one
    # layer don't accidentally mutate the other (aliasing footgun once both
    # layers may be mutated independently).
    envelope: dict[str, Any] = {
        "adcp_error": dict(payload["errors"][0]),
        "errors": payload["errors"],
    }
    serialized_context = _serialize_context(exc.context)
    if serialized_context is not None:
        envelope["context"] = serialized_context
    return envelope


# Canonical buyer-facing suggestions from error-code.json enumMetadata (AdCP 3.1.1):
# each code carries its own default hint, so a VALIDATION_ERROR must not borrow
# INVALID_REQUEST's text.


def first_validation_error_field(validation_error: ValidationError) -> str | None:
    """Return the bracket-notation path of the first Pydantic error, or ``None``.

    Lets a transport boundary attach a structured ``field`` to the
    ``AdCPValidationError`` it raises, so the wire envelope carries the offending
    field path instead of only the rendered message. List indices render as
    ``[i]`` so boundary-derived paths such as ``packages[0].budget`` align with
    the ``packages[].budget`` field strings raised by the implementation layer.
    """
    errors = validation_error.errors()
    if not errors:
        return None
    parts: list[str] = []
    for loc in errors[0]["loc"]:
        if isinstance(loc, int):
            parts.append(f"[{loc}]")
        elif parts:
            parts.append(f".{loc}")
        else:
            parts.append(str(loc))
    return "".join(parts)


def _log_internal_detail(exc: AdCPSalesAgentError) -> None:
    """Emit an ``AdCPSalesAgentError``'s non-wire ``internal_detail`` to the server log.

    The single emission point for every raise site that hands its raw cause to
    ``internal_detail=`` instead of interpolating it into the buyer-facing
    ``message``. It lives here because ``adcp_error_for()`` is the one
    place every error from every transport (MCP, A2A, REST) passes through, so
    one line replaces a hand-rolled ``logger.error(raw)`` at each raise site —
    and covers the sites that log nothing at all today.
    """
    detail = exc.internal_detail
    if detail is None:
        return
    logger.error(
        "AdCPSalesAgentError %s internal detail (not emitted to the buyer): %s",
        type(exc).__name__,
        detail,
        exc_info=detail if isinstance(detail, BaseException) else None,
    )


def adcp_error_for(exc: Exception, field: str | None = None) -> AdCPSalesAgentError:
    """Normalize untyped exceptions to typed AdCPSalesAgentError subclasses.

    Single source of truth for the wrapping applied at all three transport
    boundaries (MCP, A2A, REST). Already-typed ``AdCPSalesAgentError`` passes through
    unchanged. Pydantic ``ValidationError`` maps to a structured, sanitized
    ``AdCPValidationError``; other ``ValueError`` instances map to the plain
    validation error, ``PermissionError`` to ``AdCPAuthorizationError``, and
    anything else names INTERNAL_ERROR on the base.

    Every branch keeps its type mapping and carries NO text: an untyped exception's
    string has no provenance guarantee (it may be a DB DSN, a stack fragment, or an
    upstream response body -- AdCP 3.1.1 transport-errors.mdx Security Considerations
    MUST-NOT list), and the code's own table sentence is what the buyer sees. The
    original exception is still logged in full server-side by the transport
    boundary's record_boundary_error() / audit logger.
    """
    if isinstance(exc, AdCPSalesAgentError):
        _log_internal_detail(exc)
        return exc
    # A pydantic ValidationError is BY CONSTRUCTION a schema-constraint violation, and
    # 3.1/enums/error-code.json is explicit about which code that earns:
    #   INVALID_REQUEST  "malformed, missing required fields, or violates SCHEMA CONSTRAINTS"
    #   VALIDATION_ERROR "invalid field values or violates business rules BEYOND schema validation"
    # So this branch maps to INVALID_REQUEST; the plain-ValueError branch below stays
    # VALIDATION_ERROR, because a ValueError our own business logic raises is exactly the
    # "beyond schema validation" case. REST already answered INVALID_REQUEST here, so this
    # also closes the MCP/A2A-vs-REST divergence rather than merely documenting it.
    if isinstance(exc, ValidationError):
        # ValidationError is checked BEFORE ValueError deliberately: a pydantic
        # ValidationError IS a ValueError subclass, so the order decides whether a
        # buyer gets the field and issues or a bare VALIDATION_ERROR.
        errors = exc.errors()
        return AdCPInvalidRequestError(
            field=field if field is not None else first_validation_error_field(exc),
            issues=issues_from_validation_error(errors),
        )
    if isinstance(exc, ValueError):
        return AdCPValidationError()
    if isinstance(exc, PermissionError):
        return AdCPAuthorizationError()
    return AdCPSalesAgentError(error_code=AppErrorCode.INTERNAL_ERROR)


# ---------------------------------------------------------------------------
# Names origin/main spells differently
# ---------------------------------------------------------------------------
# Aliases, not classes: each pair below is ONE concept that the two branches
# named differently, so binding a second name costs nothing, while defining a
# second class would put two answers on the wire for one failure.
#
# ``AdCPError`` is this branch's ``AdCPSalesAgentError`` under its former name.
# The rename is repo-wide here (42 modules) but origin/main's egress work landed
# after it, so ``src/core/helpers/outbound_error_mapping.py`` and
# ``src/core/security/egress/policy.py`` still import the old spelling. Those two
# modules ALSO still call the retired constructor API — a positional ``message``
# and a plain-dict ``details``, both of which this base class refuses — so this
# alias makes them import, not work. They need porting to the keyword-only,
# typed-details constructor before either can raise. Delete this name in the same
# change.
AdCPError = AdCPSalesAgentError

# ``AdCPBlockedUrlError`` is origin/main's name for the SSRF refusal, and the two
# were ONE condition, not two: the pinned 3.1.1 ``enums/error-code.json`` defines
# no URL/SSRF code at all (the nearest, AGENT_BLOCKED, is about a blocked AGENT),
# and both branches already resolved a refused URL to the same published
# VALIDATION_ERROR — "invalid field values or violates business rules beyond
# schema validation", as against INVALID_REQUEST's "malformed ... or violates
# schema constraints". A schema-valid https URI refused by a deny-list is the
# former. So the spec distinguishes nothing here for a second class to carry, and
# there is one class with one alias.
#
# The surviving class takes origin/main's HIERARCHY (subclass of
# AdCPValidationError) and this branch's NAME and body — see the class docstring
# for why the hierarchy half is a behavior fix rather than a preference.
# origin/main's other difference, an authored ``_default_message`` ("URL resolves
# to a restricted range."), is subsumed: the message here is the code's own table
# sentence, which is the ADR-010 rule the whole taxonomy follows and which keeps
# the refused host out of buyer-facing text by construction.
AdCPBlockedUrlError = AdCPUrlNotAllowedError
