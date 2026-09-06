"""Base test environment for _impl function testing.

Unified base for both integration and unit test environments:

- **Integration mode** (``use_real_db = True``): Creates a non-scoped SQLAlchemy
  session, binds factory_boy factories, only mocks external services.
  Requires ``integration_db`` pytest fixture.
- **Unit mode** (``use_real_db = False``): No database setup, patches all
  dependencies including DB.

Subclasses override:
    EXTERNAL_PATCHES: dict[str, str]   -- {name: patch_target} for mocks
    _configure_mocks(): None           -- wire mock defaults
    call_impl(**kwargs): Any           -- call production function

Multi-transport support (subclasses may also override):
    call_a2a(**kwargs): Any            -- dispatch through the A2A handler
    REST_ENDPOINT: str                 -- POST endpoint path for REST dispatch
    build_rest_body(**kwargs): dict    -- convert kwargs to REST body
    parse_rest_response(data): model  -- parse JSON dict to Pydantic model
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import AsyncMock, MagicMock, patch

from tests.harness._realize import e2e_unsupported, realize_e2e

# The MCP transport boots the real FastMCP app lifespan, which starts the
# background schedulers. Those run a batch immediately on the *real* wall clock
# and rewrite media-buy status rows — silently mutating data a test just seeded
# (e.g. promoting a seeded pending_start buy to active). Suppress them for all
# harness-driven tests; setdefault so an explicit override still wins.
# (src.core.main._background_schedulers_enabled reads this at lifespan runtime.)
os.environ.setdefault("ADCP_RUN_BACKGROUND_SCHEDULERS", "false")

# RUNTIME imports, not TYPE_CHECKING ones. json_safe does isinstance() checks against
# these at call time, and DeliverResult is CONSTRUCTED here (the dispatch return
# contract) -- a TYPE_CHECKING-only import would be a NameError, not a type-checker
# convenience.
from datetime import date, datetime  # noqa: E402
from decimal import Decimal  # noqa: E402
from enum import Enum  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from tests.factories.account import DEFAULT_TEST_ACCOUNT_ID  # noqa: E402  (re-export)
from tests.harness.transport import DeliverResult  # noqa: E402

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.core.resolved_identity import ResolvedIdentity
    from tests.harness.transport import E2EConfig, Transport, TransportResult


def json_safe(value: Any) -> Any:
    """Recursively convert pydantic models into the JSON forms a wire body carries.

    A REST body is JSON. When a step dispatches a RAW parameter bag rather than a built
    request -- which is what lets a schema-invalid payload actually reach the transport and
    be graded on the wire -- that bag can hold typed objects a scenario constructed for
    setup (an AccountReference, a Budget). ``req.model_dump(mode="json")`` used to convert
    them on the way out; the raw path has to do the same or serialization fails with
    "Object of type X is not JSON serializable" and the scenario grades a TypeError instead
    of the server's answer.

    Leaves everything else untouched, so a deliberately-malformed value still reaches the
    wire malformed -- which is the entire point of dispatching raw.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, Enum):
        return value.value
    # datetime/date/Decimal are what model_dump(mode="json") converts and a raw bag does
    # not: a step that stashed a real datetime for setup would otherwise reach the wire as
    # a Python object and be rejected for the WRONG reason -- the scenario would grade a
    # serialization artefact instead of the server's answer.
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(v) for v in value]
    return value


class WireError(Exception):
    """A transport failure carrying the envelope the buyer received, VERBATIM.

    Deliberately NOT an ``AdCPSalesAgentError`` subclass. The harness used to rebuild the
    matching production exception from wire bytes so a test could write
    ``pytest.raises(AdCPNotFoundError)`` through a transport; that map covered 20 of
    43 classes, was silent about the other 23, and its own docstring conceded the
    reconstruction was lossy. Grading OUR class hierarchy through a lossy copy of
    production's constructor is not the same as grading the buyer's contract.

    This type carries no code-to-class knowledge at all. It exists so a failed wire
    dispatch can still raise -- callers up the stack expect an exception -- while the
    thing being asserted stays the envelope, reachable as ``.envelope`` and published
    by the dispatchers as ``TransportResult.wire_error_envelope``.
    """

    def __init__(self, envelope: dict) -> None:
        self.envelope = envelope
        errors = envelope.get("errors") or [{}]
        code = errors[0].get("code") if isinstance(errors[0], dict) else None
        super().__init__(f"wire error {code or '(no code)'}")


def _mcp_wire_envelope(exc: Exception) -> dict | None:
    """The two-layer envelope inside a FastMCP ``ToolError``, or ``None``.

    The MCP boundary translator raises ``AdCPToolError`` (single-arg JSON envelope)
    so FastMCP serializes ``str(exc)`` as the JSON-encoded envelope. This parses that
    JSON and RETURNS IT. It does not rebuild an exception: the envelope is what the
    buyer received, and it already carries code, message, recovery, suggestion, field
    and details.

    Falls back to the legacy tuple-string shape for any plain ``ToolError`` raised
    outside the boundary translator, and finally to ``extract_error_info`` for the
    single-arg ``ToolError("message")`` form.
    """
    import ast as _ast
    import json

    from fastmcp.exceptions import ToolError

    if not isinstance(exc, ToolError):
        return None

    error_str = str(exc)

    try:
        parsed = json.loads(error_str)
        if isinstance(parsed, dict):
            envelope = _wire_envelope(parsed)
            if envelope is not None:
                return envelope
    except (json.JSONDecodeError, TypeError):
        pass

    # Legacy shape (test fixtures that mock ToolError directly):
    # tuple-stringified `('CODE', 'message', 'recovery', '{"details": ...}')`.
    try:
        tup = _ast.literal_eval(error_str)
        if isinstance(tup, tuple) and len(tup) >= 2:
            entry: dict = {"code": str(tup[0])}
            if len(tup) > 3 and tup[3] is not None:
                try:
                    extra = json.loads(str(tup[3]))
                    if isinstance(extra, dict):
                        if extra.get("details") is not None:
                            entry["details"] = extra["details"]
                        if extra.get("field") is not None:
                            entry["field"] = extra["field"]
                except (json.JSONDecodeError, TypeError):
                    pass
            return {"adcp_error": dict(entry), "errors": [entry]}
    except (ValueError, SyntaxError):
        pass

    from src.core.tool_error_logging import extract_error_info

    error_code, _message, _recovery = extract_error_info(exc)
    if error_code != "TOOL_ERROR":
        entry = {"code": error_code}
        return {"adcp_error": dict(entry), "errors": [entry]}

    return None


def _wire_envelope(envelope: dict) -> dict | None:
    """Normalise a captured error body into the two-layer envelope shape, or ``None``.

    Accepts what ``build_two_layer_error_envelope`` produces
    (``{"adcp_error": {...}, "errors": [...]}``) and the legacy flat shape
    (``{"error_code": ..., "recovery": ...}``), and RETURNS THE ENVELOPE.

    It used to return a reconstructed ``AdCPSalesAgentError`` built from those bytes, with a
    hand-maintained code-to-class map. That map covered 20 of 43 classes and was
    silent about the rest, so type identity was already lost for most codes; its own
    docstring conceded the reconstruction was "lossy by construction"; and it was the
    only place outside production that called an ``AdCPSalesAgentError`` constructor, which made
    it the only place that could drift from a signature change -- and it did, twice,
    the second time costing 469 tests.

    Arming a fault still needs a real typed exception; the adapter genuinely raises
    one. ASSERTING an outcome never does: the envelope IS what the buyer received.
    """
    if not isinstance(envelope, dict):
        return None
    if isinstance(envelope.get("errors"), list) and envelope["errors"]:
        return envelope
    if isinstance(envelope.get("adcp_error"), dict):
        entry = dict(envelope["adcp_error"])
        return {**envelope, "errors": [entry]}
    # Legacy flat shape from tests that predate the envelope.
    code = envelope.get("error_code") or envelope.get("code")
    if not code:
        return None
    entry = {"code": code}
    for key in ("message", "recovery", "suggestion", "field", "details"):
        if envelope.get(key) is not None:
            entry[key] = envelope[key]
    return {"adcp_error": dict(entry), "errors": [entry]}


def _a2a_wire_envelope(exc: Exception) -> dict | None:
    """The two-layer envelope inside an a2a ``A2AError``'s ``data``, or ``None``.

    The A2A dispatcher wraps an ``AdCPSalesAgentError`` into a failed Task whose artifact
    carries the envelope; a JSON-RPC-level ``A2AError`` carries it in ``data``.

    Returns the ENVELOPE. The three-way fallback ladder that used to sit here --
    ``InvalidRequestError`` -> AdCPAuthenticationError, ``InvalidParamsError`` ->
    AdCPValidationError, ``InternalError`` -> RuntimeError -- is gone with it: those
    were hand-maintained guesses at what the wire meant, and a guess is not evidence
    of what the buyer received.
    """
    from a2a.utils.errors import A2AError

    if not isinstance(exc, A2AError):
        return None
    data = getattr(exc, "data", None)
    return _wire_envelope(data) if isinstance(data, dict) else None


