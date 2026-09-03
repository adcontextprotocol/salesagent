"""The ONE seam that decides how an outbound AdCP webhook is authenticated (#1291 C1).

``salesagent-z6nr.18``. Core Invariant: *every outbound AdCP webhook is authenticated
by exactly ONE mode, selected at ONE seam from the receiver's own registration, and
the bytes signed are the bytes sent.*

This module owns **policy only**. ``adcp.webhooks.WebhookSender`` owns the mechanism —
it serializes once, signs those exact bytes, and POSTs them
(``send_raw``: *"Byte-exact serialization — this is the ONLY representation that gets
signed AND posted"*). So #1441 (a signature computed over a re-serialization of the
body) is unreachable through this boundary by construction rather than by three call
sites remembering a rule.

What we decide, and nothing else:

* **which mode a receiver gets** — :func:`legacy_auth_mode`. security.mdx @ v3.1.1
  :1424 keys mode selection on ``authentication`` being PRESENT, *not* on its value
  being HMAC: an ``authentication`` block naming Bearer selects the LEGACY arm too.
  The three senders spelled this three different ways before C1 (``"HMAC-SHA256"``,
  ``"Bearer"``, ``"bearer"``/``"basic"``), so a bearer-registered receiver could be
  handed an RFC 9421 signature it must answer with ``webhook_mode_mismatch``
  (:1466). One case-insensitive predicate replaces all three.
* **where the tenant's key comes from** — ``resolve_signing_material``, which is the
  same row -> ref -> PEM -> published-JWK-tripwire path the request signer uses.
* **what we may honestly declare** — :func:`webhook_signing_posture`, checked against
  the algorithm we are about to sign with before the sender is handed back.

Mode selection is a CONSTRUCTOR choice, so "signed both ways" (which :1425 forbids)
is not a rule to enforce but a shape that cannot be expressed: a ``WebhookSender``
holds exactly one auth strategy, and ``signs_with_rfc9421`` reports which.

**Destination policy: there is no operator-supplied client here any more.** Read at
the pin, ``adcp/webhooks.py`` branches on ``_owns_client``: ``:1727`` — *"Operator-supplied
client: trust them completely; they own SSRF"* — and ``:1604``, that an operator-supplied
client SKIPS the SDK's check; while the owned-client path (``:1636``, ``:1715``)
builds a PINNED transport that resolves the URL, validates it, and pins the
connection to the validated IP before anything is serialized.

So a ``client=`` parameter on this module was never "our transport owns SSRF,
exactly as today". It was the one way to reach the SDK arm that validates nothing at
DELIVERY time, leaving only a caller's fire-time check and the TOCTOU between the two
resolutions. It is now GONE rather than merely unused (GH #1802, GH #1890): a
parameter no caller passes today is still a parameter the next caller can pass, and
the point of a seam is that the unpinned dial is unrepresentable rather than
discouraged. Every sender built here owns the SDK's pinned client
(``allow_private_destinations=False``), and the ONE socket this module opens itself —
:func:`send_signed_challenge` — goes through
:func:`src.core.security.outbound_http.asend`, which resolves once and pins to that
address, refuses redirects, sets ``trust_env=False``, applies the port allowlist and
caps the response body. Nothing in this module imports ``httpx``.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol, runtime_checkable

from adcp.webhooks import WebhookDeliveryResult, WebhookSender

from src.core.enum_helpers import enum_value
from src.core.exceptions import AdCPConfigurationError
from src.core.security.outbound_http import CounterpartyUrl, OutboundDeliveryFailed, asend
from src.core.signing.posture import webhook_signing_posture
from src.core.signing.provider import resolve_signing_material

if TYPE_CHECKING:  # pragma: no cover - typing only
    from adcp.webhook_auth import JwkSignerStrategy

    from src.core.database.repositories.signing_key import SigningKeyRepository

logger = logging.getLogger(__name__)

#: The receiver registered HMAC-SHA256 and supplied a credential.
LEGACY_HMAC = "hmac"

#: The receiver registered a token-bearing scheme (Bearer / Basic). The SDK has one
#: token constructor; ``Basic`` receivers therefore get ``Authorization: Bearer
#: <token>``. That is a deliberate consequence of routing every legacy scheme through
#: one sender and is logged below, not silently swallowed.
LEGACY_BEARER = "bearer"

#: ``authentication`` is present but carries no usable credential. Still the LEGACY
#: arm: :1425 forbids answering a legacy registration with an RFC 9421 signature, so
#: the honest outcome is an unauthenticated delivery, never a signed one.
LEGACY_UNCREDENTIALED = "uncredentialed"

#: Spellings of the legacy HMAC scheme seen on real registrations, lower-cased.
_HMAC_SCHEMES = frozenset({"hmac-sha256", "hmac_sha256", "hmac"})

#: Minimum HMAC credential length. Carried over verbatim from the delivery
#: service's own floor, which C1 folded into this boundary rather than dropping:
#: a credential shorter than this is brute-forceable and the pre-C1 behaviour was
#: to refuse to sign with it (and say so) rather than emit a weak signature.
#:
#: Named ...KEY_CHARS, not ...SECRET_CHARS: this is a policy threshold, never a
#: credential, but CodeQL's sensitive-data heuristic classifies any identifier
#: matching /secret/ as a secret, so logging it below tripped
#: py/clear-text-logging-sensitive-data at high severity. The name is the whole
#: cause -- do not rename it back.
_MIN_HMAC_KEY_CHARS = 32

#: Per-request timeout, matching what the three senders used before C1.
_TIMEOUT_SECONDS = 10.0

#: ``X-AdCP-Key-Id`` value for the legacy HMAC arm. The scheme has no key registry —
#: the SDK echoes this for receiver-side rotation only, and it is not part of the
#: signature.
_LEGACY_HMAC_KEY_ID = "adcp-legacy-hmac"

#: (warning id, tenant) pairs already warned about. security.mdx obliges an honest
#: posture, not a log line per webhook: without this the WARNING fires on EVERY delivery
#: for every keyless tenant, which today is all of them.
#:
#: KEYED BY PAIR, NOT BY TENANT. This set replaced two caches guarding two DISTINCT
#: conditions — deliveries going out unsigned, and a proof-of-control challenge that
#: cannot be signed at all. Under a tenant-only key whichever condition fired first would
#: permanently suppress the other, so an operator seeing "delivered unsigned" would never
#: learn that subscriber activation is also going to fail. The pair keeps one suppression
#: domain per warning, and a third warning gets its own for free instead of inheriting a
#: neighbour's.
_warned: set[tuple[str, str]] = set()
_warn_lock = threading.Lock()


@dataclass(frozen=True)
class _UnauthenticatedStrategy:
    """No auth headers at all — the pre-#1291 wire, kept reachable on purpose.

    Two registrations land here: a tenant with no active signing key (the 100% case
    until keys are provisioned — ``salesagent-7x8t``), and a legacy registration
    carrying no credential. Both must still DELIVER; what they must not do is
    acquire an RFC 9421 signature they never earned.

    It implements the SDK's public ``WebhookAuthStrategy`` protocol and is bound
    through ``WebhookSender._from_strategy``, the same internal constructor the SDK's
    own ``from_bearer_token`` / ``from_adcp_legacy_hmac`` classmethods use. The SDK
    exposes no unauthenticated constructor, and the alternative — keeping a raw
    ``httpx`` POST in the delivery services for this one case — would reintroduce
    exactly the second sending path the boundary exists to remove (and
    ``tests/unit/test_architecture_webhook_sender_boundary.py`` would catch it).
    """

    def build_auth_headers(self, *, method: str, url: str, body: bytes) -> dict[str, str]:
        return {}

    def reserved_headers(self) -> frozenset[str]:
        return frozenset({"content-length", "content-type", "host"})


@runtime_checkable
class WebhookAuthConfig(Protocol):
    """What the sender READS off a receiver registration — three attributes, no more.

    Declared structurally so the boundary names the SHAPE it needs instead of a concrete
    ORM class. Both a ``PushNotificationConfig`` row and the delivery service's frozen
    ``QueuedWebhook`` projection satisfy it, which is what lets the retry loop carry
    primitives instead of a live ORM instance whose lazy-loads need a session that may
    already be closed (#1757, salesagent-n78j0.4).

    Naming the concrete model here instead was a real constraint, not a cosmetic one: it
    made "queue a projection rather than the row" a type error, so the only way to keep
    mypy happy was to keep the ORM object on the queue.
    """

    @property
    def url(self) -> str: ...

    @property
    def authentication_type(self) -> str | None: ...

    @property
    def authentication_token(self) -> str | None: ...


def legacy_auth_mode(config: WebhookAuthConfig | None) -> str | None:
    """Which legacy mode *config* selected, or ``None`` for the RFC 9421 arm.

    ``None`` is returned only when ``authentication`` is ABSENT, which is the default
    shape of every registration — so RFC 9421 is the default and legacy can never be
    a silent global fallback; it is reachable only when a buyer explicitly asked for
    it (security.mdx @ v3.1.1 :1424, and the research note on ``legacy_hmac_fallback``
    being a seller-level DECLARATION rather than a per-receiver switch).

    Case-insensitive by construction: ``authentication_type`` is persisted verbatim
    from the buyer's ``authentication.schemes[0]``, so ``"Bearer"`` and ``"bearer"``
    are the same registration and used to reach two different code paths.

    The retired second selector is ``webhook_secret``: it is read nowhere else after
    C1 and was never written by production, so honouring it would be the "signed two
    ways" shape :1425 forbids.
    """
    if config is None:
        return None
    scheme = (config.authentication_type or "").strip().lower()
    token = (config.authentication_token or "").strip()
    if not scheme and not token:
        return None
    if not token:
        return LEGACY_UNCREDENTIALED
    if scheme not in _HMAC_SCHEMES:
        return LEGACY_BEARER
    if len(token) < _MIN_HMAC_KEY_CHARS:
        # A short HMAC key is not a signature, it is a shared password. The
        # registration still selects the LEGACY arm (:1425 forbids answering it
        # with RFC 9421), so the honest outcome is an unauthenticated delivery
        # plus a loud log — the same posture the pre-C1 delivery service took.
        logger.warning(
            "Webhook receiver %s registered HMAC-SHA256 with a %d-character secret; "
            "at least %d are required, so this delivery goes out UNSIGNED",
            config.url,
            len(token),
            _MIN_HMAC_KEY_CHARS,
        )
        return LEGACY_UNCREDENTIALED
    return LEGACY_HMAC


class DeclaredAuth(NamedTuple):
    """A receiver's declared delivery authentication, normalized to ONE shape.

    The same fact is spelled six ways across this codebase — the ORM row
    (``authentication_type``/``authentication_token``), the AdCP request type
    (``authentication.schemes[0]`` + ``credentials``), the A2A protobuf's singular
    ``scheme``, the wire enum (``delivery_auth.mode``), the admin form's
    ``auth_type``/``auth_config``, and the string ``"None"`` sentinel MCP header ingest
    writes. Six spellings of one concept is how they end up disagreeing, and two of them
    already do.

    This is the normalized pair every derivation should start from. It is deliberately the
    INPUT half only: :func:`legacy_auth_mode` decides the DELIVERY arm from an ORM row,
    :func:`delivery_auth_mode` reports the wire enum, and neither reimplements the pluck.
    """

    #: The scheme the receiver named, verbatim (never case-folded — the wire enum is
    #: ``Bearer``/``HMAC-SHA256``, and folding here would lose the spelling we must echo).
    scheme: str | None
    #: The credential it supplied, or ``None`` for a scheme with no usable secret.
    credential: str | None


def declared_auth(authentication: Any) -> DeclaredAuth:
    """Normalize an ``authentication`` block, whichever shape it arrives in.

    Accepts a pydantic model (the AdCP request types), a plain dict (a
    ``step.request_data`` blob or raw transport params) or ``None``, because the four
    wire->row call sites read two of those and the challenge payload reads the third.
    A dual accessor here is the price of ONE derivation; four copies of the same
    three-line pluck — which is what exists today, two of them with a shape guard the
    other two lack — is the alternative, and the drift is already real.

    ``schemes`` is PLURAL: that is the field name on every AdCP type. The singular
    ``scheme`` spelling belongs to the A2A protobuf and is translated at that transport's
    own boundary; reading it here would put protobuf shape in the signing layer.
    """
    if authentication is None:
        return DeclaredAuth(scheme=None, credential=None)

    def _read(field: str) -> Any:
        if isinstance(authentication, Mapping):
            return authentication.get(field)
        return getattr(authentication, field, None)

    schemes = _read("schemes")
    if not isinstance(schemes, (list, tuple)):
        # A bare string here would ITERATE — ``"Bearer"`` yielding ``"B"`` — and the
        # derivation would report a mode nobody declared. The dict path is advertised for
        # callers reading raw params, so the shape it accepts has to be checked rather than
        # assumed; a non-list is treated as no declaration at all, which is the same answer
        # an absent ``authentication`` gets.
        schemes = []
    scheme = next((enum_value(s) for s in schemes if s), None)
    credential = _read("credentials")
    return DeclaredAuth(scheme=str(scheme) if scheme else None, credential=str(credential) if credential else None)


#: The wire value for "we will sign subsequent webhooks with RFC 9421", i.e. the mode a
#: receiver gets when it declares no ``authentication`` at all.
DELIVERY_AUTH_RFC9421 = "rfc9421"

#: The wire spellings of the two deprecated legacy modes, keyed by the normalized scheme.
#: ``webhook-challenge.json``'s ``delivery_auth.mode`` enum is closed
#: (``[rfc9421, Bearer, HMAC-SHA256]``), so an unrecognized scheme has to resolve to one of
#: these rather than be echoed verbatim.
_DELIVERY_AUTH_MODES: dict[bool, str] = {True: "HMAC-SHA256", False: "Bearer"}


def delivery_auth_mode(auth: DeclaredAuth) -> str:
    """The ``delivery_auth.mode`` a challenge reports for *auth* (#1291 C2).

    The REPORTING twin of :func:`legacy_auth_mode`, off the same
    :data:`_HMAC_SCHEMES` table so the mode we tell the receiver we will use and the arm
    :func:`build_webhook_sender` actually takes cannot disagree.

    Absent ``authentication`` is :data:`DELIVERY_AUTH_RFC9421`, matching
    ``legacy_auth_mode``'s ``None``. A present scheme is one of the two legacy values; an
    UNRECOGNIZED scheme reports ``Bearer``, which is the same answer
    ``legacy_auth_mode`` gives it (:data:`LEGACY_BEARER`) rather than a third outcome.
    """
    if auth.scheme is None:
        return DELIVERY_AUTH_RFC9421
    return _DELIVERY_AUTH_MODES[auth.scheme.strip().lower() in _HMAC_SCHEMES]


def credential_fingerprint(auth: DeclaredAuth) -> str | None:
    """The sha256 hex of *auth*'s credential, or ``None`` when there is none.

    ``webhook-challenge.json`` requires this for the legacy modes and FORBIDS it for
    ``rfc9421``, so the two are derived from the same pair: no scheme means no
    fingerprint, by construction rather than by a caller remembering the rule. It is a
    fingerprint and not the credential because the challenge body is a document the
    receiver may log — the receiver already knows its own secret and only needs to confirm
    we hold the same one.
    """
    if auth.credential is None:
        return None
    return hashlib.sha256(auth.credential.encode("utf-8")).hexdigest()


def legacy_hmac_fallback_supported() -> bool:
    """Whether this agent falls back to HMAC-SHA256 — ``webhook_signing.legacy_hmac_fallback``.

    v3.1.1 defines the field as whether this agent falls back to HMAC-SHA256 on the
    legacy ``push_notification_config.authentication`` paths. The SDK model DEFAULTS it
    to false, which for this deployment is a FALSE declaration: :func:`legacy_auth_mode`
    selects :data:`LEGACY_HMAC` for any registration naming a scheme in
    :data:`_HMAC_SCHEMES`, and :func:`build_webhook_sender` answers that mode with
    ``WebhookSender.from_adcp_legacy_hmac``. Both are unconditional.

    Derived from :data:`_HMAC_SCHEMES` — the same table the selector reads — rather than
    written as ``True`` on the capabilities wire, and owned HERE rather than in
    ``posture.py``, so it sits beside the arm it describes: emptying that table or
    deleting the arm (AdCP 4.0 removes legacy HMAC) makes the declaration follow.
    """
    return bool(_HMAC_SCHEMES)


def _log_legacy_registration(config: WebhookAuthConfig, mode: str) -> None:
    """An operator signal that OUR outbound sender picked a legacy mode for this receiver.

    NOT security.mdx :1464. That line binds the INBOUND direction — "every request that
    arrives with a non-empty ``authentication`` block" — and is discharged by the log in
    ``request_verifier_middleware.__call__``. This one fires when this agent BUILDS a sender,
    which is a different event on the delivery path; an earlier docstring cited :1464 here and
    read it as "every legacy registration", narrowing a per-request duty into a
    registration-time one.

    The inbound twin of this obligation is ``src/core/signing/operations.py``
    ``_authenticated_configs`` / ``_forces_signature``; the shared rule is "a
    non-empty ``authentication`` block opts this receiver out of RFC 9421".
    """
    logger.warning(
        "Webhook receiver %s opted into the LEGACY authentication scheme %r (mode=%s); "
        "RFC 9421 webhook signing is suppressed for it (security.mdx @ v3.1.1 :1424). "
        "Legacy HMAC-SHA256 is removed in AdCP 4.0.",
        config.url,
        config.authentication_type,
        mode,
    )


def _warn_once(warning_id: str, tenant_id: str | None) -> bool:
    """Claim the right to warn about *warning_id* for this tenant, once per process.

    True the first time a (warning, tenant) pair is seen and False afterwards, so each
    caller keeps its own message next to its own condition rather than routing every
    warning through one formatter.
    """
    key = (warning_id, tenant_id or "<unknown-tenant>")
    with _warn_lock:
        if key in _warned:
            return False
        _warned.add(key)
    return True


def reset_warning_state() -> None:
    """Forget every warning already emitted. For rotation tooling and test isolation.

    The seam this module previously only claimed to have: ``reset_keyless_warning_state``
    existed but no caller in ``src/`` or ``tests/`` invoked it, and the second cache had
    no reset at all. A process-level signing cache with no reset has already produced
    order-dependent failures in this layer.
    """
    with _warn_lock:
        _warned.clear()


def _warn_keyless_once(tenant_id: str | None) -> None:
    """WARN once per tenant per process that deliveries are going out unsigned."""
    if not _warn_once("keyless", tenant_id):
        return
    logger.warning(
        "Tenant %s has no ACTIVE signing key, so its outbound AdCP webhooks are delivered "
        "UNSIGNED. This is the honest posture only while webhook_signing.supported is false; "
        "provision a request-signing key to enable the RFC 9421 profile (#1291).",
        tenant_id or "<unknown-tenant>",
    )


def _unauthenticated_sender() -> WebhookSender:
    # ``client=None`` is the SDK's "you own the client" signal, and the only value
    # this module ever passes: it selects the ``_owns_client`` arm that resolves the
    # destination, validates it and pins the connection to the validated IP before
    # anything is serialized (see the module docstring).
    return WebhookSender._from_strategy(
        _UnauthenticatedStrategy(),
        key_id="unauthenticated",
        client=None,
        timeout_seconds=_TIMEOUT_SECONDS,
        allow_private_destinations=False,
        allowed_destination_ports=None,
    )


def _agent_origin(repo: SigningKeyRepository) -> str | None:
    """This tenant's canonical origin, read on the session *repo* already holds.

    ``canonical_agent_url`` (``src/core/agent_identity.py``) is the ONE agent-URL
    derivation — a second literal here is a ``request_signature_key_origin_mismatch``
    waiting to happen, because the verifier byte-matches the origin our keys resolved
    at against the one we published.

    ``None`` when there is no tenant row: unknown origin is not a publishable one, so
    the RFC 9421 arm closes. The read happens inside the repository's OWN transaction —
    the same one that produced the key row — which ``canonical_origin`` enforces by
    construction rather than by asking (#1757).
    """
    return repo.canonical_origin()


def webhook_delivery_signer(
    *,
    tenant_id: str | None,
    repo: SigningKeyRepository | None,
    now: datetime,
) -> JwkSignerStrategy | None:
    """The RFC 9421 strategy this tenant's DELIVERIES are signed with, or ``None``.

    The whole of the RFC 9421 arm's decision, with the delivery act removed. It was
    extracted out of :func:`_rfc9421_sender` (which now calls it) rather than restated
    beside it, because a second copy of "which key signs this tenant's webhooks" is
    exactly how one transport signs with a key another transport does not have.

    ``None`` means "deliver unsigned, honestly": a tenant with no active signing key,
    or a keyed one on an origin whose trust root cannot be published, has
    ``webhook_signing.supported=false`` in the capabilities a receiver reads, so a
    signature it could not resolve a key for is worse than no signature. That is a
    DECIDED posture, warned once per tenant per process, not a fallback taken because
    something failed — the caller gets ``None`` and delivers plain, and never sees a
    signer that quietly stopped signing.

    The posture read here is the SAME object ``get_adcp_capabilities`` serializes
    (#1291 D1), which is what makes the advertised ``webhook_signing.supported`` and
    this branch one decision rather than two. It therefore inherits the publishability
    gate: on an origin that cannot serve https there is no conformant
    ``identity.brand_json_url`` for a receiver to resolve our key through, so the arm is
    dropped. That removes an UNVERIFIABLE signature rather than withdrawing a capability.

    The algorithm about to go on the wire is still checked against that posture before
    the strategy is handed back. After D1 the check is unreachable by construction —
    both sides read one object — which is the point: it is the belt to the derivation's
    braces, and a future second derivation trips it instead of shipping.

    The return TYPE is the RFC 9421 oracle, exactly as on :func:`adcp_challenge_signer`:
    ``JwkSignerStrategy`` is the class behind ``WebhookSender.signs_with_rfc9421``, so a
    future edit cannot hand a caller a Bearer or legacy-HMAC strategy and still satisfy
    the annotation. That matters most to the caller this function exists for —
    :func:`src.core.security.webhook_egress.deliver_webhook`, whose RFC 9421 arm is
    selected by the ABSENCE of an ``authentication`` block (security.mdx @ v3.1.1 :1424)
    and which must therefore never be handed a legacy strategy to apply there (:1425
    forbids answering a legacy registration with an RFC 9421 signature, and the converse
    shape — a legacy strategy on the 9421 arm — would be the same confusion mirrored).

    It is deliberately NOT the same function as :func:`adcp_challenge_signer`. A
    challenge and a delivery select the same key by the same two calls
    (``webhook_signing_posture`` + ``resolve_signing_material``, both shared), but they
    are different obligations with different failure vocabularies: a challenge that
    cannot be signed means an activation WILL FAIL and gets its own warning domain,
    while an unsignable delivery goes out plain. Fusing them would give one of the two
    conditions the other's log line.
    """
    from adcp.webhook_auth import JwkSignerStrategy

    if repo is None or tenant_id is None:
        _warn_keyless_once(tenant_id)
        return None

    origin = _agent_origin(repo)
    posture = webhook_signing_posture(repo, now=now, origin=origin)
    if not posture.supported:
        _warn_keyless_once(tenant_id)
        return None

    material = resolve_signing_material(repo, tenant_id=tenant_id, now=now)
    declared = {enum_value(alg) for alg in posture.algorithms or ()}
    if material.alg not in declared:
        raise AdCPConfigurationError(
            f"Tenant {tenant_id!r} would sign outbound webhooks with alg {material.alg!r} while "
            f"declaring webhook_signing.algorithms={sorted(declared)}; a receiver validating the "
            "declaration against the wire would reject every delivery"
        )

    return JwkSignerStrategy(private_key=material.private_key, key_id=material.kid, alg=material.alg)


def delivery_signer_for_tenant(tenant_id: str | None, *, now: datetime | None = None) -> JwkSignerStrategy | None:
    """*tenant_id*'s RFC 9421 delivery strategy, resolved on a session closed BEFORE any dial.

    The open-read-close composition every sender on the egress seam (GH #1802) needs
    verbatim: own a signing session, consume it eagerly, close it, hand back primitives.
    It lives HERE, beside the decision it composes, because three senders —
    ``webhook_delivery_service``, ``order_approval_service`` and
    ``protocol_webhook_service`` — each wrote it independently and each left a docstring
    saying it belonged in one place. Three copies of "which session resolves which
    tenant's key" is how one transport signs with a key another transport does not have,
    which is the exact failure :func:`webhook_delivery_signer` exists to prevent one level
    down. ``signing_repo`` is defined below in this module and resolved at call time; it is
    named here rather than reimplemented so the session lifetime has one owner.

    **The session never spans a socket.** :func:`signing_repo` owns it (it accepts none
    from a caller) and :func:`webhook_delivery_signer` consumes it EAGERLY — origin,
    posture and key material are all read before it returns, and the strategy it hands
    back holds key material rather than a repository — so nothing lazy survives the
    ``with`` and no pooled connection is parked on a buyer's latency (#1757,
    salesagent-n78j0.4). Callers must therefore call this BEFORE the delivery call, never
    inside a context that also holds the connection.

    **No silent downgrade, and no ``try`` here.** ``None`` and a raise are two different
    answers and this function never converts one into the other:

    * ``None`` is a DECIDED posture, not a failure — no tenant/repository, no ACTIVE
      signing key, or a key on an origin whose trust root cannot be published. Such a
      tenant's capabilities already advertise ``webhook_signing.supported=false``, so its
      receivers have been told not to expect a ``Signature`` header and the delivery goes
      out plain on the legacy/unauthenticated arm.
    * anything else RAISES (notably ``AdCPConfigurationError``: the key's ``alg``
      contradicts the declared ``webhook_signing.algorithms``, which every receiver
      validating the declaration must reject). Catching that and passing ``signer=None``
      would turn a misconfiguration into an unsigned delivery to a receiver that IS
      verifying — the silent downgrade the seam exists to remove. The raise escapes before
      anything is serialized, so nothing is sent.

    What each caller does with that raise is deliberately NOT unified here, because the
    three senders genuinely differ and flattening them would change behaviour:
    ``protocol_webhook_service`` catches it at its own delivery boundary and books an
    ``unexpected`` outcome with zero attempts (delivery-log row plus audit warning);
    ``webhook_delivery_service`` lets it reach ``_send_webhook_enhanced``'s outermost
    handler; ``order_approval_service`` lets it propagate to the two polling-thread
    callers that already wrap their call. All three send nothing.

    Where *tenant_id* comes from also stays the caller's: the delivery service reads it off
    the DEQUEUED queue entry (so the key that signs is the one the item being delivered
    names), while the other two read it off the config row / task context they were handed.
    That is a different question from "which key signs this tenant's webhooks", and only the
    latter is shared.

    ``now`` defaults to :func:`datetime.now` in UTC — the value all three call sites passed
    — and is injectable for the same reason it is on :func:`adcp_webhook_sender`: key
    validity is a time-dependent decision and a caller pinning a clock must be able to.
    """
    with signing_repo(tenant_id) as repo:
        return webhook_delivery_signer(tenant_id=tenant_id, repo=repo, now=now or datetime.now(UTC))


def _rfc9421_sender(
    *,
    tenant_id: str | None,
    repo: SigningKeyRepository | None,
    now: datetime,
) -> WebhookSender:
    """The RFC 9421 arm: the tenant's own key, or an honest unsigned delivery.

    The decision itself is :func:`webhook_delivery_signer`; this function only binds
    its answer to an SDK sender. ``WebhookSender._from_strategy`` is the same internal
    constructor the public ``__init__`` uses — read at the pin, ``__init__`` builds
    exactly ``JwkSignerStrategy(private_key=…, key_id=…, alg=…)`` and then sets the
    identical seven attributes with ``allow_private_destinations=False``,
    ``allowed_destination_ports=None`` and ``transport_hooks=()`` — so routing through
    the strategy changes nothing on the wire and stops the key decision from existing
    in two places.
    """
    strategy = webhook_delivery_signer(tenant_id=tenant_id, repo=repo, now=now)
    if strategy is None:
        return _unauthenticated_sender()

    return WebhookSender._from_strategy(
        strategy,
        key_id=strategy.key_id,
        client=None,
        timeout_seconds=_TIMEOUT_SECONDS,
        allow_private_destinations=False,
        allowed_destination_ports=None,
    )


def build_webhook_sender(
    *,
    config: WebhookAuthConfig | None,
    tenant_id: str | None,
    repo: SigningKeyRepository | None,
    now: datetime,
) -> WebhookSender:
    """The sender *config*'s receiver has earned — exactly one authentication mode.

    Every arm leaves the client to the SDK. There is deliberately no ``client``
    parameter to pass one in: an operator-supplied client SKIPS the SDK's own
    destination check (``adcp/webhooks.py`` ``:1604``, ``:1727``), so the parameter
    was the single way to reach an unpinned delivery from here. Removing it makes
    that unrepresentable rather than merely unused — see the module docstring. No
    socket is opened by construction either way, which is what callers grading only
    ``signs_with_rfc9421`` rely on.
    """
    mode = legacy_auth_mode(config)
    if mode is not None:
        assert config is not None  # legacy_auth_mode returns None for a missing config
        _log_legacy_registration(config, mode)
        if mode == LEGACY_HMAC:
            return WebhookSender.from_adcp_legacy_hmac(
                (config.authentication_token or "").encode("utf-8"),
                key_id=_LEGACY_HMAC_KEY_ID,
                client=None,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
        if mode == LEGACY_BEARER:
            return WebhookSender.from_bearer_token(
                config.authentication_token or "",
                client=None,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
        return _unauthenticated_sender()

    return _rfc9421_sender(tenant_id=tenant_id, repo=repo, now=now)


def adcp_challenge_signer(*, tenant_id: str, repo: SigningKeyRepository, now: datetime) -> JwkSignerStrategy | None:
    """The RFC 9421 strategy for a proof-of-control challenge, or ``None`` if we cannot sign.

    #1291 C2. A challenge is not a delivery: it is an assertion of THIS seller's identity
    that the receiver must verify before echoing, so it needs the signing decision without
    the delivery act. Three things make the delivery entry points unusable for it, all
    structural rather than stylistic:

    * ``send_raw`` INJECTS ``idempotency_key`` into the body before signing, and
      ``webhook-challenge.json`` is ``additionalProperties: false`` with exactly seven
      allowed properties — so a delivery-shaped send produces a body every conformant
      receiver must reject. The SDK agrees: its own ``send_webhook_challenge`` exists
      precisely because it does not inject one.
    * the SDK's challenge helpers emit FOUR of the seven required fields and accept no
      arguments for the other three, so they are locked out of a conformant body
      (upstream gap; the caller builds the payload from the SDK TYPE instead).
    * ``adcp_webhook_sender`` always hands the sender a client, and the SDK's challenge
      path refuses a sender that does not own its own client.

    **There is deliberately NO ``config`` parameter.** ``sync_accounts.mdx`` @ v3.1.1 :207
    is explicit that the challenge "MUST be signed with the seller's RFC 9421 webhook
    profile key EVEN WHEN the candidate config selects legacy delivery auth". Threading the
    candidate registration in here — the shape :func:`build_webhook_sender` takes for a
    DELIVERY, where :1425 forbids the opposite — would silently downgrade the challenge to
    Bearer or HMAC and break that MUST. The candidate's authentication belongs in the
    challenge as DATA (``delivery_auth``), never as the signing mode. It is also
    structurally unavailable: at proof time the subscriber is not persisted, and
    :func:`legacy_auth_mode` reads an ORM row.

    ``None`` means "this tenant cannot sign", which the caller must turn into "not proven".
    The return TYPE is the RFC 9421 oracle: ``JwkSignerStrategy`` is the exact class behind
    ``WebhookSender.signs_with_rfc9421``, so a future edit cannot hand back an
    unauthenticated strategy and still satisfy the annotation.

    Reuses :func:`webhook_signing_posture` (the ONE key-presence derivation, which since
    #1291 D1 also carries the trust-root publishability gate) and
    ``resolve_signing_material`` — the same two calls :func:`webhook_delivery_signer`
    makes, so key selection cannot diverge between a challenge and the deliveries that
    follow it.
    """
    from adcp.webhook_auth import JwkSignerStrategy

    if not webhook_signing_posture(repo, now=now, origin=_agent_origin(repo)).supported:
        _warn_unsignable_challenge(tenant_id)
        return None

    material = resolve_signing_material(repo, tenant_id=tenant_id, now=now)
    return JwkSignerStrategy(private_key=material.private_key, key_id=material.kid, alg=material.alg)


@dataclass(frozen=True, slots=True)
class ChallengeAnswer:
    """What a proof-of-control challenge came back with: a status and the bytes.

    The seam answers with :class:`~src.core.security.egress.response.OutboundResult`,
    which spells the status ``http_status`` and carries four more fields the proof
    decision has no business reading. ``notification_proof_service`` declares the two
    members it DOES read as a structural protocol (``status_code`` / ``content``)
    precisely so it holds no transport type of its own, so this is the projection onto
    that shape — the same move
    :class:`~src.core.security.outbound_http.WrappedFailure` makes one layer down, and
    for the same reason: a type crossing a boundary is how an httpx object reaches a
    module the egress ban forbids importing httpx into.
    """

    status_code: int
    content: bytes


async def send_signed_challenge(
    *,
    url: str,
    body: bytes,
    strategy: JwkSignerStrategy,
    timeout_seconds: float,
) -> ChallengeAnswer:
    """Sign *body* and POST it — the ONE place a proof-of-control challenge leaves (#1291 C2).

    The sign and the POST are one function because no PUBLIC SDK path can send a conformant
    AdCP challenge, read from the installed ``adcp==6.6.0`` rather than inferred:

    * ``WebhookSender.send_raw`` does ``body_dict = {**payload, "idempotency_key": …}``
      BEFORE signing, and ``webhook-challenge.json`` is ``additionalProperties: false`` with
      exactly seven allowed properties — so a delivery-shaped send produces a document every
      conformant receiver must reject;
    * ``WebhookSender.resend()`` raises ``ValueError("cannot resend: result has no captured
      sent_body …")`` — the SDK author anticipated a fabricated result and refused it;
    * ``_send_bytes``, the only method that posts caller-supplied bytes without injection, is
      private;
    * the three challenge helpers emit four of the seven required fields and accept no
      argument for ``seller_agent_url``, ``delivery_auth`` or ``event_types``.

    Living HERE rather than in the calling service is what leaves that service with no raw
    POST at all, so the outbound-sender boundary guard has one fewer allowlisted exception
    rather than a renamed one.

    ``timeout_seconds`` is a PARAMETER, not :data:`_TIMEOUT_SECONDS`. The module default of
    10.0s is right for a background delivery and wrong for a handshake inside the request
    cycle, where the buyer's latency budget is the constraint — the caller passes its own
    ceiling and the difference stays visible at the call site.

    ``Content-Type`` is load-bearing rather than decoration: ``JwkSignerStrategy`` builds its
    signature base from ``headers={"Content-Type": "application/json"}`` and covers the
    ``content-type`` component whenever that header is present, while a webhook verifier
    REJECTS a signature whose covered components omit it (``security.mdx`` @ v3.1.1 :1476,
    ``webhook_signature_components_incomplete``). The seam's ``content=`` path sets no
    Content-Type of its own, so it ships explicitly or the signature covers a header that
    never left.

    ``content=`` and never ``json=``: ``json=`` would re-encode the payload and the signature
    would cover bytes that never went on the wire (#1441's defect class). The caller
    serializes once and hands those exact bytes here.

    **Destination policy is the seam's** (GH #1802, GH #1890). This used to open a bare
    ``AsyncClient`` of its own, so the destination was validated ONCE at the caller's fire time
    and never again when the socket opened — the TOCTOU the module docstring named, plus no
    redirect refusal, no port allowlist, no ``trust_env=False`` and no body cap.
    :func:`~src.core.security.outbound_http.asend` makes all six the same decision every
    other outbound call in this application makes: it resolves the host ONCE inside
    ``EgressPolicy.resolve_for_dial`` and pins the connection to that address, so there is
    no second resolution left to disagree with the first. ``CounterpartyUrl`` marks the
    provenance — the URL came off a buyer's registration — with no ``field``, because this
    module is handed a URL and never the request document a locator would point into.

    The signature is applied through the seam's per-attempt ``sign=`` hook rather than
    precomputed here. That is what keeps this a SIGNED dial without a client of its own:
    the hook fires inside ``asend`` after ``client.build_request``, over
    ``request.content`` — the exact bytes httpx will transmit, which are ``body`` — and over
    the post-normalization ``request.url``, so signed bytes and wire bytes are one object
    rather than two that agree. Each attempt gets its own call and therefore its own RFC
    9421 ``nonce``, which is why the hook exists at all.

    ``max_attempts=1``: a challenge is a handshake inside the request cycle, budgeted by the
    caller's 2.0s ceiling, and it was exactly one POST before this moved onto the seam.
    BR-RULE-029's 1s/2s backoff between three attempts would blow that budget several times
    over for a subscriber that is not going to answer.

    There is NO silent downgrade. ``strategy`` is required and non-optional, so an
    unsignable challenge cannot reach here at all — :func:`adcp_challenge_signer` returns
    ``None`` and the caller turns that into "not proven" without dialling. A signer that
    raises mid-attempt escapes ``asend`` (it is not in the retryable set), and a refused
    destination raises ``OutboundRequestBlocked`` from ``resolve_for_dial`` before any
    request is built — so on both paths nothing is sent, rather than something being sent
    unsigned.

    A non-2xx answer is projected back onto :class:`ChallengeAnswer` rather than allowed to
    escape as ``OutboundDeliveryFailed``, so the caller keeps grading the status itself and
    still logs *which* status the endpoint answered. Its ``content`` is empty on that path
    and honestly so: the seam surfaces no body for an undelivered request (AdCP 3.1.1
    ``security.mdx`` point 6 — nothing derived from the origin's response rides out on a
    failure), and the echo check never reads it, because a non-2xx has already failed the
    2xx gate that precedes it. A transport failure has no status to project and is
    re-raised unchanged.
    """
    try:
        result = await asend(
            url,
            method="POST",
            content=body,
            headers={"Content-Type": "application/json"},
            timeout=timeout_seconds,
            max_attempts=1,
            provenance=CounterpartyUrl(field=None),
            sign=strategy.build_auth_headers,
        )
    except OutboundDeliveryFailed as exc:
        if exc.http_status is None:
            raise
        return ChallengeAnswer(status_code=exc.http_status, content=b"")
    return ChallengeAnswer(status_code=result.http_status, content=result.content)


def _warn_unsignable_challenge(tenant_id: str) -> None:
    """WARN once that this tenant cannot prove endpoint control, and how to fix it.

    Names the provisioning path, because "no signing key" is an operator action and not a
    dead end — an activation that fails with no actionable log is the quiet failure this
    project bans even when the OUTCOME is correct.

    Its own suppression domain, distinct from the keyless-delivery warning: this condition
    means an activation WILL FAIL, which an operator needs to hear even after already being
    told that deliveries go out unsigned.
    """
    if not _warn_once("unsignable-challenge", tenant_id):
        return
    logger.warning(
        "Tenant %s cannot sign a notification proof-of-control challenge: it has no ACTIVE "
        "signing key this deployment can open on an https origin it can publish a trust root "
        "from. Activating a notification subscriber will fail until one is provisioned — see "
        "scripts/ops/provision_signing_key.py or the admin signing-keys route (#1291).",
        tenant_id,
    )


@contextmanager
def signing_repo(tenant_id: str | None) -> Iterator[SigningKeyRepository | None]:
    """The tenant-scoped signing repository, on a session THIS function owns.

    It always opens its own and takes none from a caller. A ``repo=`` parameter used to
    let a caller donate one built on ITS session, which is how the webhook delivery loop
    came to hold a pooled connection across ``time.sleep`` and a POST to a buyer-supplied
    URL: the connection's lifetime belonged to whoever called, not to the work.

    Removing the parameter makes that UNREPRESENTABLE rather than merely discouraged — a
    caller cannot donate a lifetime it has no way to pass (#1757, salesagent-n78j0.4).
    The session opened here lives for the key read and closes with the block, so it is
    never held across a delivery.
    """
    if tenant_id is None:
        yield None
        return

    from src.core.database.database_session import get_db_session
    from src.core.database.repositories.signing_key import SigningKeyRepository

    with get_db_session() as session:
        yield SigningKeyRepository(session, tenant_id)


@asynccontextmanager
async def adcp_webhook_sender(
    *,
    config: WebhookAuthConfig | None,
    tenant_id: str | None,
    now: datetime | None = None,
) -> AsyncIterator[WebhookSender]:
    """A configured sender bound to the SDK's own pinned client.

    There is no ``client`` parameter, and that is a destination-policy decision rather
    than a missing convenience. ``adcp/webhooks.py`` branches on ``_owns_client``: an
    operator-supplied client is trusted completely and SKIPS the SDK's SSRF check
    (``:1604``, ``:1727``), while the owned-client path (``:1636``, ``:1715``) resolves
    the URL, validates it against ``resolve_and_validate_host``, and PINS the connection
    to the validated IP before anything is serialized. Passing a plain client bought
    nothing but the loss of that check — the destination went unvalidated at delivery
    time, with only a caller's fire-time check and the TOCTOU between the two
    resolutions — so the way to pass one is gone (GH #1802, GH #1890).

    The receivers this reaches are buyer-supplied, so the pinned path is the one they
    should get. ``allow_private_destinations`` stays at the SDK default of ``False``.
    Measured before adopting: the e2e stack's own compose subnet
    (``E2E_NETWORK_SUBNET``, default ``192.88.99.0/26``) is accepted by every flag the
    SDK classifier tests — private, loopback, link-local, multicast, reserved — which
    is what that subnet was chosen for. Docker's default bridge (``172.17/16``) and
    RFC 1918 are refused, as they should be.
    """
    # The ``yield`` is OUTSIDE the block on purpose, and moving it back inside restores a
    # real defect: a generator suspended at a ``yield`` holds every context it entered, so
    # yielding from in here checks the session out for the whole of the caller's ``async
    # with`` body — whose one statement is the POST (:741). That is the delivery
    # ``signing_repo``'s own docstring says its session is never held across. Safe because
    # ``build_webhook_sender`` consumes the repository EAGERLY on every arm: the RFC 9421
    # arm reads origin, posture and key material before returning, and the sender it hands
    # back holds primitives, so nothing lazy survives the close (#1757).
    with signing_repo(tenant_id) as repo:
        sender = build_webhook_sender(
            config=config,
            tenant_id=tenant_id,
            repo=repo,
            now=now or datetime.now(UTC),
        )
    yield sender


async def deliver_adcp_webhook(
    *,
    url: str,
    payload: dict[str, Any],
    idempotency_key: str,
    config: WebhookAuthConfig | None,
    tenant_id: str | None,
    now: datetime | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> WebhookDeliveryResult:
    """Serialize, authenticate and POST one AdCP webhook — the single delivery act.

    ``idempotency_key`` is generated ONCE PER EVENT by the caller and reused across
    its retries; the SDK injects it into the signed body, so a fresh key per attempt
    would defeat receiver-side dedup.

    The SDK owns the client, so the POST goes out over its IP-pinned transport — see
    :func:`adcp_webhook_sender` for why there is no way to hand one in.
    """
    async with adcp_webhook_sender(config=config, tenant_id=tenant_id, now=now) as sender:
        return await sender.send_raw(
            url=url,
            idempotency_key=idempotency_key,
            payload=payload,
            extra_headers=extra_headers,
        )


def deliver_adcp_webhook_sync(
    *,
    url: str,
    payload: dict[str, Any],
    idempotency_key: str,
    config: WebhookAuthConfig | None,
    tenant_id: str | None,
    now: datetime | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> WebhookDeliveryResult:
    """:func:`deliver_adcp_webhook` for the two senders that are still synchronous.

    ``run_async_in_sync_context`` is the codebase's existing sync->async hop, NOT a
    second one invented here. Using it adds two call sites to a helper the owner has
    recorded as a band-aid for the synchronous-adapter architecture
    (``.claude/notes/async-sync-architecture.md``) — named debt, not silent debt: the
    real fix is moving webhook delivery onto the background worker.
    """
    from src.core.validation_helpers import run_async_in_sync_context

    return run_async_in_sync_context(
        deliver_adcp_webhook(
            url=url,
            payload=payload,
            idempotency_key=idempotency_key,
            config=config,
            tenant_id=tenant_id,
            now=now,
            extra_headers=extra_headers,
        )
    )