def _a2a_send_message_configuration(spec: dict[str, Any]) -> Any:
    """Build the A2A ``SendMessageConfiguration`` carrying a protocol-level push config.

    ``message/send`` registers a webhook one level ABOVE the AdCP tool
    parameters: ``params.configuration.task_push_notification_config``
    (``src/a2a_server/adcp_a2a_server.py`` — ``on_message_send`` reads it before
    any skill routing happens). It is therefore not reachable by putting a
    ``push_notification_config`` in the skill parameters, and it exists on no
    other transport — MCP and REST have no equivalent protocol envelope.

    *spec* is the plain dict a step writes (``{"url": ..., "authentication":
    {"scheme": ..., "credentials": ...}}``). Note the SINGULAR ``scheme``: the
    A2A wire type is the protobuf ``AuthenticationInfo``, not the AdCP
    ``Authentication`` object with its ``schemes`` array. Absent credentials are
    sent as the protobuf default (empty string) rather than omitted, because
    that is what a buyer's client actually puts on the wire for an unset
    protobuf string — the field cannot be "missing" in proto3.
    """
    from a2a.types import AuthenticationInfo, SendMessageConfiguration, TaskPushNotificationConfig

    fields: dict[str, Any] = {"url": spec["url"]}
    authentication = spec.get("authentication")
    if authentication is not None:
        fields["authentication"] = AuthenticationInfo(
            scheme=authentication.get("scheme") or "",
            credentials=authentication.get("credentials") or "",
        )
    return SendMessageConfiguration(task_push_notification_config=TaskPushNotificationConfig(**fields))


class _TestClock:
    """Minimal clock for BDD relative date-token resolution.

    The media-buy Given steps resolve Gherkin tokens (``{now}``,
    ``{30 days from now}``, ``{1 day ago}``) against ``ctx["env"].clock`` using
    the ``now_iso`` / ``future_iso`` / ``past_iso`` interface. Emits the
    ``YYYY-MM-DDTHH:MM:SSZ`` shape AdCP request validators accept.
    """

    @staticmethod
    def _iso(dt: Any) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def now_iso(self) -> str:
        from datetime import UTC, datetime

        return self._iso(datetime.now(UTC))

    def future_iso(self, days: int) -> str:
        from datetime import UTC, datetime, timedelta

        return self._iso(datetime.now(UTC) + timedelta(days=days))

    def past_iso(self, days: int) -> str:
        from datetime import UTC, datetime, timedelta

        return self._iso(datetime.now(UTC) - timedelta(days=days))


class BaseTestEnv:
    """Base test environment for _impl function testing.

    Subclasses define:
        EXTERNAL_PATCHES: dict[str, str]   -- {name: patch_target}
        _configure_mocks(): None           -- wire mock defaults
        call_impl(**kwargs): Any           -- call production function

    Set ``use_real_db = True`` in integration subclasses to enable
    factory_boy session binding.

    Usage (integration)::

        @pytest.mark.requires_db
        def test_something(self, integration_db):
            with DeliveryPollEnv() as env:
                tenant = TenantFactory(tenant_id="t1")
                response = env.call_impl(media_buy_ids=["mb_001"])

    Usage (unit)::

        with DeliveryPollEnvUnit() as env:
            env.add_buy(media_buy_id="mb_001")
            response = env.call_impl(media_buy_ids=["mb_001"])

    Usage (multi-transport)::

        @pytest.mark.parametrize("transport", [Transport.A2A, Transport.MCP, Transport.REST])
        def test_something(self, integration_db, transport):
            with CreativeSyncEnv() as env:
                result = env.call_via(transport, creatives=[...])
                assert result.is_success

    Attributes:
        mock: dict[str, MagicMock]  -- active mocks keyed by short name
        identity: ResolvedIdentity  -- default identity (override via constructor)
    """

    EXTERNAL_PATCHES: dict[str, str] = {}
    ASYNC_PATCHES: set[str] = set()  # Names that need AsyncMock (for async functions)
    MODULE: str = ""  # Convenience for unit envs building patch paths
    REST_ENDPOINT: str = ""  # Override in subclass for REST dispatch
    # The tool/skill this env dispatches. Declaring these is what lets the base
    # own call_mcp/call_a2a instead of every env re-implementing the same
    # one-line delegation. REST_METHOD's de-facto
    # contract lives at dispatchers.py's getattr(env, "REST_METHOD", "post").
    MCP_TOOL: str = ""
    A2A_SKILL: str = ""
    # The parser the base delegation feeds wire dicts to. Declared per env
    # because envs parse into their LOCAL response subclass, which is not always
    # the tool's pinned SDK model — defaulting to the pinned model would quietly
    # change what call_mcp/call_a2a return for every converted env. Envs that
    # select a parser from request CONTENT override response_parser() instead.
    RESPONSE_MODEL: Any = None
    use_real_db: bool = False

    def __init__(
        self,
        principal_id: str = "test_principal",
        tenant_id: str = "test_tenant",
        dry_run: bool = False,
        database_url: str | None = None,
        e2e_config: E2EConfig | None = None,
        **tenant_overrides: Any,
    ) -> None:
        self._principal_id = principal_id
        self._tenant_id = tenant_id
        self._dry_run = dry_run
        # E2E mode: bind factories to the live server's DB so the HTTP-reached
        # server sees Given-step data. Explicit database_url wins; else the
        # e2e_config's postgres_url. None => normal cached/integration engine.
        self._database_url = database_url or (e2e_config.postgres_url if e2e_config else None)
        self.e2e_config: E2EConfig | None = e2e_config
        self._e2e_engine: Any = None
        self._tenant_overrides = tenant_overrides
        self.mock: dict[str, MagicMock] = {}
        self._enter_cleanups: list[tuple[str, Callable[[], None]]] = []
        self._session: Session | None = None
        self._identity_cache: dict[str, ResolvedIdentity] = {}
        self._rest_client: Any = None  # Lazy-created TestClient
        self.clock = _TestClock()  # BDD steps may use env.clock for date tokens
        # Raw A2A Task returned by the last _run_a2a_handler call. The submitted
        # (manual-approval) contract lives on the Task itself — state=SUBMITTED
        # with NO artifacts — and the synthesized submitted wire above cannot
        # prove artifact absence, so guards assert on this captured Task.
        self._last_a2a_task: Any = None

    # -- Transport mode -----------------------------------------------------

    @property
    def is_e2e(self) -> bool:
        """True when this env dispatches over the live HTTP server (e2e mode).

        Keys on ``e2e_config`` — the same signal ``conftest`` uses to thread the
        live-stack config and ``RestE2EDispatcher`` uses to select HTTP
        dispatch. A bare ``database_url`` rebinds factories to another DB but is
        NOT e2e mode (no server-surface realization needed). Mock-setup methods
        dispatch on this via :func:`tests.harness._realize.realize_e2e`.
        """
        return self.e2e_config is not None

    @realize_e2e(
        e2e_unsupported(
            "no server fault-injection surface for a genuinely untyped exception on a live "
            "remote process (same structural limitation prkv.8's own e2e-verify atom hit)"
        )
    )
    def inject_untyped_exception(self, exception: Exception) -> None:
        """Make the skill's business logic raise *exception* directly (prkv.18).

        Substitutes the implementation at its REGISTRY ROW, so every transport reaches the
        raising stand-in. It used to patch a dotted path to the ``_impl`` function, declared
        per env as ``IMPL_TARGET``; that stopped working the day the transports began
        dispatching through ``TOOLS``, because the row holds the function OBJECT and a
        module attribute is no longer what anything calls. The env already names its tool
        (``MCP_TOOL``), so the second declaration is gone with the mechanism that needed it.

        Registers the patcher with the same ``_guard`` cleanup registry ``EXTERNAL_PATCHES``
        uses, so both release paths (a normal ``__exit__`` and a failed ``__enter__``) stop
        it and this needs no new cleanup path.

        Skill-agnostic by design: any env that declares ``MCP_TOOL`` gets this capability for
        free, rather than each domain mixin hand-rolling its own untyped-exception injector.

        For a genuinely untyped exception, the REST boundary's catch-all
        handler is reachable only through Starlette's ``ServerErrorMiddleware``
        (see ``prkv.8``), which always re-raises after building its response —
        the default ``TestClient(app)`` (``raise_server_exceptions=True``)
        would surface that re-raise as a test error instead of the wire
        response. Setting the INSTANCE attribute here (not a class-level
        default on ``IntegrationEnv``) scopes the opt-out to exactly this
        call, on this env instance — ``get_rest_client()`` is lazy, so a
        Given-time set is honored at dispatch time.
        """
        from dataclasses import replace

        from src.core.tools.registry import _TOOLS

        if not self.MCP_TOOL:
            raise ValueError(
                f"{type(self).__name__} declares no MCP_TOOL — set it to the tool's registry "
                "name before calling inject_untyped_exception()"
            )
        raising = AsyncMock(side_effect=exception)
        patcher = patch.dict(_TOOLS, {self.MCP_TOOL: replace(_TOOLS[self.MCP_TOOL], impl=raising)})
        patcher.start()
        self.mock["_untyped_exception"] = raising
        self._guard("patch:_untyped_exception", patcher.stop)
        self.REST_RAISE_SERVER_EXCEPTIONS = False

    # -- Identity (one function, all transports) ----------------------------

    def identity_for(self, transport: Transport) -> ResolvedIdentity:
        """Build ResolvedIdentity with the correct protocol for *transport*.

        This is the single source of truth for test identity across all
        transports. The identity is cached per protocol so repeated calls
        with the same transport return the same object.

        In integration mode (``use_real_db=True``), the identity carries
        the real ``auth_token`` from the factory-created Principal row.
        This enables full auth chain testing: header → token → DB lookup.
        """
        from tests.harness.transport import TRANSPORT_PROTOCOL

        protocol = TRANSPORT_PROTOCOL[transport]
        if protocol not in self._identity_cache:
            from tests.factories.principal import PrincipalFactory

            # In integration mode, commit factory data first so the token
            # is visible to other sessions (e.g., get_principal_from_token
            # in the MCP auth chain uses a separate get_db_session() call).
            auth_token = None
            principal_id = self._principal_id
            if self.use_real_db:
                self._commit_factory_data()
                # _resolve_auth_token() returns None for two different reasons:
                # (a) a real DB lookup ran and found no matching Principal row, or
                # (b) self._session isn't bound yet (env constructed/used outside
                # its `with` context). Only (a) is a genuine "principal doesn't
                # exist" signal — gate on self._session directly so a session-
                # timing case doesn't get misread as a missing-principal one.
                if self._session:
                    auth_token = self._resolve_auth_token()
                    if auth_token is None:
                        # No Principal row for this principal_id+tenant_id (never
                        # created, or deleted after "authenticating") — mirror
                        # production's resolve_identity() (src/core/resolved_identity.py:
                        # 168-172), which nulls principal_id on a failed token->principal
                        # lookup, so in-process transports agree with e2e_rest's real DB
                        # lookup instead of diverging on the deleted-principal case
                        # .
                        principal_id = None

            self._identity_cache[protocol] = PrincipalFactory.make_identity(
                principal_id=principal_id,
                tenant_id=self._tenant_id,
                protocol=protocol,
                dry_run=self._dry_run,
                auth_token=auth_token,
                **self._tenant_overrides,
            )
        return self._identity_cache[protocol]

    def invalid_token_identity(self) -> ResolvedIdentity:
        """An identity carrying a token that matches no Principal row.

        Per-transport behavior is production's, and it now agrees across all
        four wire transports: on an auth-REQUIRED tool the presented-but-
        rejected credential is refused with AUTH_INVALID (terminal) everywhere —
        A2A and MCP drive the real header→token→lookup chain, e2e_rest sends the
        token over real HTTP, and REST leaves the production ``_require_auth_dep``
        in place for this identity (``_configure_rest_auth``). On an auth-
        OPTIONAL discovery tool it is treated as absent, also on every transport.
        """
        from tests.harness._identity import make_identity

        return make_identity(
            principal_id=None,
            tenant_id=self._tenant_id,
            auth_token="invalid-token-harness",
            **self._tenant_overrides,
        )

    def anonymous_identity(self) -> ResolvedIdentity:
        """Tenant-resolvable identity with NO credential and NO principal.

        Models the production no-auth discovery call where the tenant still
        resolves (Host header / subdomain) — distinct from identity=None,
        which is the no-tenant case.
        """
        from tests.harness._identity import make_identity

        return make_identity(
            principal_id=None,
            tenant_id=self._tenant_id,
            auth_token=None,
            **self._tenant_overrides,
        )

    def _resolve_auth_token(self) -> str | None:
        """Look up the real access_token from the session-bound Principal.

        Only called in integration mode where ``self._session`` is bound
        to factory-created ORM models. Returns None if the principal
        hasn't been created yet (identity built before Given steps run).
        """
        if not self._session:
            return None
        from sqlalchemy import select

        from src.core.database.models import Principal

        token = self._session.scalars(
            select(Principal.access_token).filter_by(
                principal_id=self._principal_id,
                tenant_id=self._tenant_id,
            )
        ).first()
        return token

    def switch_principal(self, principal_id: str) -> None:
        """Re-point the env at *principal_id*, clearing cached identity.

        Public accessor for the principal-switch mutation (mirrors
        ``get_session()``): step functions must not reach into the private
        ``_identity_cache`` / ``_principal_id``. Clearing the cache forces the
        next ``identity`` / ``identity_for`` access to re-resolve from scratch —
        picking up a principal row committed after the env was created (in
        integration mode this re-runs the auth-token lookup).
        """
        self._identity_cache.clear()
        self._principal_id = principal_id

    def switch_tenant(self, tenant_id: str) -> None:
        """Re-point the env at *tenant_id*, clearing cached identity.

        Sibling of ``switch_principal``: step functions that seed a scenario
        into its own fresh tenant (isolation in the shared e2e_rest live DB)
        must not reach into the private ``_identity_cache`` / ``_tenant_id``.
        Clearing the cache forces the next identity build to resolve the auth
        token against the new tenant's principal rows.
        """
        self._identity_cache.clear()
        self._tenant_id = tenant_id

    @property
    def identity(self) -> ResolvedIdentity:
        """Default identity (protocol='mcp'). Backward-compatible.

        Supports direct override via ``env._identity = ...`` for integration
        tests that create tenants in the DB and need LazyTenantContext.
        """
        # Backward compat: tests may set env._identity directly
        direct = self.__dict__.get("_identity")
        if direct is not None:
            return direct
        from tests.harness.transport import Transport

        return self.identity_for(Transport.MCP)

    # -- Transport dispatch -------------------------------------------------

    def call_via(self, transport: Transport, **kwargs: Any) -> TransportResult:
        """Dispatch through *transport* and return normalized TransportResult.

        Injects the correct identity for the transport into kwargs (unless
        the caller explicitly provides one). Routes to the appropriate
        dispatcher.
        """
        from tests.harness.dispatchers import DISPATCHERS

        # Inject transport-correct identity
        kwargs.setdefault("identity", self.identity_for(transport))

        dispatcher = DISPATCHERS[transport]
        return dispatcher.dispatch(self, **kwargs)

    # -- Per-transport hooks (override in subclass) -------------------------

    def _configure_mocks(self) -> None:
        """Wire up happy-path return values on self.mock entries.

        Called automatically after all patches are started.
        Override in subclass.
        """

    def call_impl(self, **kwargs: Any) -> Any:
        """Call the production function under test.

        Override in subclass. Should construct the request object
        and call the _impl function.
        """
        raise NotImplementedError

    def response_parser(self, tool: str) -> Any:
        """The callable that turns a wire dict into this env's response object.

        An INSTANCE hook rather than a class attribute: two envs select the
        parser from request CONTENT (create_media_buy / update_media_buy), which
        a class attribute cannot express because it cannot bind ``self``.
        Receives ``**data`` — the shape ``_run_a2a_handler`` / ``_run_mcp_client``
        already call.

        Defaults to the tool's pinned response model. An env whose tool has no
        pinned model (create_media_buy, update_media_buy, sync_creatives,
        list_authorized_properties, sync_accounts, update_performance_index)
        MUST override this, or delivery would return payload=None on a
        SUCCESSFUL dispatch.
        """
        from tests.harness.spec_models import spec_response_model

        model = self.RESPONSE_MODEL or spec_response_model(tool)
        if model is None:
            raise NotImplementedError(
                f"{type(self).__name__} dispatches {tool!r}, which has no pinned response model; "
                "override response_parser() to name the parser explicitly"
            )
        return model

    def deliver_a2a(self, **kwargs: Any) -> DeliverResult:
        """Dispatch through the real A2A pipeline, returning payload AND wire.

        THE override point for A2A. The dispatchers call this and read both
        fields off the return value, so an env that needs custom routing,
        kwargs shaping or parser selection overrides HERE — at the frame that
        already owns those concerns — rather than re-implementing dispatch.
        """
        if not self.A2A_SKILL:
            raise NotImplementedError(
                f"{type(self).__name__} declares no A2A_SKILL and does not override deliver_a2a(). "
                "Set A2A_SKILL to enable Transport.A2A dispatch."
            )
        from tests.harness.transport import Transport

        return self._deliver_via_client(Transport.A2A, self.A2A_SKILL, kwargs)

    def call_a2a(self, **kwargs: Any) -> Any:
        """The parsed A2A payload. Defined ONCE; never override — override
        :meth:`deliver_a2a` instead, so the wire survives the call."""
        return self.deliver_a2a(**kwargs).payload

    @property
    def last_a2a_task(self) -> Any:
        """Raw A2A Task from the last ``_run_a2a_handler`` dispatch (or None).

        Public accessor for Task-level contract assertions — e.g. the submitted
        (manual-approval) contract, where state=TASK_STATE_SUBMITTED with NO
        artifacts IS the wire and the parsed response is a harness synthesis
        that cannot prove artifact absence.
        """
        return self._last_a2a_task

    def deliver_mcp(self, **kwargs: Any) -> DeliverResult:
        """Dispatch through the real FastMCP Client pipeline, returning payload AND wire.

        THE override point for MCP — see :meth:`deliver_a2a`.

        Note on enum coercion: FastMCP auto-coerces string values to enums when
        calling tools through the MCP protocol, so envs dispatching here need no
        manual coercion.
        """
        if not self.MCP_TOOL:
            raise NotImplementedError(
                f"{type(self).__name__} declares no MCP_TOOL and does not override deliver_mcp(). "
                "Set MCP_TOOL to enable Transport.MCP dispatch."
            )
        from tests.harness.transport import Transport

        return self._deliver_via_client(Transport.MCP, self.MCP_TOOL, kwargs)

    def _deliver_via_client(self, transport: Any, tool: str, kwargs: dict[str, Any]) -> DeliverResult:
        """Dispatch through THE one client core, then parse with this env's parser.

        This is The harness's single-dispatch invariant, made literal: ``AdCPTestClient`` is the
        implementation the env dispatch methods DELEGATE TO, not a peer beside
        them. Routing here means address resolution, request wrapping, delivery
        and error unwrapping have exactly one implementation for both the client
        and every env.

        The payload is re-parsed with this env's own ``response_parser`` rather
        than kept as the core's pinned-model parse: envs return their LOCAL
        response subclass, and ~34 call sites outside tests/harness depend on
        that type. The core still owns the DISPATCH; the env owns only how its
        own wire is typed.

        Errors are re-RAISED rather than returned, because the dispatchers'
        contract is that deliver_* raises and they translate — the core folds
        errors into a TransportResult, so unfolding it here keeps the exception
        (and the wire envelope stashed on it) flowing to the same handler.
        """
        from tests.harness.client import _dispatch_core
        from tests.harness.transport import NO_IDENTITY_OVERRIDE

        payload = dict(kwargs)
        identity = payload.pop("identity", NO_IDENTITY_OVERRIDE)
        result = _dispatch_core(self, transport, tool, payload, identity)
        if result.error is not None:
            raise result.error
        wire = result.wire_response
        if wire is None:
            return DeliverResult(payload=result.payload, wire_response=None)
        # The captured wire is deliberately UNSTRIPPED so envelope assertions can
        # see message/success; the response model has not declared them, so they
        # come off before validation.
        parser = self.response_parser(tool)
        return DeliverResult(payload=parser(**wire), wire_response=wire)

    def call_mcp(self, **kwargs: Any) -> Any:
        """The parsed MCP payload. Defined ONCE; never override — override
        :meth:`deliver_mcp` instead, so the wire survives the call."""
        return self.deliver_mcp(**kwargs).payload

    def _run_a2a_handler(
        self,
        skill_name: str,
        response_cls: type,
        **kwargs: Any,
    ) -> Any:
        """A2A dispatch via real AdCPRequestHandler — exercises full A2A pipeline.

        Dispatches through the real AdCPRequestHandler.on_message_send(), which
        exercises: message parsing → skill routing → normalize_request_params →
        handler dispatch → _serialize_for_a2a → Task/Artifact framing.

        Identity is injected by monkey-patching ``_resolve_a2a_identity`` and
        ``_get_auth_token`` on the handler instance — single mock point, same
        as the MCP Client approach patches resolve_identity_from_context.

        Args:
            skill_name: A2A skill name (e.g., "get_products").
            response_cls: Pydantic model class to parse artifact data into.
            **kwargs: Skill parameters. ``identity`` is popped and used for
                the identity mock; ``a2a_push_notification_config`` is popped
                and sent as the protocol-level ``SendMessageConfiguration``
                (see :func:`_a2a_send_message_configuration`) rather than as a
                skill parameter; remaining kwargs become skill parameters.
        """
        import asyncio

        from a2a.server.routes.common import ServerCallContext
        from a2a.types import SendMessageRequest, Task

        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
        from tests.harness.transport import NO_IDENTITY_OVERRIDE, Transport
        from tests.utils.a2a_helpers import create_a2a_message_with_skill, extract_data_from_artifact

        self._commit_factory_data()

        # Pop identity — used for the handler mock, not sent as a skill parameter.
        identity = kwargs.pop("identity", NO_IDENTITY_OVERRIDE)
        # Pop the protocol-level push config — it belongs on SendMessageRequest.
        # configuration, one level above the skill parameters (see
        # _a2a_send_message_configuration).
        protocol_push_config = kwargs.pop("a2a_push_notification_config", None)
        a2a_identity = self.identity_for(Transport.A2A) if identity is NO_IDENTITY_OVERRIDE else identity

        # The real A2A handler writes audit logs which require the tenant to exist
        # in the DB. Ensure the tenant record exists (idempotent) so audit logging
        # doesn't fail with FK violations on discovery endpoints.
        if self.use_real_db and a2a_identity and a2a_identity.tenant_id:
            self._ensure_tenant_for_audit(a2a_identity.tenant_id)

        # Unpack req object into flat parameters if present.
        # A2A skills accept a flat parameter dict, not a request model.
        req = kwargs.pop("req", None)
        if req is not None and hasattr(req, "model_dump"):
            req_fields = req.model_dump(mode="json", exclude_none=True)
            parameters = {**req_fields, **kwargs}
        else:
            parameters = dict(kwargs)

        handler = AdCPRequestHandler()

        # Auth strategy mirrors _run_mcp_client. When the identity carries a real
        # auth_token (integration mode), populate the AuthContext that the SDK
        # call-context builder would have built from the wire and run the REAL
        # _get_auth_token + _resolve_a2a_identity (header → token → DB lookup →
        # ResolvedIdentity). Only the transport's state injection is supplied here
        # (the in-process equivalent of MCP's get_http_headers seam) — the auth
        # chain itself is real. When no real token exists (unit mode), inject the
        # identity directly via the single mock point (unchanged behavior).
        auth_token = a2a_identity.auth_token if a2a_identity else None

        if auth_token:
            from src.core.auth_context import AUTH_CONTEXT_STATE_KEY, AuthContext

            headers = {
                "x-adcp-auth": auth_token,
                "x-adcp-tenant": a2a_identity.tenant_id or "",
            }
            server_context = ServerCallContext(
                state={AUTH_CONTEXT_STATE_KEY: AuthContext(auth_token=auth_token, headers=headers)}
            )
        else:
            # _get_auth_token must return a non-None value when identity exists,
            # otherwise the handler rejects the request before _resolve_a2a_identity
            # is called. Use auth_token from identity, falling back to a sentinel.
            handler._resolve_a2a_identity = lambda *args, **kw: a2a_identity  # type: ignore[assignment]
            handler._get_auth_token = lambda *args, **kw: (  # type: ignore[assignment]
                (a2a_identity.auth_token or "harness-test-token") if a2a_identity else None
            )
            server_context = ServerCallContext()

        # Set tenant ContextVar so production code can read it
        if a2a_identity and a2a_identity.tenant:
            from src.core.config_loader import set_current_tenant

            set_current_tenant(a2a_identity.tenant)

        message = create_a2a_message_with_skill(skill_name=skill_name, parameters=parameters)
        if protocol_push_config is None:
            params = SendMessageRequest(message=message)
        else:
            params = SendMessageRequest(
                message=message,
                configuration=_a2a_send_message_configuration(protocol_push_config),
            )

        async def _call():
            return await handler.on_message_send(params, server_context)

        try:
            task_result = asyncio.run(_call())
        except Exception as exc:
            # The ORIGINAL exception propagates. It used to be translated into a
            # reconstructed AdCPSalesAgentError so callers could catch domain exceptions; the
            # dispatcher now reads the envelope off the A2AError instead
            # , and a genuine in-process production error --
            # which is what the IMPL path raises -- is unaffected either way.
            envelope = _a2a_wire_envelope(exc)
            if envelope is not None:
                raise WireError(envelope) from exc
            raise

        # Parse Task.artifacts[0] into response_cls
        if not isinstance(task_result, Task):
            raise TypeError(f"Expected Task, got {type(task_result).__name__}: {task_result}")

        # Expose the raw Task so tests can pin Task-level contract facts
        # (state, artifact absence) that the parsed response cannot prove.
        self._last_a2a_task = task_result

        # AdCP-domain errors now surface as a failed Task with the two-layer
        # envelope in the artifact DataPart. Reconstruct the AdCPSalesAgentError so
        # callers can catch domain exceptions instead of getting
        # a pydantic ValidationError from trying to parse the envelope as a
        # success response.
        from a2a.types import TaskState

        from src.core.errors.codes import AppErrorCode

        # Raised a few lines below and never imported -- the A2A-task-failed branch would
        # have died with a NameError instead of the error it means to raise.
        from src.core.exceptions import AdCPSalesAgentError

        if task_result.status.state == TaskState.TASK_STATE_FAILED:
            if task_result.artifacts:
                envelope = _wire_envelope(extract_data_from_artifact(task_result.artifacts[0]))
                if envelope is not None:
                    raise WireError(envelope)
            raise AdCPSalesAgentError(
                error_code=AppErrorCode.INTERNAL_ERROR,
                internal_detail=f"A2A task failed: {task_result.status}",
            )

        if task_result.status.state == TaskState.TASK_STATE_SUBMITTED:
            # Async manual-approval path: the server returns a submitted Task with NO
            # artifacts (adcp_a2a_server.py:683) — the submitted envelope is conveyed by
            # the Task state + id, not an artifact union. Reconstruct the submitted wire
            # (protocol status="submitted" + the task_id the buyer polls) so success-path
            # grading sees the real A2A wire.
            submitted_wire = {"status": "submitted", "task_id": task_result.id}
            return DeliverResult(payload=response_cls(**submitted_wire), wire_response=dict(submitted_wire))

        if not task_result.artifacts:
            raise ValueError(f"Task has no artifacts. Status: {task_result.status}")
        artifact_data = extract_data_from_artifact(task_result.artifacts[0])
        # Surface the full, unstripped artifact DataPart as the real A2A wire for
        # success-path assertions. Captured BEFORE stripping so siblings that need
        # the top-level envelope fields (message/success) still see them.
        wire_response = dict(artifact_data)
        # Strip protocol fields added by _serialize_for_a2a (message, success).
        # These are populated by the protocol layer per the pin's Protocol
        # Envelope branch (see tests/helpers/adcp_schema_validator.py) — not
        # declared on the Pydantic response model — and cause ValidationError
        # under extra="forbid" in non-production mode.
        return DeliverResult(payload=response_cls(**artifact_data), wire_response=wire_response)

    def _run_mcp_client(
        self,
        tool_name: str,
        response_cls: type,
        **kwargs: Any,
    ) -> Any:
        """MCP dispatch via in-memory Client — exercises full FastMCP pipeline.

        Uses FastMCP's in-memory transport (FastMCPTransport) to go through the
        complete server path: middleware chain → TypeAdapter → tool function.

        When the identity carries a real ``auth_token`` (integration mode),
        patches ``get_http_headers`` so the full auth chain runs: header
        extraction → tenant detection → token-to-principal DB lookup →
        ResolvedIdentity from real data.

        When no real token is available (unit mode), patches
        ``resolve_identity_from_context`` directly.

        Args:
            tool_name: MCP tool name (e.g., "get_products").
            response_cls: Pydantic model class to parse structured_content into.
            **kwargs: Tool arguments. ``identity`` is popped and used for the
                auth mock; ``req`` is popped and its fields unpacked into the
                arguments dict.
        """
        import asyncio
        from unittest.mock import patch

        from fastmcp import Client

        from src.core.main import mcp
        from tests.harness.transport import NO_IDENTITY_OVERRIDE, Transport

        self._commit_factory_data()

        # Pop identity — used for the auth mock, not sent as a tool argument.
        identity = kwargs.pop("identity", NO_IDENTITY_OVERRIDE)
        mcp_identity = self.identity_for(Transport.MCP) if identity is NO_IDENTITY_OVERRIDE else identity

        # Unpack req object into flat arguments if present.
        # MCP tools accept individual params, not a request model.
        req = kwargs.pop("req", None)
        if req is not None and hasattr(req, "model_dump"):
            # Narrowed to the tool's own parameters -- the same "DTO fields INTERSECT
            # implementation arguments" rule production uses. The DTO is a SUPERSET of what
            # a given tool implements (GetMediaBuysRequest declares include_history,
            # pagination and more that get_media_buys does not take), so dumping it whole
            # sends arguments the tool never advertised. In dev, extra="forbid" turns that
            # into a VALIDATION_ERROR and the scenario fails for a reason it never intended
            # to test; in production it would be silently ignored, which is worse -- the
            # harness would be grading a request the buyer could not actually make.

            req_fields = req.model_dump(exclude_none=True)
            # No narrowing. This filtered req fields down to a hand-written wrapper's
            # parameter list -- "accepted = DTO fields INTERSECT wrapper parameters" -- which
            # is exactly the intersection the registry removed. The DTO IS the accepted shape
            # on every transport now, so a field the request carries is a field the tool
            # takes, and filtering could only drop one.
            # kwargs override req fields (explicit > implicit)
            arguments = {**req_fields, **kwargs}
        else:
            arguments = dict(kwargs)

        # Choose auth strategy based on whether we have a real DB token.
        auth_token = mcp_identity.auth_token if mcp_identity else None

        if auth_token:
            # Real auth chain: header → token → DB lookup → identity.
            # Patch get_http_headers in BOTH modules that import it:
            # transport_helpers (called by resolve_identity_from_context) and
            # mcp_auth_middleware (called for context_id extraction).
            headers = self._credential_headers(mcp_identity)

            async def _call():
                mock_th = patch("src.core.transport_helpers.get_http_headers", return_value=headers)
                mock_mw = patch("src.core.mcp_auth_middleware.get_http_headers", return_value=headers)
                with mock_th as patched_th, mock_mw as patched_mw:
                    async with Client(mcp) as client:
                        result = await client.call_tool(tool_name, arguments)
                        # Guard: verify the header patches were called.
                        # If a third module imports get_http_headers without being
                        # patched, this won't catch it — but at least we verify
                        # the known auth paths were exercised.
                        assert patched_th.called or patched_mw.called, (
                            f"Auth chain not exercised for {tool_name} — get_http_headers patches were not called"
                        )
                        return DeliverResult(
                            payload=response_cls(**result.structured_content),
                            wire_response=result.structured_content,
                        )

        else:
            # Unit mode: inject identity directly.
            async def _call():
                with patch(
                    "src.core.mcp_auth_middleware.resolve_identity_from_context",
                    return_value=mcp_identity,
                ):
                    async with Client(mcp) as client:
                        result = await client.call_tool(tool_name, arguments)
                        return DeliverResult(
                            payload=response_cls(**result.structured_content),
                            wire_response=result.structured_content,
                        )

        try:
            return asyncio.run(_call())
        except Exception as exc:
            envelope = _mcp_wire_envelope(exc)
            if envelope is not None:
                raise WireError(envelope) from exc
            raise

    def _pop_rest_identity(self, kwargs: dict[str, Any]) -> Any:
        """Pop ``identity`` from REST kwargs, defaulting to the REST identity.

        Identity handling (mirrors production auth middleware):
        - identity is None → dep raises AUTH_REQUIRED (no token) with suggestion
        - identity is ResolvedIdentity → dep returns it (valid token)
        - identity absent → uses default self.identity_for(Transport.REST)
        """
        from tests.harness.transport import NO_IDENTITY_OVERRIDE, Transport

        identity = kwargs.pop("identity", NO_IDENTITY_OVERRIDE)
        if identity is NO_IDENTITY_OVERRIDE:
            identity = self.identity_for(Transport.REST)
        return identity

    def _prepare_rest_request(self, kwargs: dict[str, Any]) -> tuple[Any, Any]:
        """Resolve identity, commit factory data, get the client, and install auth.

        Single source of truth for the REST request preamble every dispatcher
        shares: pops ``identity`` from *kwargs* (defaulting to the REST identity),
        commits pending factory rows, creates/returns the TestClient, and installs
        the per-request auth-dep override (which must run AFTER ``get_rest_client``).
        Returns ``(client, resolved_identity)``; the caller builds the body from the
        now-identity-free *kwargs* and issues the HTTP verb.
        """
        identity = self._pop_rest_identity(kwargs)
        self._commit_factory_data()
        client = self.get_rest_client()
        self._configure_rest_auth(identity)
        return client, identity

    @staticmethod
    def _credential_headers(identity: Any) -> dict[str, str]:
        """The headers that carry *identity*'s credential to the production auth chain.

        One builder for both in-process wire transports: MCP patches
        ``get_http_headers`` to return it, REST sends it on the TestClient
        request. Shape is what production reads off the request
        (``src/core/auth_middleware.py``: ``x-adcp-auth`` for the token,
        ``x-adcp-tenant`` for tenant detection). Empty when no credential is
        presented, so callers can splat it unconditionally.
        """
        token = getattr(identity, "auth_token", None)
        if not token:
            return {}
        return {"x-adcp-auth": token, "x-adcp-tenant": getattr(identity, "tenant_id", None) or ""}

    @staticmethod
    def _presents_unresolvable_credential(identity: Any) -> bool:
        """True when *identity* presented a token that resolved to no principal.

        The discriminator production itself keys on: a credential WAS presented
        (``auth_token``) but no principal came back. AdCP v3.1.1 splits the two
        auth rejections on exactly this axis — absent credential -> AUTH_MISSING
        (correctable), presented-but-rejected -> AUTH_INVALID (terminal) — so
        the harness cannot collapse them the way it may collapse a valid token.
        """
        return bool(getattr(identity, "auth_token", None)) and not getattr(identity, "principal_id", None)

    @classmethod
    def _rest_request_headers(cls, identity: Any) -> dict[str, str]:
        """Auth headers for a REST request whose ``_require_auth_dep`` is NOT overridden.

        A valid identity is injected through the dependency override, so its
        request needs no headers. The presented-but-unresolvable identity is
        the one case where the real dependency runs (see
        ``_configure_rest_auth``) — and the real dependency reads the
        credential off the REQUEST, so without these headers it would see an
        empty ``AuthContext`` and answer AUTH_MISSING to a caller that did
        present a token.
        """
        if not cls._presents_unresolvable_credential(identity):
            return {}
        return cls._credential_headers(identity)

    @classmethod
    def _configure_rest_auth(cls, identity: Any) -> None:
        """Install per-request FastAPI auth-dep overrides for the test app.

        Single source of truth for the REST auth contract every dispatcher needs
        (must run AFTER ``get_rest_client``). The ``_require_auth_dep`` override
        is REMOVED — so the real production dependency runs and raises the real
        error, rather than the harness hand-copying a raise that drifted from
        production once already (#1417/cx41) — in the two cases where the
        rejection itself is what is being graded:

        - ``identity is None``: no credential at all -> real dep sees an empty
          ``AuthContext`` -> AUTH_MISSING.
        - ``identity`` presents an unresolvable credential: the request carries
          the bogus token (``_rest_request_headers``) -> real dep runs
          ``resolve_identity(require_valid_token=True)`` -> AUTH_INVALID.

        The second case used to fall through to the override below, which
        treats ANY non-None identity as an already-resolved valid token; REST
        therefore answered AUTH_MISSING to a caller who had presented a
        credential, diverging from A2A/MCP/e2e_rest, which all drive the real
        chain (GH #1886).

        ``_resolve_auth_dep`` (auth-OPTIONAL discovery routes) keeps returning
        the identity in both cases: production returns an identity there too,
        with ``principal_id`` None, which is exactly what these identities are.
        """
        from src.app import app
        from src.core.auth_context import _require_auth_dep, _resolve_auth_dep

        if identity is None or cls._presents_unresolvable_credential(identity):
            app.dependency_overrides.pop(_require_auth_dep, None)
        else:
            app.dependency_overrides[_require_auth_dep] = lambda: identity
        app.dependency_overrides[_resolve_auth_dep] = lambda: identity

    def _run_rest_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Shared REST dispatch: configure auth → build body → POST → return Response.

        Symmetric with ``_run_mcp_client``. Handles the full REST lifecycle:
        1. Pop ``identity`` from kwargs and configure dep override for this request
        2. Commit factory data
        3. Build request body from remaining kwargs
        4. POST via TestClient
        5. Return raw httpx.Response

        Envs whose route is not a body-carrying POST override this method and
        reuse ``_pop_rest_identity`` / ``_configure_rest_auth``.
        """
        client, identity = self._prepare_rest_request(kwargs)
        body = self.build_rest_body(**kwargs)
        return client.post(endpoint, json=body, headers=self._rest_request_headers(identity))

    def call_rest(self, **kwargs: Any) -> Any:
        """Call the REST endpoint and parse the response.

        Symmetric with ``call_impl``, ``call_a2a``, ``call_mcp``.
        Pops identity, configures auth, POSTs, parses response.
        Raises on HTTP errors (dispatcher catches and wraps in TransportResult).
        """
        endpoint = self.REST_ENDPOINT  # type: ignore[attr-defined]
        response = self._run_rest_request(endpoint, **kwargs)

        if response.status_code >= 400:
            envelope = self.parse_rest_error_envelope(response.status_code, response.json())
            if envelope is not None:
                raise WireError(envelope)
            raise AssertionError(
                f"REST returned HTTP {response.status_code} with a body carrying no AdCP error code: "
                f"{response.text[:400]}"
            )

        return self.parse_rest_response(response.json())

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Convert call_impl kwargs to the REST endpoint body shape.

        Default: if ``req`` is a Pydantic model, delegates serialization to it
        via ``model_dump(mode="json", exclude_none=True)``.  Enums, nested
        models, and optional fields are handled by Pydantic — no manual
        field-by-field extraction needed.

        If no ``req`` is present, returns empty dict (valid for endpoints
        where all parameters are optional).

        Subclasses that receive flat kwargs (not a ``req`` object) must
        override to build the body dict themselves.
        """
        from pydantic import BaseModel as PydanticBaseModel

        req = kwargs.get("req")
        if req is not None and isinstance(req, PydanticBaseModel):
            return req.model_dump(mode="json", exclude_none=True)
        if req is None:
            return {}
        raise NotImplementedError(
            f"{type(self).__name__}.build_rest_body() received non-Pydantic 'req': {type(req)}. "
            "Override build_rest_body() to handle this type."
        )

    def parse_rest_response(self, data: dict[str, Any]) -> BaseModel:
        """Parse REST JSON response dict into the expected Pydantic model.

        Override in subclass.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement parse_rest_response(). "
            "Override to enable Transport.REST dispatch."
        )

    def parse_rest_error_envelope(self, status_code: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """The two-layer envelope from a REST error body, or ``None``.

        Shares ``_wire_envelope`` with the A2A and MCP paths so all three agree on
        what an error body means.

        The ``STATUS_TO_ERROR`` map that used to sit here -- 400 -> AdCPValidationError,
        404 -> AdCPNotFoundError, and five more -- is DELETED. It was the same design
        mistake as the code-to-class map in a second spelling: an HTTP status guessed
        back into an AdCP class. A status is not a code, and a guess is not evidence of
        what the buyer received. A body with no recoverable code
        yields ``None``, and the dispatcher reports the raw HTTP failure instead.
        """
        return _wire_envelope(data)

    def get_rest_client(self) -> Any:
        """Return FastAPI TestClient with auth dependency overridden.

        Created lazily. Only available on IntegrationEnv subclasses.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement get_rest_client(). REST dispatch requires IntegrationEnv."
        )

    def _commit_factory_data(self) -> None:
        """Flush pending session state before calling production code.

        Factories use ``sqlalchemy_session_persistence = "commit"`` and auto-commit
        each model creation. This explicit commit ensures any cascading saves or
        deferred flushes are visible to production code's separate database session.
        Called automatically by call_impl() before each test execution.
        """
        if self._session:
            self._session.commit()

    def _seed_e2e_identity(self) -> None:
        """Seed tenant + principal into the server DB for discovery scenarios (e2e).

        Discovery scenarios (list_creative_formats, get_products) never run a
        Given step that creates a tenant/principal — in-process they don't need
        one (identity is a mock). Over e2e the live HTTP server authenticates the
        request against its own DB, so the buyer's tenant/principal/token MUST
        exist there or auth fails before the handler runs.

        Called from ``__enter__`` in e2e mode. Delegates to the idempotent
        ``setup_default_data`` (get-or-create) so it shares ONE seeding path and
        envs that also call ``setup_default_data()`` themselves don't
        double-create. Seeds the SAME ``tenant_id`` / ``principal_id`` the env's
        identity uses, so the token ``identity_for`` later resolves matches the
        seeded row.
        """
        if not self._session:
            return
        # Only IntegrationEnv exposes setup_default_data; e2e mode is always
        # an IntegrationEnv (use_real_db=True), so this is the seeding path.
        setup = getattr(self, "setup_default_data", None)
        if setup is not None:
            setup()
            self._session.commit()

    def _ensure_tenant_for_audit(self, tenant_id: str) -> None:
        """Create a minimal tenant record if none exists (idempotent).

        The real A2A handler writes audit logs which require the tenant FK.
        Discovery endpoints (list_creative_formats, get_products, etc.) don't
        need a tenant for their logic, but the handler's post-invocation audit
        logging does. This creates a stub tenant so audit logging doesn't fail.

        Uses ``self._session`` (env-managed), not ``get_db_session()``.
        """
        if not self._session:
            return
        from sqlalchemy import select

        from src.core.database.models import Tenant

        exists = self._session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not exists:
            from tests.factories import TenantFactory

            TenantFactory(tenant_id=tenant_id)
            self._session.commit()

    # -- Context manager protocol ------------------------------------------

    def __enter__(self) -> Self:
        # The nested-env guard runs BEFORE the try: it must not unwind the OUTER
        # env's factories. Everything that ACQUIRES anything runs inside.
        if self.use_real_db:
            from tests.factories import ALL_FACTORIES

            for f in ALL_FACTORIES:
                assert f._meta.sqlalchemy_session is None, (
                    f"Factory {getattr(f, '__name__', type(f).__name__)} session already bound — "
                    "nested IntegrationEnv contexts are not supported"
                )

        try:
            # 0. Subclass setup that must precede the database and the mocks.
            self._enter_pre()

            # 1. Database setup (integration mode only). INSIDE the try: the
            #    engine and the session are resources, and a SASession(bind=...)
            #    failure used to leak the engine's connection pool.
            if self.use_real_db:
                from sqlalchemy.orm import Session as SASession

                from src.core.database.database_session import get_engine
                from tests.factories import ALL_FACTORIES

                # E2E mode connects directly to the specified database (the live
                # server's Postgres via e2e_config.postgres_url) instead of the
                # cached engine, so factory writes land in the DB the HTTP
                # server reads.
                if self._database_url:
                    from sqlalchemy import create_engine

                    from src.core.database.database_session import _pydantic_json_serializer

                    self._e2e_engine = create_engine(
                        self._database_url, echo=False, json_serializer=_pydantic_json_serializer
                    )
                    self._guard("db_engine", self._dispose_engine)
                    engine = self._e2e_engine
                else:
                    engine = get_engine()

                self._session = SASession(bind=engine)
                self._guard("db_session", self._close_session)

                for f in ALL_FACTORIES:
                    f._meta.sqlalchemy_session = self._session
                self._guard("db_factories", self._unbind_factories)

            # 2. Start patches
            for name, target in self.EXTERNAL_PATCHES.items():
                if name in self.ASYNC_PATCHES:
                    patcher = patch(target, new_callable=AsyncMock)
                else:
                    patcher = patch(target)
                self.mock[name] = patcher.start()
                self._guard(f"patch:{name}", patcher.stop)

            self._configure_mocks()

            # 3. E2E discovery-path seeding: the live server authenticates against
            #    its own DB, so seed tenant/principal even for scenarios that never
            #    run a tenant-creating Given step. Idempotent; no-op in-process.
            if self.use_real_db and self.is_e2e:
                self._seed_e2e_identity()

            # 4. Subclass setup that needs the entered base and configured mocks.
            self._enter_post()
        except BaseException:
            self._unwind_partial_enter()
            raise

        return self

    # -- Subclass setup hooks ----------------------------------------------
    #
    # A subclass extends entry through these, never by overriding __enter__.
    # The reason is structural, not stylistic: a cooperative
    # ``super().__enter__()`` chain places a subclass's own setup OUTSIDE this
    # method's try by construction, whichever side of the super() call it sits
    # on. Every resource a hook acquires must be registered with :meth:`_guard`
    # on the line it is acquired.
    #
    # ``tests/harness/test_harness_base.py::test_harness_envs_define_no_enter_exit``
    # enforces that: __enter__/__exit__ (and their async twins) may be defined
    # only on BaseTestEnv and on AdminAccountEnv, which is not a BaseTestEnv.

    def _enter_pre(self) -> None:
        """Setup that must run before the database binding and the mocks.

        Overridden by e.g. ``LocalOriginMixin``, whose TLS origin must exist
        before ``_configure_mocks`` runs — ``CircuitBreakerEnv._configure_mocks``
        programs ``self.origin``.
        """

    def _enter_post(self) -> None:
        """Setup that needs the entered base and the configured mocks.

        Overridden by e.g. ``CircuitBreakerEnv``, which attaches a log handler
        once the env is otherwise live.
        """

    # -- The one cleanup registry ------------------------------------------

    def _guard(self, label: str, cleanup: Callable[[], None]) -> None:
        """Register *cleanup* to run on BOTH release paths, newest first.

        Call it on the line the resource is acquired. Anything acquired without
        a matching _guard survives a failed __enter__ for the rest of the
        process: Python does not call __exit__ when __enter__ raises, and the
        factory binding is GLOBAL. Measured before this registry existed: two
        real setup failures produced 350 further errors in one bdd_e2e run, and
        the two causes were indistinguishable in the report.
        """
        self._enter_cleanups.append((label, cleanup))

    def _release_entered(self, errors: list[Exception] | None) -> None:
        """Run every registered cleanup in REVERSE registration order, then clear.

        LIFO is deliberate and is a change from the pre-registry teardown, which
        released the database BEFORE the patches. Releasing in reverse
        acquisition order is the property that makes a partially-entered env
        safe, and no teardown here depends on a patch still being active.

        *errors* collects failures when the caller wants them (``__exit__``,
        which raises them as a group). ``None`` means best-effort and silent —
        the partial-enter path, where the caller is already raising and a
        cleanup detail must not replace the real cause.
        """
        for _label, cleanup in reversed(self._enter_cleanups):
            try:
                cleanup()
            except Exception as e:
                if errors is not None:
                    errors.append(e)
        self._enter_cleanups.clear()

    # Three cleanups, not one, and each registered on the line its resource is
    # acquired. A single "db" cleanup registered after all three acquisitions
    # left an already-created engine undisposed when SASession(bind=engine)
    # raised — exactly the pool leak of GH #1430, still open. Splitting also
    # fixes the second half: each runs in its own _release_entered try, so a
    # failure is COLLECTED into __exit__'s error list rather than swallowed by a
    # suppress() that head did not have. Registration order engine -> session ->
    # factories means LIFO release is factories -> session -> engine, which is
    # exactly the order the pre-registry __exit__ used.

    def _unbind_factories(self) -> None:
        from tests.factories import ALL_FACTORIES

        for f in ALL_FACTORIES:
            f._meta.sqlalchemy_session = None

    def _close_session(self) -> None:
        if self._session is not None:
            session, self._session = self._session, None
            session.close()

    def _dispose_engine(self) -> None:
        """Closing the session alone leaves its pool's connections open, and
        ~300 e2e envs per run accumulate toward the server's max_connections
        (GH #1430)."""
        if getattr(self, "_e2e_engine", None) is not None:
            engine, self._e2e_engine = self._e2e_engine, None
            engine.dispose()

    def _unwind_partial_enter(self) -> None:
        """Release whatever ``__enter__`` had acquired before it failed.

        Best-effort and SILENT by design, unlike ``__exit__``: the caller is
        already raising, and an error raised from here would replace the real
        cause with a cleanup detail. That is why ``_release_entered`` takes
        ``None`` on this path and an error list on the other.

        The GLOBAL state — the factory session binding — is released
        unconditionally at the end even if a registered cleanup misbehaved,
        because a leaked binding fails every later scenario on the worker.
        """
        self._release_entered(None)
        self.mock.clear()

        if self.use_real_db:
            with suppress(Exception):
                from tests.factories import ALL_FACTORIES

                for f in ALL_FACTORIES:
                    f._meta.sqlalchemy_session = None

    def __exit__(self, *exc: object) -> bool:
        errors: list[Exception] = []

        # 1. Clean up REST client
        if self._rest_client is not None:
            try:
                from src.app import app

                app.dependency_overrides.clear()
                self._rest_client = None
            except Exception as e:
                errors.append(e)

        # 2. Release everything __enter__ registered, newest first. This covers
        #    the database (factory unbind / session close / engine dispose) and
        #    every patch, plus whatever the subclass hooks acquired.
        self._release_entered(errors)
        self.mock.clear()
        self._identity_cache.clear()

        if errors:
            if len(errors) == 1:
                raise errors[0]
            raise ExceptionGroup("Multiple teardown errors", errors)
        return False


class IntegrationEnv(BaseTestEnv):
    """Integration test environment — real database, only mocks external services.

    Requires ``integration_db`` pytest fixture.
    Supports REST dispatch via FastAPI TestClient.
    """

    use_real_db = True
    #: TestClient(app, raise_server_exceptions=...) for get_rest_client(). True
    #: preserves every existing REST test's behavior unchanged — provably a
    #: no-op for every typed error path (AdCPSalesAgentError/ValueError/
    #: RequestValidationError/PermissionError/ToolError each have their own
    #: @app.exception_handler and never reach ServerErrorMiddleware, the only
    #: place this flag matters). inject_untyped_exception() sets this to False
    #: as an INSTANCE attribute (not by overriding this class default) so the
    #: opt-out is scoped to exactly the scenario that calls it.
    REST_RAISE_SERVER_EXCEPTIONS: bool = True

    def setup_default_data(self, **tenant_kwargs: Any) -> tuple[Any, Any]:
        """Get-or-create default tenant + principal via factories.

        Must be called inside the ``with env:`` block (factories are bound
        to the session during ``__enter__``).

        Returns (tenant, principal) ORM instances. Uses self._tenant_id
        and self._principal_id from constructor. Idempotent: reuses existing
        rows rather than re-creating, so it is safe to call after the e2e
        discovery-path auto-seed (``_seed_e2e_identity``) already created them.

        Extra ``tenant_kwargs`` are tenant policy columns the live e2e_rest
        server reads from the shared DB (e.g. ``human_review_required``).
        Forwarded to ``TenantFactory`` on the create path; APPLIED to the
        existing row on the get path — the __enter__ auto-seed creates the
        tenant with model defaults, so the kwargs must win over those defaults
        regardless of which call created the row.
        """
        from sqlalchemy import select

        from src.core.database.models import Principal, Tenant
        from tests.factories import PrincipalFactory, TenantFactory

        tenant = self._session.scalars(select(Tenant).filter_by(tenant_id=self._tenant_id)).first()
        if tenant is None:
            tenant = TenantFactory(tenant_id=self._tenant_id, **tenant_kwargs)
        elif tenant_kwargs:
            for column, value in tenant_kwargs.items():
                setattr(tenant, column, value)
            self._commit_factory_data()

        principal = self._session.scalars(
            select(Principal).filter_by(tenant_id=self._tenant_id, principal_id=self._principal_id)
        ).first()
        if principal is None:
            principal = PrincipalFactory(tenant=tenant, principal_id=self._principal_id)

        # NO account is seeded here, deliberately. Seeding one for every tenant made
        # UC-011's account-LISTING scenarios wrong -- "0 accounts visible" saw one -- which
        # is the cost of a default that is invisible at the call site. The tools that
        # REQUIRE an account seed it where they build the request instead: see
        # MediaBuyCreateEnv._ensure_required_request_fields / _seed_named_account, the BDD
        # request defaults, and MediaBuyFactory.
        return tenant, principal

    def setup_default_account(self, principal_id: str | None = None) -> Any:
        """Get-or-create the default Account (plus this principal's access to it).

        AdCP 3.1.1 makes ``account`` REQUIRED on several requests (sync-creatives-request
        and update-media-buy-request both list it in /required), so a scenario that does
        not seed one cannot build a valid request at all -- it fails on a missing field
        before reaching the behaviour it means to grade.

        Must be called inside the ``with env:`` block, and it calls
        ``setup_default_data`` first: the Account row carries a tenant_id FK, so seeding
        it against a tenant that does not exist yet is the FK violation this method
        exists to make unreachable.

        Idempotent, like ``setup_default_data`` -- reuses an existing row so repeated
        Given steps do not collide.
        """
        tenant, principal = self.setup_default_data()
        # Access is granted to the principal that will actually SEND the request, which is
        # not always the env's default: a cross-principal isolation test drives a second
        # principal, and an account its principal cannot reach comes back as
        # AdCPAuthorizationError rather than the behaviour under test.
        grantee = principal_id or principal.principal_id
        return self._seed_default_account(tenant, grantee)

    def _seed_default_account(self, tenant: Any, grantee: str) -> Any:
        """The body of ``setup_default_account``, callable from ``setup_default_data`` too.

        Split out so the tenant seeder can seed an account without calling
        ``setup_default_account``, which starts by calling the tenant seeder -- the two
        would otherwise recurse.
        """
        from sqlalchemy import select

        from src.core.database.models import Account, AgentAccountAccess
        from tests.factories.account import AccountFactory, AgentAccountAccessFactory

        account = self._session.scalars(select(Account).filter_by(tenant_id=self._tenant_id)).first()
        if account is None:
            # tenant_id, never tenant= -- Account.tenant is a real relationship, so handing
            # it a SubFactory's throwaway Tenant makes SQLAlchemy re-sync tenant_id FROM
            # that object at flush and silently relocate the row (see AccountFactory.Meta).
            # A DETERMINISTIC id, not the factory Sequence: tests name this account by
            # literal (``{"account_id": "acct_test"}``) in ~120 request constructions, and a
            # sequence id would parse in all of them and resolve in none.
            account = AccountFactory(tenant_id=tenant.tenant_id, account_id=DEFAULT_TEST_ACCOUNT_ID)

        # Only a principal that EXISTS can be granted access: agent_account_access carries
        # an FK to principals, and several scenarios drive a deliberately unknown identity
        # (tenant-not-found, unauthenticated) whose principal has no row. For those the
        # grant is skipped -- the account still exists so the request is well-formed, and
        # the scenario reaches the auth rejection it is actually about.
        from src.core.database.models import Principal

        grantee_exists = (
            self._session.scalars(select(Principal).filter_by(tenant_id=self._tenant_id, principal_id=grantee)).first()
            is not None
        )
        access = self._session.scalars(
            select(AgentAccountAccess).filter_by(
                tenant_id=self._tenant_id,
                principal_id=grantee,
                account_id=account.account_id,
            )
        ).first()
        if access is None and grantee_exists:
            AgentAccountAccessFactory(
                tenant_id=tenant.tenant_id,
                principal_id=grantee,
                account_id=account.account_id,
            )
        self._commit_factory_data()
        return account

    def default_account_reference(self) -> Any:
        """The seeded account as the AccountReference a request field wants.

        core/account-ref.json is a oneOf: {account_id} or {brand, operator, sandbox?}.
        The account_id form is the one a seeded row can satisfy exactly, so steps get
        that rather than reconstructing a brand/operator pair the DB may not agree with.
        """
        from adcp.types import AccountReference

        return AccountReference(root={"account_id": self.setup_default_account().account_id})

    # Seeding a NAMED account reference lives here rather than on one env: any env whose
    # tool carries an ``account`` needs it, and update_media_buy needed it the moment the
    # boundary started RESOLVING the reference instead of accepting and dropping it.
    def _seed_named_account_ref(self, account: Any) -> None:
        """Seed the row behind an account reference, when it is the suite's default.

        Takes the reference in either spelling -- the wire dict a per-field caller passes,
        or the typed AccountReference on a built request -- because both paths reach the
        same boundary lookup.
        """
        root = getattr(account, "root", account)
        account_id = root.get("account_id") if isinstance(root, dict) else getattr(root, "account_id", None)
        if account_id == DEFAULT_TEST_ACCOUNT_ID:
            self.setup_default_account()

    def _seed_named_account(self, req: Any) -> None:
        """Seed the account a caller-BUILT request names, when it is the suite's default.

        A test that hands ``req=`` built its request outside this env, so
        ``_ensure_required_request_fields`` never ran and nothing created the row the
        transport boundary is about to resolve. Only DEFAULT_TEST_ACCOUNT_ID is seeded: a
        test naming its own account is describing a specific account state (missing,
        suspended, foreign) and manufacturing a row for it would erase the case.
        """
        account = getattr(req, "account", None)
        if account is not None:
            self._seed_named_account_ref(account)

    def configure_tenant_field(self, field: str, value: Any) -> None:
        """Write a tenant-level config field for both auth paths.

        Updates the in-memory tenant overrides (mock identity path) AND the
        DB Tenant row when the column exists (real MCP/A2A auth chain reads
        the DB via config_loader). Clears the identity cache so the next
        ``identity_for`` re-resolves with the new value.
        """
        self._tenant_overrides[field] = value
        self._identity_cache.clear()

        if self._session:
            from src.core.database.models import Tenant

            tenant = self._session.get(Tenant, self._tenant_id)
            if tenant is not None and hasattr(tenant, field):
                setattr(tenant, field, value)
                self._session.commit()

    # -- Public query API (step functions must use these, not env._session) ----

    def get_session(self) -> Session:
        """Return the env-bound SQLAlchemy session for read-back assertions.

        Public accessor so step functions never reach into the private
        ``_session`` attribute. Only valid inside the ``with env:`` block.
        """
        if self._session is None:
            raise RuntimeError(
                f"{type(self).__name__}.get_session() called without an active session — "
                "use it inside a 'with env:' block (integration mode)."
            )
        return self._session

    def query(self, model: type, **filters: Any) -> list:
        """Return all rows of ``model`` matching ``filters`` via the bound session."""
        from sqlalchemy import select

        return list(self.get_session().scalars(select(model).filter_by(**filters)).all())

    def get_one(self, model: type, **filters: Any) -> Any:
        """Return the first row of ``model`` matching ``filters``, or ``None``."""
        from sqlalchemy import select

        return self.get_session().scalars(select(model).filter_by(**filters)).first()

    def get_workflow_steps(self) -> list:
        """Return WorkflowStep rows scoped to this env's tenant.

        WorkflowStep has no tenant_id column; tenant scoping is via its Context
        relationship, so this joins WorkflowStep -> Context and filters on
        ``Context.tenant_id``.
        """
        from sqlalchemy import select

        from src.core.database.models import Context, WorkflowStep

        stmt = select(WorkflowStep).join(WorkflowStep.context).where(Context.tenant_id == self._tenant_id)
        return list(self.get_session().scalars(stmt).all())

    def get_rest_client(self) -> Any:
        """Return FastAPI TestClient with default auth dep override.

        The default dep override returns ``self.identity_for(Transport.REST)``.
        ``_run_rest_request`` overrides this per-request for multi-agent and
        no-auth scenarios. Direct callers of ``get_rest_client()`` get the
        default identity.
        """
        if self._rest_client is None:
            from starlette.testclient import TestClient

            from src.app import app
            from src.core.auth_context import _require_auth_dep, _resolve_auth_dep
            from tests.harness.transport import Transport

            rest_identity = self.identity_for(Transport.REST)
            app.dependency_overrides[_require_auth_dep] = lambda: rest_identity
            app.dependency_overrides[_resolve_auth_dep] = lambda: rest_identity
            self._rest_client = TestClient(app, raise_server_exceptions=self.REST_RAISE_SERVER_EXCEPTIONS)

        return self._rest_client


class BareIntegrationEnv(IntegrationEnv):
    """Integration env with no external patches — for repository-level tests.

    Repository tests exercise the data layer directly: they need the real
    database session and factory binding ``IntegrationEnv`` provides, but none
    of the adapter/notifier mocks. ``get_session()`` commits any pending
    factory data and exposes the session for direct repository construction.
    """

    EXTERNAL_PATCHES: dict[str, str] = {}

    def get_session(self) -> Any:
        """Commit pending factory data and expose the session."""
        self._commit_factory_data()
        return self._session
