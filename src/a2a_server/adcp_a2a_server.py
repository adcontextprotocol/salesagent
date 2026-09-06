#!/usr/bin/env python3
"""
Prebid Sales Agent A2A Server using official a2a-sdk library.
Supports both standard A2A message format and JSON-RPC 2.0.
"""

import json
import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable

# Import core functions for direct calls (raw functions without FastMCP decorators)
from datetime import UTC, datetime
from typing import Any

from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue import Event
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import (
    AgentCard,
    AgentExtension,
    AgentInterface,
    AgentSkill,
    Artifact,
    AuthenticationInfo,
    CancelTaskRequest,
    DeleteTaskPushNotificationConfigRequest,
    GetExtendedAgentCardRequest,
    GetTaskPushNotificationConfigRequest,
    GetTaskRequest,
    InternalError,
    InvalidParamsError,
    InvalidRequestError,
    ListTaskPushNotificationConfigsRequest,
    ListTaskPushNotificationConfigsResponse,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    MethodNotFoundError,
    Part,
    SendMessageRequest,
    SubscribeToTaskRequest,
    Task,
    TaskNotFoundError,
    TaskPushNotificationConfig,
    TaskState,
    TaskStatus,
    UnsupportedOperationError,
)
from a2a.utils.errors import A2AError
from adcp.server.mcp_tools import ADCP_TOOL_DEFINITIONS
from adcp.types import ContextObject, GeneratedTaskStatus
from adcp.types.base import AdCPBaseModel
from google.protobuf import json_format, struct_pb2

from src.core.audit_logger import get_audit_logger
from src.core.auth_context import AUTH_CONTEXT_STATE_KEY
from src.core.database.repositories import PushNotificationConfigUoW
from src.core.domain_config import get_a2a_server_url
from src.core.errors.codes import AppErrorCode
from src.core.errors.issues import ErrorIssue, JsonPointer
from src.core.exceptions import (
    AdCPAuthenticationError,
    AdCPAuthRequiredError,
    AdCPCapabilityNotSupportedError,
    AdCPSalesAgentError,
    AdCPUrlNotAllowedError,
    AdCPValidationError,
    adcp_error_for,
    build_two_layer_error_envelope,
)
from src.core.resolved_identity import ResolvedIdentity
from src.core.schema_helpers import (
    coerce_creative_filters,
    select_request_fields,
    to_account_reference,
    to_brand_reference,
)
from src.core.schemas import CreativeStatusEnum
from src.core.tool_context import ToolContext
from src.core.tool_error_logging import record_boundary_error

# Signals tools removed - should come from dedicated signals agents, not sales agent
from src.core.tools._boundary import invoke_tool
from src.core.tools.registry import TOOLS
from src.core.version import get_version
from src.core.webhook_validator import (
    webhook_url_for_log,
)
from src.core.webhooks.delivery import WebhookTaskContext
from src.core.webhooks.registration import (
    ValidatedWebhookRegistration,
    accept_push_notification_primitives,
)
from src.services.protocol_webhook_service import get_protocol_webhook_service

logger = logging.getLogger(__name__)


#: The ONE request model this file still names, for the ONE selection that is deliberately
#: NOT narrowed to a builder: _handle_update_media_buy_skill validates the whole bag against
#: the DTO before building. Every narrowed selection reads its model off the tool
#: (``select_request_fields_for``) and names nothing.
from src.core.schemas import UpdateMediaBuyRequest  # noqa: E402


def _require_params(params: dict, required: list[str], *, field: str | None = None) -> None:
    """Refuse a skill invocation missing required parameters.

    Three handlers carried an identical copy of this check; one helper keeps them from
    drifting apart (CLAUDE.md treats duplicated logic as a defect).
    """
    missing = [p for p in required if p not in params]
    if missing:
        raise AdCPValidationError(
            issues=[ErrorIssue.of(pointer=JsonPointer.of(name).pointer, keyword="required") for name in missing],
            field=field,
        )


def _invalid_params_from_ssrf_error(exc: Exception) -> InvalidParamsError:
    """Wrap a refused registration as A2A InvalidParamsError with the AdCP ``data`` envelope.

    Both typed rejections this seam can see pass through VERBATIM: a refused URL
    (``AdCPUrlNotAllowedError``) and a refused credential (``AdCPValidationError``
    naming ``push_notification_config.authentication.credentials``). Narrowing to
    the URL class alone would send a credential refusal down the else branch and
    re-label it as a URL problem. Only an untyped exception is manufactured into
    ``AdCPUrlNotAllowedError``; its buyer-facing suggestion comes from the
    CODE_TABLE entry for the code, never a per-class override (ADR-010), so no
    ``suggestion=`` is passed here.
    """
    if isinstance(exc, (AdCPUrlNotAllowedError, AdCPValidationError)):
        adcp_err: AdCPSalesAgentError = exc
    else:
        adcp_err = AdCPUrlNotAllowedError(
            field="push_notification_config.url",
        )
    return InvalidParamsError(
        message=adcp_err.message,
        data=build_two_layer_error_envelope(adcp_err),
    )


def _a2a_push_config_auth(config: Any) -> tuple[str | None, str | None]:
    """Pull ``(scheme, credentials)`` out of an A2A push-config protobuf.

    Both A2A surfaces that carry a push config -- ``setTaskPushNotificationConfig``
    and the protocol-level ``message/send`` configuration -- hold the same flat
    protobuf whose ``authentication`` is an optional submessage with a SINGULAR
    free-form ``scheme`` string. Read in one place so the two surfaces cannot
    disagree about which field the credential half lives in.
    """
    if not config.HasField("authentication"):
        return None, None
    return (config.authentication.scheme or None, config.authentication.credentials or None)


def _accept_a2a_push_config(url: str, scheme: str | None, credentials: str | None) -> ValidatedWebhookRegistration:
    """Accept an A2A push-config registration, or raise ``InvalidParamsError``.

    The ONE A2A translation seam for push-config ingest, shared by BOTH surfaces
    that carry one: ``setTaskPushNotificationConfig`` and the protocol-level
    ``message/send`` configuration. Delegates to
    :func:`~src.core.webhooks.registration.accept_push_notification_primitives`
    (the A2A ``authentication`` carries a SINGULAR free-form ``scheme`` string,
    not the tool path's ``schemes`` list) so this transport cannot drift from the
    tool path on either precondition.

    Why both surfaces must come through here rather than call the constructor
    directly: ``on_message_send``'s body runs inside a ``try`` whose handlers are
    ``except A2AError: raise`` / ``except Exception`` -> ``_internal_error_for``.
    ``AdCPValidationError`` is not an ``A2AError``, so a raw constructor call
    there would surface a buyer's correctable credential refusal as
    ``INTERNAL_ERROR``. The translation below preserves the raised error
    verbatim (see :func:`_invalid_params_from_ssrf_error`'s isinstance branch),
    which is what keeps a credential refusal naming the credentials field
    instead of being re-labelled as a URL problem.

    BOTH typed rejections are caught, because the gate now raises two classes:
    ``reject_unsafe_webhook_registration_url`` refuses the URL with the dedicated
    ``AdCPUrlNotAllowedError`` (a direct ``AdCPSalesAgentError`` subclass, NOT an
    ``AdCPValidationError``), while the credential precondition still raises
    ``AdCPValidationError``. Catching only the latter would let a refused URL
    escape to ``on_message_send``'s ``except Exception`` and reach the buyer as
    ``INTERNAL_ERROR`` instead of a correctable -32602.
    """
    try:
        return accept_push_notification_primitives(
            url,
            scheme,
            credentials,
            field_prefix="push_notification_config",
        )
    except (AdCPValidationError, AdCPUrlNotAllowedError) as e:
        raise _invalid_params_from_ssrf_error(e) from e


def _dict_to_value(d: dict) -> struct_pb2.Value:
    """Convert a Python dict to a protobuf Value for use in Part.data."""
    val = struct_pb2.Value()
    json_format.Parse(json.dumps(d, default=str), val)
    return val


def _dict_to_struct(d: dict) -> struct_pb2.Struct:
    """Convert a Python dict to a protobuf Struct for use in Task.metadata."""
    s = struct_pb2.Struct()
    s.update(d)
    return s


# Field names typed `integer` (not `number`) in the pinned AdCP v3.1.1 schema
# that this server can place in an A2A Part.data (via _dict_to_value above).
#
# google.protobuf.Value/Struct -- the well-known types backing Part.data --
# have NO integer variant: every JSON number is stored as number_value (a
# double), by protobuf's own well-known-type design. Any int placed in a
# Part.data is therefore irreversibly widened to a double the moment it
# enters the Struct/Value, and comes back out as a JSON float (86400 ->
# 86400.0) from ANY subsequent json_format.MessageToJson/MessageToDict call
# -- ours or the a2a-sdk's own jsonrpc_dispatcher.py, which performs the
# identical conversion to build the real HTTP response body. There is no way
# to preserve the distinction inside the Struct/Value representation itself;
# the only fix point is a coercion applied to the JSON produced FROM the
# Struct/Value, driven by which fields are known to be integer-typed per spec.
#
# Spec: v3.1.1 (adcp==6.6.0) -- replay_ttl_seconds:
# get-adcp-capabilities-response.json #/properties/adcp/properties/idempotency
# (type: integer). limit: get-creative-delivery-response.json
# #/properties/limit. Others below are verified `type: integer` fields on
# this server's other explicit-skill responses (sync/assign counts, delivery
# totals, revision, attribution window). Extend this set as new integer
# fields are found on the A2A wire -- coercion only fires for a listed name
# whose value is a whole-numbered float, so an unlisted or genuinely
# fractional field is never touched.
A2A_WIRE_INTEGER_FIELDS = frozenset(
    {
        "replay_ttl_seconds",
        "limit",
        "returned_count",
        "revision",
        "interval",
        "attribution_window_days",
        "total_processed",
        "created",
        "updated",
        "unchanged",
        "failed",
        "deleted",
        "total_assignments_processed",
        "assigned",
        "unassigned",
        "total_impressions",
        "active_count",
        "impressions",
    }
)


def restore_a2a_integer_types(data: Any, integer_field_names: frozenset[str] = A2A_WIRE_INTEGER_FIELDS) -> Any:
    """Recursively coerce known integer-typed fields back to ``int``.

    Reverses the double-widening every number undergoes when it round-trips
    through a protobuf Struct/Value (see A2A_WIRE_INTEGER_FIELDS above).
    Only touches a value that is BOTH a whole-numbered float AND at a key in
    ``integer_field_names`` -- an unlisted key or a genuinely fractional
    value is returned unchanged, so this cannot silently corrupt real
    ``number``-typed fields.

    Shared by the production ``/a2a`` route wrapper (src/app.py) and the test
    harness's ``extract_data_from_artifact`` (tests/utils/a2a_helpers.py) --
    both perform the same Struct/Value -> JSON conversion the a2a-sdk itself
    performs, so both need the same restoration to keep the harness's "real
    A2A wire" claim honest.
    """
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key in integer_field_names and isinstance(value, float) and value.is_integer():
                result[key] = int(value)
            else:
                result[key] = restore_a2a_integer_types(value, integer_field_names)
        return result
    if isinstance(data, list):
        return [restore_a2a_integer_types(item, integer_field_names) for item in data]
    return data


# ADCP Discovery Skills: Skills that don't require authentication
# Per AdCP spec section 3.2, these endpoints allow optional authentication for public discovery.
# IMPORTANT: This is the single source of truth for auth-optional skills in A2A.
# Add new skills here ONLY if they meet AdCP discovery endpoint requirements:
#   1. Return only public/non-sensitive data
#   2. Support tenant-level access control (e.g., brand_manifest_policy)
#   3. Never expose user-specific or transactional data
#   4. Must be safe to call without authentication
DISCOVERY_SKILLS = frozenset(
    {
        "get_adcp_capabilities",  # Agent capabilities (always public per AdCP spec)
        "list_accounts",  # Account discovery (public, returns empty for unauthed per BR-RULE-055)
        "list_creative_formats",  # Creative specifications (always public)
        "get_products",  # Conditional: depends on tenant brand_manifest_policy setting
    }
)


def _internal_error_for(operation: str, exc: Exception) -> InternalError:
    """Canonical InternalError shape for non-skill A2A boundary failures.

    Skill handlers raise typed ``AdCPSalesAgentError`` (or untyped exceptions that the
    dispatcher normalizes), and ``_handle_explicit_skill`` → ``on_message_send``
    surface those as a two-layer envelope on a failed Task's DataPart. Non-skill
    paths (``on_message_send`` fallthrough, NL handlers) historically picked their
    own prefixes (``"Message processing failed: "``, ``"Error in ..."``)
    for semantically identical untyped failures — divergence on the buyer-
    facing wire message for the same condition.

    Use this helper at every non-skill ``InternalError(...)`` raise site that
    is NOT a deliberate protocol-level convention (see push-notif handlers
    below). ``message`` is built from ``adcp_error_for(exc).message``,
    NEVER the raw exception's own ``str()`` — the two are only the same value
    when ``exc`` is already a typed ``AdCPSalesAgentError`` (passed through unchanged,
    its message deliberately authored to be buyer-safe) or one of the other
    typed branches (``ValueError``/``PermissionError``, our own deliberately-
    raised validation text). For an arbitrary/untyped exception,
    ``adcp_error_for`` itself replaces the message with
    ``type(exc).__name__`` — the raw text has no provenance guarantee (AdCP
    3.1.1 transport-errors.mdx Security Considerations MUST-NOT list) and must
    not reach the JSON-RPC wire. This keeps ``message`` informative for the
    common typed-error case (the same text ``data`` carries) without ever
    re-deriving it from ``exc`` directly.

    The four ``on_*_task_push_notification_config`` JSON-RPC protocol methods use
    this helper too — they have no async Task to carry a DataPart, so the two-layer
    envelope rides in the error's ``data`` field (``error.data["errors"][0]["code"]``
    / ``error.data["adcp_error"]``). ``InternalError`` stays an ``A2AError`` so the
    SDK's ``JsonRpcDispatcher`` serializes it as a structured JSON-RPC error; raising
    a non-``A2AError`` (e.g. ``AdCPAdapterError``) would hit the dispatcher's
    ``except Exception`` branch and be flattened to a bare ``InternalError`` with no
    envelope.
    """
    typed = adcp_error_for(exc)
    return InternalError(
        message=f"{operation} failed: {typed.message}",
        data=build_two_layer_error_envelope(typed),
    )


class AdCPRequestHandler(RequestHandler):
    """Request handler for AdCP A2A operations supporting JSON-RPC 2.0."""

    def __init__(self):
        """Initialize the AdCP A2A request handler."""
        self.tasks: dict[str, Task] = {}  # In-memory task storage
        # The VALUE, not the raw protobuf: what is stashed here is handed straight
        # to the sender, so it must carry the gate's receipt.
        self._task_push_configs: dict[str, ValidatedWebhookRegistration] = {}
        logger.info("AdCP Request Handler initialized for direct function calls")

    @staticmethod
    def _build_error_envelope(exc: Exception) -> dict[str, Any]:
        """Build a spec-compliant two-layer envelope for any exception.

        Single source of truth for "wrap-arbitrary-exception → wire envelope"
        used by both the per-skill dispatcher (``_build_failed_skill_result``)
        and the top-level ``on_message_send`` error handler. Delegates to
        ``adcp_error_for`` for the type→AdCPSalesAgentError mapping
        (``ValueError → AdCPValidationError``, ``PermissionError →
        AdCPAuthorizationError``, arbitrary ``Exception →
        AdCPSalesAgentError(INTERNAL_ERROR)``) so the wire output stays in
        ``CODE_TABLE`` (the pinned ``enums/error-code.json`` plus this platform's
        own ``AppErrorCode`` members) and the envelope shape never degrades to a
        flat ``{"error": "..."}`` dict the storyboard runner would synthesize
        as ``MCP_ERROR``.
        """

        return build_two_layer_error_envelope(adcp_error_for(exc))

    @staticmethod
    def _build_failed_skill_result(skill_name: str, exc: Exception) -> dict[str, Any]:
        """Build the dispatcher result dict for a failed skill invocation.

        Both the typed-AdCPSalesAgentError branch and the untyped fallthrough land here so
        the artifact DataPart always carries a spec-compliant two-layer envelope
        under ``error_envelope`` — the single source of truth on the wire, never a
        flat ``{"error": "..."}`` dict. Callers needing the human-readable message
        read ``error_envelope["errors"][0]["message"]``.
        """
        return {
            "skill": skill_name,
            "error_envelope": AdCPRequestHandler._build_error_envelope(exc),
            "success": False,
        }

    def _get_auth_token(self, context: ServerCallContext | None = None) -> str | None:
        """Extract Bearer token from ServerCallContext.

        Args:
            context: ServerCallContext from SDK (None when called directly in tests).
        """
        if context is None:
            return None
        auth_ctx = context.state.get(AUTH_CONTEXT_STATE_KEY)
        return auth_ctx.auth_token if auth_ctx else None

    def _resolve_a2a_identity(
        self,
        auth_token: str | None,
        require_valid_token: bool = True,
        context: ServerCallContext | None = None,
    ) -> ResolvedIdentity:
        """Resolve identity at the A2A transport boundary — called ONCE per request.

        This is the A2A equivalent of REST's _resolve_auth(). It calls
        resolve_identity() once and returns the result. All downstream handlers
        receive the pre-resolved identity instead of re-resolving from auth_token.

        Args:
            auth_token: Bearer token from Authorization header (None for unauthenticated)
            require_valid_token: If True, auth failures raise A2AError
            context: ServerCallContext from SDK (None when called directly in tests).

        Returns:
            ResolvedIdentity with tenant and (optionally) principal info

        Raises:
            A2AError: If require_valid_token=True and authentication fails
        """
        from src.core.resolved_identity import resolve_identity
        from src.core.testing_hooks import AdCPTestContext

        auth_ctx = context.state.get(AUTH_CONTEXT_STATE_KEY) if context is not None else None
        headers = auth_ctx.headers if auth_ctx else {}

        if require_valid_token and not auth_token:
            raise InvalidRequestError(
                message="Missing authentication token",
                data=build_two_layer_error_envelope(AdCPAuthRequiredError()),
            )

        # Extract testing context from A2A request headers (same as MCP does)
        testing_context = AdCPTestContext.from_headers(headers)

        try:
            identity = resolve_identity(
                headers=headers,
                auth_token=auth_token,
                require_valid_token=require_valid_token,
                protocol="a2a",
                testing_context=testing_context,
            )
        except AdCPAuthenticationError as e:
            # resolve_identity raises AdCPAuthenticationError (AUTH_INVALID)
            # for a presented-but-invalid token. Route through the same
            # two-layer envelope builder used elsewhere in this file instead
            # of dropping the wire code entirely (a recorded gap — this
            # branch previously re-wrapped as a bare InvalidRequestError with
            # no error_code/wire-code field at all).
            raise InvalidRequestError(message=str(e), data=build_two_layer_error_envelope(e)) from e

        if require_valid_token:
            if not identity.principal_id:
                # No principal_id at all -> AUTH_MISSING per v3.1.1
                # error-code.json.
                raise InvalidRequestError(
                    message="Authentication token is invalid or expired.",
                    data=build_two_layer_error_envelope(AdCPAuthRequiredError()),
                )

            if not identity.tenant:
                # DEFER: tenant-axis, out of scope for the AUTH_MISSING/
                # AUTH_INVALID split — left unchanged.
                raise InvalidRequestError(
                    message=f"Unable to determine tenant from authentication. Principal: {identity.principal_id}"
                )

            tenant_id = identity.tenant_id or identity.tenant.get("tenant_id", "unknown")
            logger.info(
                f"[A2A AUTH] ✅ Authentication successful: tenant={tenant_id}, principal={identity.principal_id}"
            )

        # Set tenant ContextVar at the A2A transport boundary
        if identity.tenant:
            from src.core.config_loader import set_current_tenant

            set_current_tenant(identity.tenant)

        return identity

    def _make_tool_context(
        self, identity: ResolvedIdentity, tool_name: str, context_id: str | None = None
    ) -> ToolContext:
        """Build ToolContext from a pre-resolved identity — NO database calls.

        Args:
            identity: Pre-resolved identity from _resolve_a2a_identity
            tool_name: Name of the tool being called
            context_id: Optional context ID for conversation tracking

        Returns:
            ToolContext for calling core functions
        """
        if not context_id:
            context_id = f"a2a_{datetime.now(UTC).timestamp()}"

        tenant_id = identity.tenant_id or (
            identity.tenant.get("tenant_id", "unknown") if identity.tenant else "unknown"
        )

        return ToolContext(
            context_id=context_id,
            tenant_id=tenant_id,
            principal_id=identity.principal_id,
            tool_name=tool_name,
            request_timestamp=datetime.now(UTC),
            metadata={"source": "a2a_server", "protocol": "a2a_jsonrpc"},
            testing_context=identity.testing_context,
        )

    def _log_a2a_operation(
        self,
        operation: str,
        tenant_id: str,
        principal_id: str,
        success: bool = True,
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ):
        """Log A2A operations to audit system for visibility in activity feed."""
        try:
            if not tenant_id:
                return

            audit_logger = get_audit_logger("A2A", tenant_id)
            audit_logger.log_operation(
                operation=operation,
                principal_name=f"A2A_Client_{principal_id}",
                principal_id=principal_id,
                adapter_id="a2a_client",
                success=success,
                details=details,
                error=error,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning("Failed to log A2A operation: %s", e)

    async def _send_protocol_webhook(
        self,
        task: Task,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ):
        """Send protocol-level push notification if configured.

        Per AdCP A2A spec (https://docs.adcontextprotocol.org/docs/protocols/a2a-guide#push-notifications-a2a-specific):
        - Final states (completed, failed, canceled): Send full Task object with artifacts
        - Intermediate states (working, input-required, submitted): Send TaskStatusUpdateEvent

        ``notify`` selects the payload type from the status: Task for final states,
        TaskStatusUpdateEvent for intermediate ones.
        """
        try:
            # Check if task has push notification config stored
            webhook_config = self._task_push_configs.get(task.id)
            if not webhook_config:
                return

            push_notification_service = get_protocol_webhook_service()

            if not webhook_config.url.strip():
                logger.info("[red]No push notification URL present; skipping webhook[/red]")
                return

            # The stashed VALUE is handed to the sender directly. There is nothing to
            # fabricate: send_notification reads exactly .url / .authentication_type /
            # .authentication_token, which is precisely what the value carries. The
            # detached DBPushNotificationConfig(tenant_id="", principal_id="") that
            # used to stand in here was a config-shaped object with empty scope ids,
            # built purely to satisfy a type — i.e. a way to hand a sender a config
            # that no repository ever receipted.
            push_notification_config = webhook_config

            # Convert status string to GeneratedTaskStatus enum
            try:
                status_enum = GeneratedTaskStatus(status)
            except ValueError:
                # Fallback for unknown status values
                logger.warning("Unknown status '%s', defaulting to 'working'", status)
                status_enum = GeneratedTaskStatus.working

            # Build result data for the webhook payload
            # Include error information in result if status is failed
            result_data: dict[str, Any] = result or {}
            if error and status == "failed":
                result_data["error"] = error

            # Extract skills_requested from protobuf Struct metadata
            meta_dict = json_format.MessageToDict(task.metadata) if task.metadata.ByteSize() > 0 else {}
            skills = list(meta_dict.get("skills_requested", []))

            # tenant_id / principal_id are None here, and that is a decision rather
            # than an omission. This path delivers PROTOCOL task updates, whose
            # task_type is a skill name; records_delivery_log only fires for
            # "delivery_report" / "media_buy_delivery", so no webhook_delivery_log
            # row is expected and the registration this sender holds
            # (ValidatedWebhookRegistration) carries no scope ids to give it.
            # Stating them as None is what makes that visible -- the dict this
            # replaced simply had no such keys (salesagent-pldmk.39).
            webhook_task = WebhookTaskContext(
                task_id=task.id,
                task_type=skills[0] if skills else "unknown",
                tenant_id=None,
                principal_id=None,
                media_buy_id=None,
                sequence_number=1,
                notification_type=None,
            )

            # notify() picks the payload type: Task for final states,
            # TaskStatusUpdateEvent for intermediate ones. protocol is "a2a"
            # unconditionally -- this IS the A2A server.
            sent = await push_notification_service.notify(
                push_notification_config,
                task=webhook_task,
                status=status_enum,
                result=result_data,
                protocol="a2a",
                context_id=task.context_id or "",
            )
            if not sent:
                logger.warning(
                    "Protocol webhook not delivered for task %s (send_notification returned False)",
                    task.id,
                )
        except Exception as e:
            # Don't fail the task if webhook fails
            logger.warning("Failed to send protocol-level webhook for task %s: %s", task.id, e)

    async def on_message_send(
        self,
        params: SendMessageRequest,
        context: ServerCallContext,
    ) -> Task | Message:
        """Handle 'message/send' method for non-streaming requests.

        Supports both invocation patterns from AdCP PR #48:
        1. Natural Language: parts[{kind: "text", text: "..."}]
        2. Explicit Skill: parts[{kind: "data", data: {skill: "...", parameters: {...}}}]

        Args:
            params: Parameters including the message and configuration
            context: Server call context

        Returns:
            Task object or Message response
        """
        logger.info("Handling message/send request: %s", params)

        # Parse message for both text and structured data parts
        message = params.message
        text_parts = []
        skill_invocations = []

        if hasattr(message, "parts") and message.parts:
            for part in message.parts:
                # Handle text parts (natural language invocation)
                if part.text:
                    text_parts.append(part.text)

                # Handle structured data parts (explicit skill invocation)
                # part.data is a protobuf Value — convert to Python dict
                elif part.HasField("data"):
                    data = json_format.MessageToDict(part.data)
                    if isinstance(data, dict) and "skill" in data:
                        # Support both "input" (A2A spec) and "parameters" (legacy) for skill params
                        params_data = data.get("input") or data.get("parameters", {})
                        skill_invocations.append({"skill": data["skill"], "parameters": params_data})
                        logger.info(
                            f"Found explicit skill invocation: {data['skill']} with params: {list(params_data.keys())}"
                        )

        # Combine text for natural language fallback
        combined_text = " ".join(text_parts).strip().lower()

        # Create task for tracking
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        # In protobuf, message_id is always a string (empty string default)
        msg_id = params.message.message_id or None
        context_id = params.message.context_id or msg_id or f"ctx_{task_id}"

        # Extract push notification config from protocol layer (A2A SendMessageConfiguration).
        # SSRF gate runs after auth resolution below (defense-in-depth: AUTH_REQUIRED
        # before scheme/blocked-host checks when the request requires credentials).
        push_notification_config: TaskPushNotificationConfig | None = None
        if params.HasField("configuration") and params.configuration.HasField("task_push_notification_config"):
            push_notification_config = params.configuration.task_push_notification_config

        # Prepare task metadata (JSON-serializable only — protobuf Struct)
        task_metadata: dict[str, Any] = {
            "request_text": combined_text,
            "invocation_type": "explicit_skill" if skill_invocations else "natural_language",
        }
        if skill_invocations:
            task_metadata["skills_requested"] = [inv["skill"] for inv in skill_invocations]

        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
            metadata=_dict_to_struct(task_metadata),
        )
        self.tasks[task_id] = task

        # Bound BEFORE the try because the handler below reads it: identity is
        # resolved partway through, so any earlier failure — the push-config gate
        # among them — used to raise UnboundLocalError from the error handler and
        # replace the real error with a confusing one.
        identity: ResolvedIdentity | None = None

        try:
            # Get authentication token
            auth_token = self._get_auth_token(context)

            # Check if any requested skills require authentication
            # Default to not requiring auth - only require if we have non-discovery skills
            requires_auth = False
            if skill_invocations:
                # If ANY skill requires auth (not in discovery set), then require auth
                requested_skills = {inv["skill"] for inv in skill_invocations}
                non_discovery_skills = requested_skills - DISCOVERY_SKILLS
                if non_discovery_skills:
                    requires_auth = True

            # Require authentication for non-public skills. Stay a JSON-RPC
            # InvalidRequestError (protocol-level rejection, top-level error), but
            # carry the two-layer envelope in ``data`` so the buyer-facing
            # AUTH_MISSING code + suggestion reach the A2A wire — matching
            # REST's no-identity envelope (auth_context.py), which the bare
            # A2AError previously dropped. (#1417; split to AUTH_MISSING per
            # v3.1.1 error-code.json — )
            if requires_auth and not auth_token:
                raise InvalidRequestError(
                    message="Missing authentication token - Bearer token required in Authorization header",
                    data=build_two_layer_error_envelope(AdCPAuthRequiredError()),
                )

            # SSRF-reject unsafe push URLs after the auth-required gate so callers
            # that need credentials see AUTH_REQUIRED before scheme/blocked-host checks.
            # ONE branch: stash iff a registration was built. Previously the gate ran
            # under `config and config.url` while the stash ran under `config` alone,
            # so a blank-url config was stashed ungated (the reader then early-returned
            # on it). Observably equivalent, minus the ungated stash.
            if push_notification_config and push_notification_config.url:
                registration = _accept_a2a_push_config(
                    push_notification_config.url,
                    *_a2a_push_config_auth(push_notification_config),
                )
                logger.info(
                    "Protocol-level push notification config provided for task %s: %s",
                    task_id,
                    webhook_url_for_log(push_notification_config.url),
                )
                self._task_push_configs[task_id] = registration

            # ── Transport boundary: resolve identity ONCE ──
            # Like REST's _resolve_auth(), identity is resolved here and passed
            # to all downstream handlers. No handler should call resolve_identity().
            # Its `= None` initialisation used to live HERE, which is why a failure
            # in the push-config gate above reached the error handler with the name
            # unbound; it now sits before the `try` so every branch can read it.
            if auth_token:
                # A PRESENTED token must always be validated, regardless of
                # whether the requested skill itself requires auth — absent
                # token -> proceed anonymous (fine); presented-but-invalid
                # token -> must reject with AUTH_INVALID (terminal), even on
                # a public/discovery-only skill request. Previously this
                # reused `requires_auth` (skill-based) here, so an invalid
                # token on a discovery-only request was silently swallowed as
                # anonymous by resolve_identity()'s require_valid_token=False
                # path instead of being rejected.
                identity = self._resolve_a2a_identity(auth_token, require_valid_token=True, context=context)
            elif not requires_auth:
                # Unauthenticated discovery request — resolve tenant from headers only
                identity = self._resolve_a2a_identity(None, require_valid_token=False, context=context)

            # Route: Handle explicit skill invocations first, then natural language fallback
            if skill_invocations:
                # Process explicit skill invocations
                results = []
                for invocation in skill_invocations:
                    skill_name = invocation["skill"]
                    parameters = invocation["parameters"]
                    logger.info("Processing explicit skill: %s with parameters: %s", skill_name, parameters)

                    try:
                        result = await self._handle_explicit_skill(
                            skill_name,
                            parameters,
                            identity,
                            push_config_registration=self._task_push_configs.get(task_id),
                        )
                        results.append({"skill": skill_name, "result": result, "success": True})
                    except A2AError:
                        # A2AError should bubble up immediately (JSON-RPC error).
                        # Reserved for transport-protocol failures (MethodNotFound,
                        # malformed request, etc.) — never AdCP-level errors, which
                        # are now caught below and surfaced as failed Tasks with a
                        # two-layer envelope in the artifact DataPart.
                        raise
                    except AdCPSalesAgentError as e:
                        # AdCP-level errors are async-task failures, not JSON-RPC
                        # errors. Mirrors the SDK's _send_adcp_error reference for
                        # storyboard scenarios that exercise invalid-state
                        # transitions on an otherwise-routable skill.
                        # NOTE: logging happens in ``_handle_explicit_skill``'s
                        # except branch (with audit log + activity feed); duplicating
                        # the logger call here would produce two messages for the
                        # same failure.
                        results.append(self._build_failed_skill_result(skill_name, e))
                    except Exception as e:
                        # Untyped fallthrough — same envelope shape as the AdCPSalesAgentError
                        # branch so storyboard runners can `JSON.parse` the DataPart
                        # uniformly regardless of which branch caught the failure.
                        # Route through the canonical boundary hook (ERROR + exc_info
                        # for untyped failures, plus activity-feed + audit) so untyped
                        # A2A skill failures land on the same observability surface as
                        # MCP/REST and the typed path. The typed
                        # (AdCPSalesAgentError/ValueError/PermissionError) failures were already
                        # recorded inside _handle_explicit_skill, so this only fires for
                        # genuinely-unexpected exceptions that escaped it.
                        record_boundary_error(
                            "a2a",
                            skill_name,
                            e,
                            tenant_id=getattr(identity, "tenant_id", None),
                            principal_id=getattr(identity, "principal_id", None) or "anonymous",
                        )
                        results.append(self._build_failed_skill_result(skill_name, e))

                # Check for submitted status (manual approval required) - return early without artifacts
                # Per AdCP spec, async operations should return Task with status=submitted and no artifacts
                for res in results:
                    if res["success"] and isinstance(res["result"], dict):
                        result_status = res["result"].get("status")
                        if result_status == "submitted":
                            task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_SUBMITTED))
                            del task.artifacts[:]  # No artifacts for pending tasks
                            logger.info(
                                f"Task {task_id} requires manual approval, returning status=submitted with no artifacts"
                            )
                            # Send protocol-level webhook notification
                            await self._send_protocol_webhook(task, status="submitted")
                            self.tasks[task_id] = task
                            return task

                # Create artifacts for all skill results with human-readable text
                for i, res in enumerate(results):
                    if res["success"]:
                        artifact_data = res["result"]
                    elif "error_envelope" in res:
                        # Failure path: surface the full two-layer envelope as
                        # the DataPart so the storyboard runner / harness can
                        # read either ``adcp_error.code`` or ``errors[0].code``.
                        artifact_data = res["error_envelope"]
                    else:
                        # Every failure result comes from _build_failed_skill_result,
                        # which always sets error_envelope. A failed result without it
                        # is a contract violation — fail loud rather than silently emit
                        # the legacy flat ``{"error": ...}`` shape.
                        raise AdCPSalesAgentError(
                            error_code=AppErrorCode.INTERNAL_ERROR,
                            internal_detail=(
                                f"Skill result for {res.get('skill', '?')!r} is marked failed "
                                "but carries no error_envelope"
                            ),
                        )

                    # Generate human-readable text from response __str__()
                    # Per A2A spec, use TextPart + DataPart pattern (not description field)
                    #
                    # The text is READ from the payload, never re-derived from it:
                    # _stamp_a2a_protocol_fields already stamped str(response) onto
                    # artifact_data["message"] at serialization time. An outbound
                    # payload is finished — feeding it back through Model(**data)
                    # to recover the same string handed pydantic before-validators
                    # a reference to the dict about to go on the wire, and one of
                    # them mutated it in place (the list_creatives format_id
                    # bare-string defect). Nothing rebuilds an outbound payload.
                    text_message = None
                    if res["success"] and isinstance(artifact_data, dict):
                        text_message = artifact_data.get("message")

                    # Build parts list per A2A spec: optional text Part + required data Part
                    parts = []
                    if text_message:
                        parts.append(Part(text=text_message))
                    parts.append(Part(data=_dict_to_value(artifact_data)))

                    task.artifacts.append(
                        Artifact(
                            artifact_id=f"skill_result_{i + 1}",
                            name=f"{'error' if not res['success'] else res['skill']}_result",
                            parts=parts,
                        )
                    )

                # Check if any skills failed and determine task status
                failed_skills = [res["skill"] for res in results if not res["success"]]
                successful_skills = [res["skill"] for res in results if res["success"]]

                if failed_skills and not successful_skills:
                    # All skills failed - mark task as failed
                    task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_FAILED))

                    # Send protocol-level webhook notification for failure
                    error_messages = [
                        res["error_envelope"]["errors"][0]["message"] for res in results if not res["success"]
                    ]
                    await self._send_protocol_webhook(task, status="failed", error="; ".join(error_messages))

                    return task
                elif successful_skills:
                    # Log successful skill invocations with rich context
                    try:
                        tenant_id = (identity.tenant_id or "unknown") if identity else "unknown"
                        principal_id = (identity.principal_id or "unknown") if identity else "unknown"

                        # Extract meaningful details from results
                        log_details = {"skills": successful_skills, "count": len(successful_skills)}

                        # Add context from the first successful skill
                        first_result = next((r for r in results if r["success"]), None)
                        if first_result and "result" in first_result:
                            result_data = first_result["result"]

                            # Extract budget and package info for create_media_buy
                            if "create_media_buy" in first_result["skill"]:
                                if isinstance(result_data, dict):
                                    if "total_budget" in result_data:
                                        log_details["total_budget"] = result_data["total_budget"]
                                    if "packages" in result_data:
                                        log_details["package_count"] = len(result_data["packages"])
                                    if "media_buy_id" in result_data:
                                        log_details["media_buy_id"] = result_data["media_buy_id"]

                            # Extract product count for get_products
                            elif "get_products" in first_result["skill"]:
                                if isinstance(result_data, dict) and "products" in result_data:
                                    log_details["product_count"] = len(result_data["products"])

                            # Extract creative count for sync_creatives
                            elif "sync_creatives" in first_result["skill"]:
                                if isinstance(result_data, dict) and "creatives" in result_data:
                                    log_details["creative_count"] = len(result_data["creatives"])

                        self._log_a2a_operation(
                            "explicit_skill_invocation",
                            tenant_id,
                            principal_id,
                            True,
                            log_details,
                        )
                    except Exception as e:
                        logger.warning("Could not log skill invocations: %s", e)

            # Natural language fallback (existing keyword-based routing)
            elif any(word in combined_text for word in ["product", "inventory", "available", "catalog"]):
                # The same handler the explicit-skill path uses, and the same one the
                # pricing branch below already calls. There used to be a private twin here
                # (_get_products) that built its own request and hardcoded adcp_version=None
                # -- a second declaration of one tool on one transport, which is how it kept
                # a lazy import of a deleted builder alive after every other caller was
                # rewired: nothing enumerating the registry could see it.
                result = await self._handle_get_products_skill({"brief": combined_text}, identity)
                tenant_id = (identity.tenant_id or "unknown") if identity else "unknown"
                principal_id = (identity.principal_id or "unknown") if identity else "unknown"

                self._log_a2a_operation(
                    "get_products",
                    tenant_id,
                    principal_id,
                    True,
                    {
                        "query": combined_text[:100],
                        "product_count": len(result.get("products", [])) if isinstance(result, dict) else 0,
                    },
                )
                del task.artifacts[:]
                task.artifacts.append(
                    Artifact(
                        artifact_id="product_catalog_1",
                        name="product_catalog",
                        parts=[Part(data=_dict_to_value(result))],
                    )
                )
            elif any(word in combined_text for word in ["price", "pricing", "cost", "cpm", "budget"]):
                # Redirect pricing queries to get_products which has real price_guidance
                result = await self._handle_get_products_skill(
                    {"brief": combined_text},
                    identity,
                )
                tenant_id = (identity.tenant_id or "unknown") if identity else "unknown"
                principal_id = (identity.principal_id or "unknown") if identity else "unknown"

                self._log_a2a_operation(
                    "get_products",
                    tenant_id,
                    principal_id,
                    True,
                    {
                        "query": combined_text[:100],
                        "query_type": "pricing",
                        "products_count": len(result.get("products", [])) if isinstance(result, dict) else 0,
                    },
                )
                del task.artifacts[:]
                task.artifacts.append(
                    Artifact(
                        artifact_id="pricing_info_1",
                        name="pricing_information",
                        parts=[Part(data=_dict_to_value(result))],
                    )
                )
            elif any(word in combined_text for word in ["target", "audience"]):
                # Redirect targeting queries to get_adcp_capabilities which has real targeting info
                result = await self._handle_get_adcp_capabilities_skill({}, identity)
                tenant_id = (identity.tenant_id or "unknown") if identity else "unknown"
                principal_id = (identity.principal_id or "unknown") if identity else "unknown"

                self._log_a2a_operation(
                    "get_adcp_capabilities",
                    tenant_id,
                    principal_id,
                    True,
                    {
                        "query": combined_text[:100],
                        "query_type": "targeting",
                    },
                )
                del task.artifacts[:]
                task.artifacts.append(
                    Artifact(
                        artifact_id="targeting_opts_1",
                        name="targeting_options",
                        parts=[Part(data=_dict_to_value(result))],
                    )
                )
            elif any(word in combined_text for word in ["create", "buy", "campaign", "media"]):
                # ``_create_media_buy`` is an NL stub that always raises
                # ``AdCPCapabilityNotSupportedError`` — the explicit-skill
                # path is the spec contract for media buy creation. The
                # outer error handler at on_message_send catches the raise
                # and attaches a spec-compliant two-layer envelope to the
                # failed Task artifact.
                await self._create_media_buy(combined_text, identity)
            else:
                # General help response
                capabilities = {
                    "supported_queries": [
                        "product_catalog",
                        "targeting_options",
                        "pricing_information",
                        "campaign_creation",
                    ],
                    "example_queries": [
                        "What video ad products do you have available?",
                        "Show me targeting options",
                        "What are your pricing models?",
                        "How do I create a media buy?",
                    ],
                }
                tenant_id = (identity.tenant_id or "unknown") if identity else "unknown"
                principal_id = (identity.principal_id or "unknown") if identity else "unknown"

                self._log_a2a_operation(
                    "get_capabilities",
                    tenant_id,
                    principal_id,
                    True,
                    {"query": combined_text[:100], "response_type": "capabilities"},
                )
                del task.artifacts[:]
                task.artifacts.append(
                    Artifact(
                        artifact_id="capabilities_1",
                        name="capabilities",
                        parts=[Part(data=_dict_to_value(capabilities))],
                    )
                )

            # Determine task status based on operation result
            # For sync_creatives, check if any creatives are pending review
            task_state = TaskState.TASK_STATE_COMPLETED
            task_status_str = "completed"

            result_data = {}
            if task.artifacts:
                # Extract result from artifacts — part.data is a protobuf Value
                for artifact in task.artifacts:
                    if artifact.parts:
                        for part in artifact.parts:
                            if part.HasField("data"):
                                data_dict = json.loads(json_format.MessageToJson(part.data))
                                result_data[artifact.name] = data_dict

                                # Check if this is a sync_creatives response with pending creatives
                                if artifact.name == "result" and isinstance(data_dict, dict):
                                    creatives = data_dict.get("creatives", [])
                                    if any(
                                        c.get("status") == CreativeStatusEnum.pending_review.value
                                        for c in creatives
                                        if isinstance(c, dict)
                                    ):
                                        task_state = TaskState.TASK_STATE_SUBMITTED
                                        task_status_str = "submitted"

                                    # Check for explicit status field (e.g., create_media_buy returns this)
                                    result_status = data_dict.get("status")
                                    if result_status == "submitted":
                                        task_state = TaskState.TASK_STATE_SUBMITTED
                                        task_status_str = "submitted"

            # Mark task with appropriate status
            task.status.CopyFrom(TaskStatus(state=task_state))

            # Send protocol-level webhook notification if configured
            await self._send_protocol_webhook(task, status=task_status_str)

        except A2AError:
            # Re-raise A2AError as-is (will be caught by JSON-RPC handler)
            raise
        except Exception as e:
            # Use identity resolved at transport boundary (if available).
            # identity is initialised to None before the try (below), because it is
            # bound partway through it: ANY failure before that point — the
            # push-config gate among them — otherwise raised UnboundLocalError from
            # the error handler itself and replaced the real error.
            err_tenant_id = (identity.tenant_id or "unknown") if identity else "unknown"
            err_principal_id = (identity.principal_id or "unknown") if identity else "unknown"

            record_boundary_error(
                "a2a",
                "message_processing",
                e,
                tenant_id=err_tenant_id,
                principal_id=err_principal_id,
            )

            # Send protocol-level webhook notification for failure if configured
            task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_FAILED))
            # Attach error to task artifacts as a spec-compliant two-layer
            # envelope (same shape as failed-skill DataParts) so storyboard
            # runners can ``JSON.parse`` the artifact uniformly regardless of
            # which failure path produced it.
            del task.artifacts[:]
            task.artifacts.append(
                Artifact(
                    artifact_id="error_1",
                    name="processing_error",
                    parts=[Part(data=_dict_to_value(self._build_error_envelope(e)))],
                )
            )

            await self._send_protocol_webhook(task, status="failed")

            # Raise A2A error instead of creating failed task
            raise _internal_error_for("message processing", e)

        self.tasks[task_id] = task
        return task

    async def on_message_send_stream(
        self,
        params: SendMessageRequest,
        context: ServerCallContext,
    ) -> AsyncGenerator[Event]:
        """Handle 'message/stream' method for streaming requests.

        Args:
            params: Parameters including the message and configuration
            context: Server call context

        Yields:
            Event objects (Task or Message) from the agent's execution
        """
        # For now, implement non-streaming behavior
        # In production, this would yield events as they occur
        result = await self.on_message_send(params, context)

        # Event is a union type: Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
        # result is already Task | Message — yield it directly
        yield result

    def _get_task_or_raise(self, task_id: str) -> Task:
        """Return the in-memory task, or raise ``TaskNotFoundError``.

        A bare ``None`` return makes the SDK synthesize a generic internal error;
        the A2A spec defines ``TaskNotFoundError`` for an unknown task id, so
        raising it is the correct thing to do here and is what an A2A client
        should be able to react to precisely.

        What a client sees TODAY is still ``-32603``, not the spec's ``-32001``:
        this app builds its A2A routes with ``enable_v0_3_compat=True``
        (``src/app.py:306``), so requests dispatch through
        ``a2a.compat.v0_3.jsonrpc_adapter``, whose ``handle_request`` ends in a
        bare ``except Exception -> CoreInternalError`` with no ``A2AError -> code``
        mapping — the mapping the SDK's own main dispatcher performs. Returning
        ``None`` produces the same ``-32603`` there, so the code cannot be fixed
        at this layer (#1670). Raising the right type is still correct and is what
        will surface ``-32001`` the moment that gap closes; the xfail'd
        live-server test pins the current reality.

        The requested id is put on both the message and structured ``data``.
        Only the message reaches a client today: the same compat adapter that
        flattens the code to ``-32603`` rebuilds the error as
        ``CoreInternalError(message=str(e))``, which drops ``data`` — driving
        the real route returns ``data: null``. Populating it is still correct
        and becomes readable when #1670 closes, the same as the code.

        Shared by ``on_get_task`` and ``on_cancel_task`` so both surface the
        same error.
        """
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(message=f"Task not found: {task_id}", data={"task_id": task_id})
        return task

    async def on_get_task(
        self,
        params: GetTaskRequest,
        context: ServerCallContext,
    ) -> Task:
        """Handle 'tasks/get' method to retrieve task status.

        Raises ``TaskNotFoundError`` for an unknown task id — see
        ``_get_task_or_raise`` (and #1670 for why the wire code is still -32603).
        """
        return self._get_task_or_raise(params.id)

    async def on_cancel_task(
        self,
        params: CancelTaskRequest,
        context: ServerCallContext,
    ) -> Task:
        """Handle 'tasks/cancel' method to cancel a task.

        Raises ``TaskNotFoundError`` for an unknown task id — cancelling a task
        that does not exist is the same not-found condition as get, not a silent
        no-op. See ``_get_task_or_raise`` (and #1670 for why the wire code is
        still -32603).
        """
        task = self._get_task_or_raise(params.id)
        # CopyFrom mutates the stored Task in place — self.tasks already holds
        # this exact reference, so re-storing it would rebind the same object.
        task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_CANCELED))
        return task

    async def on_list_tasks(
        self,
        params: ListTasksRequest,
        context: ServerCallContext,
    ) -> ListTasksResponse:
        """Handle 'tasks/list' method."""
        raise UnsupportedOperationError(message="Task listing not supported")

    async def on_subscribe_to_task(
        self,
        params: SubscribeToTaskRequest,
        context: ServerCallContext,
    ) -> AsyncGenerator[Event, None]:
        """Handle task subscription requests."""
        raise UnsupportedOperationError(message="Task subscription not supported")
        yield  # Make this a generator (unreachable but satisfies type checker)

    async def on_get_task_push_notification_config(
        self,
        params: GetTaskPushNotificationConfigRequest,
        context: ServerCallContext,
    ) -> TaskPushNotificationConfig:
        """Handle get push notification config requests.

        Retrieves the push notification configuration for a specific config ID.
        """
        tool_context = None
        try:
            auth_token = self._get_auth_token(context)
            if not auth_token:
                raise InvalidRequestError(message="Missing authentication token")
            identity = self._resolve_a2a_identity(auth_token, context=context)
            tool_context = self._make_tool_context(identity, "get_push_notification_config")

            config_id = params.get("id") if isinstance(params, dict) else getattr(params, "id", None)
            if not config_id:
                raise InvalidParamsError(message="Missing required parameter: id")

            with PushNotificationConfigUoW(tool_context.tenant_id) as uow:
                assert uow.push_notification_configs is not None
                config = uow.push_notification_configs.get_by_id(
                    config_id,
                    principal_id=tool_context.principal_id,
                )

                if not config:
                    raise TaskNotFoundError(message=f"Push notification config not found: {config_id}")

                response_id = config.id
                response_url = config.url
                response_validation_token = config.validation_token or ""
                # Read-BACK, not sender-side auth resolution: this echoes the
                # buyer's own registration to them. The egress seam has nothing
                # to offer here — there is no outbound request being
                # authenticated — so this file is a justified false positive in
                # test_architecture_no_inline_webhook_auth_resolution's allowlist,
                # not deferred debt. Deliberately no FIXME.
                auth_scheme = config.authentication_type
                auth_credentials = config.authentication_token

            auth_info = (
                AuthenticationInfo(scheme=auth_scheme, credentials=auth_credentials)
                if auth_scheme and auth_credentials
                else None
            )
            return TaskPushNotificationConfig(
                id=response_id,
                task_id=params.task_id,
                url=response_url,
                authentication=auth_info,
                token=response_validation_token,
            )

        except A2AError:
            raise
        except Exception as e:
            record_boundary_error(
                "a2a",
                "get_push_notification_config",
                e,
                tenant_id=tool_context.tenant_id if tool_context else None,
                principal_id=tool_context.principal_id if tool_context else None,
            )
            raise _internal_error_for("get push notification config", e) from e

    async def on_create_task_push_notification_config(
        self,
        params: TaskPushNotificationConfig,
        context: ServerCallContext,
    ) -> TaskPushNotificationConfig:
        """Handle set push notification config requests.

        Creates or updates a push notification configuration for async operation callbacks.
        Buyers use this to register webhook URLs where they want to receive status updates.
        """
        tool_context = None
        try:
            auth_token = self._get_auth_token(context)
            if not auth_token:
                raise InvalidRequestError(message="Missing authentication token")
            identity = self._resolve_a2a_identity(auth_token, context=context)
            tool_context = self._make_tool_context(identity, "set_push_notification_config")

            # In a2a-sdk 1.0, TaskPushNotificationConfig is a flat protobuf message
            # with fields: tenant, id, task_id, url, token, authentication
            task_id = params.task_id
            url = params.url
            config_id = params.id or f"pnc_{uuid.uuid4().hex[:16]}"
            validation_token = params.token

            if not url:
                raise InvalidParamsError(message="Missing required parameter: url")

            auth_type, auth_token_value = _a2a_push_config_auth(params)

            # Both registration preconditions, BEFORE the try. The except below
            # funnels every ValueError into _invalid_params_from_ssrf_error, which
            # manufactures field="push_notification_config.url" plus the https SSRF
            # wording for a non-AdCP error -- so a credential refusal raised from
            # inside the repository would reach the buyer as "fix your URL" about a
            # URL that is fine (salesagent-47n9.20).
            registration = _accept_a2a_push_config(url, auth_type, auth_token_value)

            # No ValueError funnel around upsert any more: the repository no longer
            # re-validates, because the value it now takes IS the receipt that the
            # gate above ran. The funnel existed only to catch that second gate, and
            # its own comment (above) documents how it mislabelled what it caught.
            with PushNotificationConfigUoW(tool_context.tenant_id) as uow:
                assert uow.push_notification_configs is not None
                _config, created = uow.push_notification_configs.upsert(
                    registration,
                    config_id=config_id,
                    principal_id=tool_context.principal_id,
                    validation_token=validation_token,
                    # This IS the A2A server, so the dialect is not in doubt here.
                    protocol="a2a",
                )

            logger.info(
                f"Push notification config {'created' if created else 'updated'}: {config_id} for tenant {tool_context.tenant_id}"
            )

            auth_info = (
                AuthenticationInfo(scheme=auth_type, credentials=auth_token_value)
                if auth_type and auth_token_value
                else None
            )
            return TaskPushNotificationConfig(
                task_id=task_id or "*",
                url=url,
                authentication=auth_info,
                id=config_id,
                token=validation_token or "",
            )

        except A2AError:
            raise
        except Exception as e:
            record_boundary_error(
                "a2a",
                "create_push_notification_config",
                e,
                tenant_id=tool_context.tenant_id if tool_context else None,
                principal_id=tool_context.principal_id if tool_context else None,
            )
            raise _internal_error_for("set push notification config", e) from e

    async def on_list_task_push_notification_configs(
        self,
        params: ListTaskPushNotificationConfigsRequest,
        context: ServerCallContext,
    ) -> ListTaskPushNotificationConfigsResponse:
        """Handle list push notification config requests.

        Returns all active push notification configurations for the authenticated principal.
        """
        tool_context = None
        try:
            auth_token = self._get_auth_token(context)
            if not auth_token:
                raise InvalidRequestError(message="Missing authentication token")
            identity = self._resolve_a2a_identity(auth_token, context=context)
            tool_context = self._make_tool_context(identity, "list_push_notification_configs")

            with PushNotificationConfigUoW(tool_context.tenant_id) as uow:
                assert uow.push_notification_configs is not None
                configs = uow.push_notification_configs.list_active_by_principal(
                    principal_id=tool_context.principal_id,
                )
                config_snapshots = [
                    (c.id, c.url, c.authentication_type, c.authentication_token, c.validation_token or "")
                    for c in configs
                ]

            configs_list = [
                TaskPushNotificationConfig(
                    id=snap_id,
                    task_id=params.task_id,
                    url=snap_url,
                    authentication=(
                        AuthenticationInfo(scheme=snap_auth_type, credentials=snap_auth_token)
                        if snap_auth_type and snap_auth_token
                        else None
                    ),
                    token=snap_validation_token,
                )
                for snap_id, snap_url, snap_auth_type, snap_auth_token, snap_validation_token in config_snapshots
            ]

            logger.info("Listed %s push notification configs for tenant %s", len(configs_list), tool_context.tenant_id)

            return ListTaskPushNotificationConfigsResponse(configs=configs_list)

        except A2AError:
            raise
        except Exception as e:
            record_boundary_error(
                "a2a",
                "list_push_notification_configs",
                e,
                tenant_id=tool_context.tenant_id if tool_context else None,
                principal_id=tool_context.principal_id if tool_context else None,
            )
            raise _internal_error_for("list push notification configs", e) from e

    async def on_delete_task_push_notification_config(
        self,
        params: DeleteTaskPushNotificationConfigRequest,
        context: ServerCallContext,
    ) -> None:
        """Handle delete push notification config requests.

        Marks a push notification configuration as inactive (soft delete).
        """
        tool_context = None
        try:
            auth_token = self._get_auth_token(context)
            if not auth_token:
                raise InvalidRequestError(message="Missing authentication token")
            identity = self._resolve_a2a_identity(auth_token, context=context)
            tool_context = self._make_tool_context(identity, "delete_push_notification_config")

            config_id = params.id
            if not config_id:
                raise InvalidParamsError(message="Missing required parameter: id")

            with PushNotificationConfigUoW(tool_context.tenant_id) as uow:
                assert uow.push_notification_configs is not None
                deleted = uow.push_notification_configs.soft_delete(
                    config_id,
                    principal_id=tool_context.principal_id,
                )
                if not deleted:
                    raise TaskNotFoundError(message=f"Push notification config not found: {config_id}")

            logger.info("Deleted push notification config: %s for tenant %s", config_id, tool_context.tenant_id)
            return None

        except A2AError:
            raise
        except Exception as e:
            record_boundary_error(
                "a2a",
                "delete_push_notification_config",
                e,
                tenant_id=tool_context.tenant_id if tool_context else None,
                principal_id=tool_context.principal_id if tool_context else None,
            )
            raise _internal_error_for("delete push notification config", e) from e

    async def on_get_extended_agent_card(
        self,
        params: GetExtendedAgentCardRequest,
        context: ServerCallContext,
    ) -> AgentCard:
        """Handle 'GetExtendedAgentCard' method."""
        raise UnsupportedOperationError(message="Extended agent card not supported")

    @staticmethod
    def _stamp_a2a_protocol_fields(response: AdCPBaseModel) -> dict[str, Any]:
        """Dump a Pydantic response and stamp the A2A protocol fields onto it.

        ``message`` and ``success`` are not spec fields on any response
        model — they are A2A transport-envelope markers (like MCP's
        ``task_id``/``adcp_version``; see
        ``tests/integration/test_harness_wire_response.py::ENVELOPE_MARKERS``),
        a deliberate A2A-binding deviation (#1868 review).
        ``success`` is derived from ``errors`` so a response carrying
        per-item errors reports ``success=False`` uniformly, regardless of
        which caller stamped it.

        Single point for this derivation — three sites used to duplicate it
        inline, and two of the three (the get_products explicit-skill and
        NL handlers, which need the dict pre-stamped before
        ``apply_version_compat`` sees it) omitted the errors-derivation
        entirely, always forcing ``success=True``.

        Args:
            response: Pydantic model from a skill handler.

        Returns:
            Dict with ``message``/``success`` stamped, ready for A2A.
        """
        response_data = response.model_dump(mode="json")
        response_data["message"] = str(response)

        # Derive success from errors field if present, default True otherwise
        if "errors" in response_data:
            response_data["success"] = not bool(response_data["errors"])
        else:
            response_data.setdefault("success", True)

        return response_data

    @staticmethod
    def _serialize_for_a2a(response: AdCPBaseModel | dict) -> dict[str, Any]:
        """Serialize a handler response for A2A protocol at the framework boundary.

        Single serialization point for all explicit-skill A2A responses.

        - Pydantic models: serialized via ``model_dump(mode="json")`` here,
          and the protocol fields (``message``, ``success``) are added via
          ``_stamp_a2a_protocol_fields``.
        - Dicts: passed through. Only skill handlers that pre-apply version
          compat (e.g., ``_handle_get_products_skill`` calls
          ``apply_version_compat`` and emits a dict already populated with
          ``message``/``success`` via ``_stamp_a2a_protocol_fields``) use
          this path. Error dicts that bypass the envelope contract were
          retired in this PR — NL handlers now raise typed ``AdCPSalesAgentError``
          instead.

        Args:
            response: Pydantic model OR pre-serialized dict from a skill
                handler.

        Returns:
            Dict ready for A2A DataPart.
        """
        if isinstance(response, dict):
            return response

        return AdCPRequestHandler._stamp_a2a_protocol_fields(response)

    async def _handle_explicit_skill(
        self,
        skill_name: str,
        parameters: dict,
        identity: ResolvedIdentity | None,
        push_config_registration: ValidatedWebhookRegistration | None = None,
    ) -> dict:
        """Handle explicit AdCP skill invocations.

        Maps skill names to appropriate handlers and validates parameters.
        Handlers return raw Pydantic models; serialization happens here at the boundary.

        Args:
            skill_name: The AdCP skill name (e.g., "get_products")
            parameters: Dictionary of skill-specific parameters
            identity: Pre-resolved identity from transport boundary
            push_config_registration: the ALREADY-ACCEPTED protocol-layer push config

        Returns:
            Dictionary containing the skill result

        Raises:
            ValueError: For unknown skills or invalid parameters
        """
        # Inject the protocol-layer push config into parameters for skills that need it.
        #
        # The TYPED model the seam already accepted, not a dict re-derived from the
        # protobuf. This used to re-serialize with MessageToDict and re-translate
        # A2A's singular ``scheme`` into AdCP's ``schemes`` array — a second dialect
        # for a config ``_accept_a2a_push_config`` had accepted moments earlier, and
        # the reason gh-#1299's exemption leaked: the dict was re-validated by the
        # skill's request body, where ``credentials`` minLength 32 applies and
        # DIVERTED THE CREATE. Passing the model means ``to_push_notification_config``
        # returns it unchanged (isinstance short-circuit), so the transport-layer
        # config is validated exactly once, at the transport boundary that owns it.
        if push_config_registration and skill_name in ("create_media_buy", "sync_creatives"):
            parameters = {**parameters, "push_notification_config": push_config_registration.config}
        # Normalize deprecated fields before any handler sees the parameters
        from src.core.request_compat import normalize_request_params

        compat_result = normalize_request_params(skill_name, parameters)
        parameters = compat_result.params

        logger.info("Handling explicit skill: %s with parameters: %s", skill_name, list(parameters.keys()))

        # Validate identity for non-discovery skills. Stay a JSON-RPC
        # InvalidRequestError (the skill never dispatches, so this is a
        # transport-channel rejection) but carry the two-layer envelope in
        # ``data``, which AdCP 3.1.1 names as the binding for a request rejected
        # before dispatch — docs/building/operating/transport-errors.mdx,
        # "Transport-Level Errors", and position 4 of its client detection order
        # (``error.data.adcp_error``). Without it the A2A wire carried a bare
        # JSON-RPC error and the buyer-facing code and suggestion that REST
        # returns were simply absent, which the test harness was papering over by
        # synthesizing an envelope production never sent (salesagent-pldmk.26).
        #
        # No identity / no principal_id resolved at all -> AUTH_MISSING per
        # v3.1.1 error-code.json. The code and its suggestion come from the
        # CODE_TABLE entry for ``AdCPAuthRequiredError``, never from a per-class
        # message/suggestion override (ADR-010) — which is why nothing is passed
        # to the constructor here. Same layering fix as the :282-283/:286-287
        # sites above, which were bare InvalidRequestErrors with no wire code at all.
        if skill_name not in DISCOVERY_SKILLS and (identity is None or not identity.principal_id):
            raise InvalidRequestError(
                message="Authentication required for skill invocation",
                data=build_two_layer_error_envelope(AdCPAuthRequiredError()),
            )

        # Map skill names to handlers. Handler signatures are heterogeneous
        # (discovery skills accept ``identity: ResolvedIdentity | None``; the rest
        # require non-None), so the dispatch is typed dynamically — the non-discovery
        # guard above enforces a non-None identity before the call.
        # Dispatch is DERIVED: TOOLS says which tools exist on A2A, and the handler for a
        # tool is ``_handle_{name}_skill`` on this class. There is no dict to keep in step --
        # a row with a2a=True is dispatchable, which is what makes TOOLS the single
        # declaration rather than a second one that can disagree with the card beside it.
        skill_handlers: dict[str, Callable[..., Awaitable[Any]]] = {
            name: getattr(self, f"_handle_{name}_skill")
            for name, spec in TOOLS.items()
            if spec.a2a and hasattr(self, f"_handle_{name}_skill")
        }

        if skill_name not in skill_handlers:
            available_skills = list(skill_handlers.keys())
            raise MethodNotFoundError(message=f"Unknown skill '{skill_name}'. Available skills: {available_skills}")

        try:
            handler = skill_handlers[skill_name]
            # Handlers return raw Pydantic models (or raise typed AdCPSalesAgentError on validation failure)
            result = await handler(parameters, identity)
            # Serialize at the boundary — models become dicts with protocol fields
            return self._serialize_for_a2a(result)
        except A2AError:
            # Re-raise A2AError as-is (already properly formatted)
            raise
        except (AdCPSalesAgentError, ValueError, PermissionError) as e:
            # Normalize ValueError/PermissionError to typed AdCPSalesAgentError via the
            # shared adcp_error_for() helper — same mapping the MCP
            # and REST boundaries apply. The outer dispatcher's `except
            # AdCPSalesAgentError` branch wraps the result into a failed Task with the
            # two-layer envelope.
            normalized = adcp_error_for(e)

            # Defensive about identity shape — test fixtures sometimes pass a
            # string or partially-built identity instead of ResolvedIdentity.
            # record_boundary_error handles None tenant_id internally.
            record_boundary_error(
                "a2a",
                skill_name,
                normalized,
                tenant_id=getattr(identity, "tenant_id", None),
                principal_id=getattr(identity, "principal_id", None) or "anonymous",
            )

            if normalized is not e:
                raise normalized from e
            raise
        # Untyped exceptions fall through to the dispatcher's `except Exception`
        # at the call site, which routes them through `_build_failed_skill_result`
        # for uniform envelope shape. No catch-all here.

    async def _handle_get_products_skill(self, parameters: dict, identity: ResolvedIdentity | None) -> Any:
        """Handle explicit get_products skill invocation.

        Aligned with adcp spec - brand must be a BrandReference dict.

        NOTE: Authentication is OPTIONAL for this endpoint. Access depends on tenant's
        brand_manifest_policy setting (public/require_brand/require_auth).
        """
        # The DTO is the accepted shape, so validating into it IS the selection -- the same
        # step REST and MCP take, from the same registry row. A hand-listed forward is the
        # shape that silently drops every field added later, and this one already named five
        # of the twenty-one fields the DTO declares.
        req = TOOLS["get_products"].validate(parameters)
        response = await invoke_tool("get_products", req, identity)

        # Apply v2 compat for pre-3.0 clients at the boundary
        from src.core.version_compat import apply_version_compat

        adcp_version = parameters.get("adcp_version")
        if isinstance(response, dict):
            response_data = response
        else:
            # Stamp protocol fields (message, success) before apply_version_compat
            # sees the dict, since a dict bypasses _serialize_for_a2a's own stamping.
            response_data = self._stamp_a2a_protocol_fields(response)
        return apply_version_compat("get_products", response_data, adcp_version)

    async def _handle_create_media_buy_skill(self, parameters: dict, identity: ResolvedIdentity) -> dict:
        """Handle explicit create_media_buy skill invocation.

        IMPORTANT: This handler ONLY accepts AdCP spec-compliant format:
        - packages[] (required) - each package must have budget
        - brand (required)
        - start_time (required)
        - end_time (required)

        Per AdCP v2.2.0 spec, budget is specified at the PACKAGE level, not top level.
        Legacy format (product_ids, total_budget, start_date, end_date) is NOT supported.
        """
        tool_context = self._make_tool_context(identity, "create_media_buy")

        # Parse parameters into typed request model (validation at A2A boundary)
        from src.core.schemas import CreateMediaBuyRequest

        # Pre-process: A2A field name translations
        params = {**parameters}
        if "custom_targeting" in params:
            params.setdefault("targeting_overlay", params.pop("custom_targeting"))
        # No server-minted defaults for buyer payload fields: a randomized
        # po_number would change the request's canonical idempotency hash, so an
        # identical A2A retry would reject as IDEMPOTENCY_CONFLICT instead of
        # replaying — and the stored payload would diverge from the same request
        # sent via MCP/REST (cross-transport parity). po_number stays None when
        # the buyer omits it, exactly like the other transports.
        # buyer_ref removed in adcp 3.12

        # push_notification_config is an A2A *transport-layer* parameter
        # (injected by _handle_explicit_skill from the SendMessageConfiguration).
        # It stays IN params so the builder puts it on the request like every other field.
        # It used to be popped out here and forwarded beside the request, so that the adcp
        # Authentication.credentials MinLen(32) constraint would not apply to the whole
        # create_media_buy (gh-#1299). That constraint now applies, deliberately: a payload
        # that does not conform to the schema is refused AT the schema rather than carried
        # past it. The bypass had one field announced by three separate mechanisms.

        # Normalize explicit brand through the shared coercion funnel (#1324).
        # to_brand_reference returns None only for None input (excluded above); every
        # other input returns BrandReference or raises typed AdCPValidationError.
        if params.get("brand") is not None:
            brand_ref = to_brand_reference(params["brand"])
            assert brand_ref is not None  # None only for None input; excluded by guard
            params["brand"] = brand_ref.model_dump(mode="json")

        # Validate required AdCP parameters (packages is optional in model but required by spec).
        # Raise typed AdCPValidationError so the outer dispatcher's `except AdCPSalesAgentError` branch
        # routes through `_build_failed_skill_result` -> `_build_error_envelope`, producing
        # the single two-layer envelope wire shape. Returning a custom dict here bypasses
        # the envelope builder and erases the real code on the buyer side.
        _require_params(params, ["brand", "packages", "start_time", "end_time"])

        # Validated for its rejection: a refusal here leaves the handler as a pydantic
        # ValidationError and the dispatcher gives it the same field + message +
        # buyer-facing suggestion every transport emits (AdCP POST-F3, #1417).
        # Validated for its rejection only: the values forwarded below are the wire values
        # (create_media_buy_raw re-validates them through this same model), so the model is
        # the boundary's gate rather than a container to pluck from.
        CreateMediaBuyRequest.model_validate(params)

        # Call core function with validated parameters and identity.
        # Per AdCP 3.1.1 (media-buy/package-update.json) targeting_overlay and budgets live on each
        # PackageRequest; only request-level spec fields are forwarded here.
        #
        # Selected off the TOOL rather than hand-listed. It named create_media_buy_raw until
        # the wrappers moved to taking the built request, whose signature would now select
        # nothing -- and it then named the builder, which is a second place to name the wrong
        # one. The ten-name list before that dropped `ext` and `paused` — both declared by
        # CreateMediaBuyRequest AND accepted by the builder, so both were honoured on MCP and
        # silently discarded on A2A. That is the same defect class as the missing
        # idempotency_key on update_media_buy; the cure is to stop enumerating.

        # Wrap for boundary-pattern consistency with delivery/sync_creatives. A crash is
        # structurally impossible here (create_media_buy_raw re-coerces via
        # CreateMediaBuyRequest), and to_account_reference is idempotent on an already
        # typed/dict account — but resolving at the boundary keeps all three handlers uniform.
        # The DTO is the accepted shape, so validating into it IS the selection.
        # Boundary-coerced values override the raw bag; everything else validates
        # straight into the DTO, which is the accepted shape.
        req = TOOLS["create_media_buy"].validate({**params, "account": to_account_reference(params.get("account"))})
        response = await invoke_tool("create_media_buy", req, identity)

        return response

    async def _handle_sync_creatives_skill(self, parameters: dict, identity: ResolvedIdentity) -> dict:
        """Handle explicit sync_creatives skill invocation (AdCP spec endpoint)."""
        # DEBUG: Log incoming parameters
        logger.info("[A2A sync_creatives] Received parameters keys: %s", list(parameters.keys()))
        logger.info("[A2A sync_creatives] assignments param: %s", parameters.get("assignments"))
        logger.info("[A2A sync_creatives] creatives count: %s", len(parameters.get("creatives", [])))

        # Create ToolContext from A2A auth info and resolve identity
        tool_context = self._make_tool_context(identity, "sync_creatives")

        # Map A2A parameters - creatives is required.
        # Raise typed AdCPValidationError so the outer dispatcher emits a two-layer envelope.
        if "creatives" not in parameters:
            raise AdCPValidationError()

        # Pass wire dicts THROUGH; do not pre-construct CreativeAsset here.
        # ``sync_creatives_raw`` declares ``list[CreativeAsset] | list[dict]`` for
        # exactly this reason: ``_sync_creatives_impl`` validates each entry
        # individually, which is what produces the per-creative partial-success
        # results this tool's contract promises. Building CreativeAsset(**c) at the
        # boundary hard-failed the WHOLE call on one malformed entry, so A2A alone
        # could not express a partial success -- and it was a third construction of
        # a request the other two transports build by one shared path.
        #
        # The legacy format_id upgrade stays -- it is a wire-compatibility rewrite of
        # a field's shape (a bare string, or a dict with no agent_url, both of which
        # the library CreativeAsset rejects outright) -- but it is dumped straight
        # back to a wire dict. upgrade_legacy_format_id returns OUR FormatId
        # subclass, and pydantic does not re-validate a model instance that already
        # satisfies the annotation, so handing that instance on made A2A the only
        # transport whose CreativeAsset.format_id was a different CLASS. Pydantic v2
        # equality is class-sensitive, so the registry match in _processing then
        # found nothing and every generative creative was written as a plain static
        # asset with no error. Dumping keeps the rewrite and
        # leaves the request identical to the one MCP and REST build.
        from src.core.format_cache import upgrade_legacy_format_id

        creatives = [
            {**c, "format_id": upgrade_legacy_format_id(c["format_id"]).model_dump(mode="json")}
            if isinstance(c, dict) and "format_id" in c
            else c
            for c in parameters["creatives"]
        ]

        ctx_param = parameters.get("context")
        context = ContextObject(**ctx_param) if isinstance(ctx_param, dict) else ctx_param

        # Call core function with spec-compliant parameters (AdCP 2.5: full upsert
        # semantics, patch parameter removed).
        #
        # Selected off the TOOL rather than hand-listed (it named sync_creatives_raw until
        # the wrappers moved to taking the built request): the set forwarded is "the DTO's
        # fields INTERSECT the builder's parameters", the same set MCP advertises and read
        # from the same lookup, so a field added to the DTO and the builder cannot reach one
        # transport and not another (which is how idempotency_key -- AdCP 3.1.1 /required --
        # was lost here until it was hand-added back).
        #
        # Three fields are set AFTER selection because they need boundary coercion the raw
        # bag cannot carry: `creatives` (legacy format_id upgraded above), `context` (typed
        # ContextObject) and `account` (typed AccountReference).

        # The DTO is the accepted shape, so validating into it IS the selection.
        # Boundary-coerced values override the raw bag; everything else validates
        # straight into the DTO, which is the accepted shape.
        req = TOOLS["sync_creatives"].validate(
            {
                **parameters,
                "creatives": creatives,
                "context": context,
                "account": to_account_reference(parameters.get("account")),
            }
        )
        response = await invoke_tool("sync_creatives", req, identity)

        return response

    async def _handle_list_creatives_skill(self, parameters: dict, identity: ResolvedIdentity) -> dict:
        """Handle explicit list_creatives skill invocation (AdCP spec endpoint)."""
        # Create ToolContext from A2A auth info and resolve identity
        tool_context = self._make_tool_context(identity, "list_creatives")

        # Structured AdCP CreativeFilters (statuses, concept_ids, format_ids, …)
        # arrive over the wire as a JSON dict; coerce to the typed model the core
        # function expects so they are honoured rather than dropped. Invalid filters
        # raise AdCPValidationError (VALIDATION_ERROR + suggestion) via the shared helper.
        filters = coerce_creative_filters(parameters.get("filters"))

        # Call core function with optional parameters (fixing original validation bug)
        # Selected off the TOOL rather than hand-listed. The 20-name list this replaces is the
        # shape that silently drops every field added later, which is how an A2A buyer's
        # media_buy_ids came to be ignored (a recorded gap row 11). It named list_creatives_raw
        # when it was written; the wrapper takes the built request now, so intersecting with IT
        # would select nothing -- which is exactly the choice no site should be making, and
        # REST's ListCreativesBody now reads the same seam off the same tool.
        # `filters` is set explicitly AFTER selection because it needs typed coercion
        # (invalid filters must raise AdCPValidationError, not reach the impl as a dict).

        # The DTO is the accepted shape, so validating into it IS the selection.
        # Boundary-coerced values override the raw bag; everything else validates
        # straight into the DTO, which is the accepted shape.
        req = TOOLS["list_creatives"].validate({**parameters, "filters": filters})
        response = await invoke_tool("list_creatives", req, identity)

        return response

    async def _handle_get_adcp_capabilities_skill(self, parameters: dict, identity: ResolvedIdentity | None) -> Any:
        """Handle explicit get_adcp_capabilities skill invocation (CRITICAL AdCP discovery endpoint).

        NOTE: Authentication is OPTIONAL for this endpoint since it returns public discovery data.
        Returns agent capabilities including supported protocols, targeting, and portfolio info.
        """
        # Identity already resolved at transport boundary (on_message_send)

        # Import and call the core implementation

        # Consume the parameter bag wholesale rather than naming each field: a handler
        # that enumerates is the shape that silently drops every field added later --
        # which is exactly how `ext` went missing here (a recorded gap Lane D).
        # adcp_version / adcp_major_version are forwarded EXPLICITLY: select_request_fields
        # strips the version-envelope pair by design (a REST body defaults adcp_version to
        # "1.0.0", which the envelope pattern rejects), but for THIS tool they are real
        # request data -- they drive version negotiation and the unsupported-version
        # advisory. Selecting alone would silently disable that negotiation.
        # The DTO is the accepted shape, so validating into it IS the selection. The version
        # envelope no longer needs re-adding by hand: it was stripped by the selection, and
        # every DTO now inherits adcp_version / adcp_major_version from the SDK request model.
        req = TOOLS["get_adcp_capabilities"].validate(parameters)
        response = await invoke_tool("get_adcp_capabilities", req, identity)

        return response

    async def _handle_list_creative_formats_skill(self, parameters: dict, identity: ResolvedIdentity | None) -> Any:
        """Handle explicit list_creative_formats skill invocation (CRITICAL AdCP endpoint).

        NOTE: Authentication is OPTIONAL for this endpoint since it returns public discovery data.
        """
        # Identity already resolved at transport boundary (on_message_send)

        # Build request from parameters (all optional).

        # Selected off the TOOL rather than hand-listed: the 13-name list this
        # replaces already dropped ext, pagination, property_id and publisher_domain,
        # all of which ListCreativeFormatsRequest declares (a recorded gap Lane D).
        # The DTO is the accepted shape, so validating into it IS the selection.
        req = TOOLS["list_creative_formats"].validate(parameters)

        # Call core function with identity
        response = await invoke_tool("list_creative_formats", req, identity)

        return response

    async def _handle_list_accounts_skill(self, parameters: dict, identity: ResolvedIdentity | None) -> Any:
        """Handle explicit list_accounts skill invocation.

        Authentication is OPTIONAL per BR-RULE-055 — unauthenticated calls
        return an empty account list.
        """

        # The DTO is the accepted shape, so validating into it IS the selection.
        request = TOOLS["list_accounts"].validate(parameters)
        return await invoke_tool("list_accounts", request, identity)

    async def _handle_sync_accounts_skill(self, parameters: dict, identity: ResolvedIdentity | None) -> Any:
        """Handle explicit sync_accounts skill invocation.

        Authentication is REQUIRED per BR-RULE-055.
        """

        # The DTO is the accepted shape, so validating into it IS the selection.
        request = TOOLS["sync_accounts"].validate(parameters)
        return await invoke_tool("sync_accounts", request, identity)

    async def _handle_update_media_buy_skill(self, parameters: dict, identity: ResolvedIdentity) -> dict:
        """Handle explicit update_media_buy skill invocation (CRITICAL for campaign management)."""
        # Identity already resolved at transport boundary (on_message_send)

        # Parse parameters into typed request model (validation at A2A boundary)

        # Pre-process: support legacy 'updates.packages' → 'packages'
        params = {**parameters}
        if "packages" not in params and "updates" in params:
            legacy_updates = params.pop("updates")
            if isinstance(legacy_updates, dict) and "packages" in legacy_updates:
                params["packages"] = legacy_updates["packages"]

        # media_buy_id is required. Raise typed AdCPValidationError so the dispatcher
        # routes it through the two-layer envelope, matching the create_media_buy skill.
        if "media_buy_id" not in params:
            raise AdCPValidationError()

        # Validate top-level fields via typed model (packages validated by _raw
        # which handles legacy formats with extra fields like 'status')
        # Selected off the DTO, not hand-listed. The seven-name list this replaces omitted
        # `account` and `idempotency_key` until they were noticed and hand-added back, while
        # sitting directly above a comment praising the SELECTED half of this same function
        # for not hand-listing: the two halves of one function disagreed, which is the whole
        # argument for having one rule.
        #
        # `packages` is the ONE documented exception and is excluded from the gate on
        # purpose: it carries legacy shapes (extra keys like `status`) that
        # update_media_buy_raw normalises downstream, so validating it here would reject
        # requests the tool accepts. It is still FORWARDED below — excluded from the
        # validation gate, not from the request.
        validation_bag = select_request_fields(UpdateMediaBuyRequest, params, None)
        validation_bag.pop("packages", None)
        req = UpdateMediaBuyRequest.model_validate(validation_bag)

        # Selected off the TOOL rather than hand-listed. The
        # eight-name list this replaces silently dropped currency, daily_budget, ext,
        # flight_start_date, flight_end_date, idempotency_key and pacing -- all accepted on
        # MCP and REST. idempotency_key is the costly one: AdCP 3.1.1 puts it in
        # update-media-buy-request.json /required, so a spec-conformant A2A buyer's
        # at-most-once key was being discarded, the same defect class as .
        # media_buy_id comes from the validated model; the rest of the bag is selected.

        # The DTO is the accepted shape, so validating into it IS the selection.
        # Boundary-coerced values override the raw bag; everything else validates
        # straight into the DTO, which is the accepted shape.
        built = TOOLS["update_media_buy"].validate({**params, "media_buy_id": req.media_buy_id or ""})
        response = await invoke_tool("update_media_buy", built, identity)

        return response

    async def _handle_get_media_buys_skill(self, parameters: dict, identity: ResolvedIdentity) -> Any:
        """Handle get_media_buys skill invocation.

        Builds through the SHARED builder and hands the wrapper the built request, like REST
        and MCP. ``include_snapshot`` travels IN the request now -- it is a GetMediaBuysRequest
        field, and popping it out here was how this transport came to carry it separately.
        """
        from src.core.schemas import GetMediaBuysRequest

        GetMediaBuysRequest.model_validate(parameters)
        # The DTO is the accepted shape, so validating into it IS the selection.
        req = TOOLS["get_media_buys"].validate(parameters)
        return await invoke_tool("get_media_buys", req, identity)

    async def _handle_get_media_buy_delivery_skill(self, parameters: dict, identity: ResolvedIdentity) -> dict:
        """Handle explicit get_media_buy_delivery skill invocation (CRITICAL for monitoring).

        Per AdCP spec, all parameters are optional:
        - media_buy_ids (plural, per AdCP v1.6.0 spec) or media_buy_id (singular, legacy)
        - status_filter: Filter by status (active, pending, paused, completed, failed, all)
        - start_date: Start date for reporting period (YYYY-MM-DD)
        - end_date: End date for reporting period (YYYY-MM-DD)

        When no media_buy_ids are provided, returns delivery data for all media buys
        the requester has access to, filtered by the provided criteria.
        """
        # Identity already resolved at transport boundary (on_message_send)

        # Parse parameters into typed request model (validation at A2A boundary)
        # Pre-process: support singular media_buy_id (legacy) → media_buy_ids (spec)
        from src.core.schemas import GetMediaBuyDeliveryRequest

        params = {**parameters}
        if "media_buy_ids" not in params and "media_buy_id" in params:
            params["media_buy_ids"] = [params.pop("media_buy_id")]

        # Builds through the SHARED builder and hands the wrapper the built request -- the
        # same two steps REST and MCP take. Selection is against the TOOL's own seam:
        # the nine-name list this replaces once dropped reporting_dimensions,
        # attribution_window, include_package_daily_breakdown and account, silently
        # discarding the buyer's requested attribution window (gh-#1299 follow-up).
        # Deriving the field set makes that class of omission structurally impossible.
        # Raw values are forwarded for everything the builder coerces itself
        # (status_filter str→MediaBuyStatus, dates, the dimension/window objects).
        # The DTO is the accepted shape, so validating into it IS the selection. This used
        # to validate, then re-narrow through select_request_fields_for against the MCP
        # wrapper's parameter list, then rebuild -- three steps whose only effect was to
        # drop whatever that hand-written list happened to omit.
        req = GetMediaBuyDeliveryRequest.model_validate(params)
        response = await invoke_tool("get_media_buy_delivery", req, identity)

        return response

    def _extract_brand_name_from_query(self, query: str) -> str:
        """Extract or infer brand name from the user query.

        Used for backward compatibility with natural language queries.
        Extracts a brand name to populate brand (BrandReference) for adcp v3.6.0.
        """
        # Look for common patterns that might indicate the brand/offering
        query_lower = query.lower()

        # If the query mentions specific brands or products, use those
        if "advertise" in query_lower or "promote" in query_lower:
            # Try to extract what they're promoting
            parts = query.split()
            for i, word in enumerate(parts):
                if word.lower() in ["advertise", "promote", "advertising", "promoting"]:
                    if i + 1 < len(parts):
                        # Take the next few words as the brand name
                        brand_parts = parts[i + 1 : i + 4]  # Take up to 3 words
                        brand_name = " ".join(brand_parts).strip(".,!?")
                        if len(brand_name) > 5:  # Make sure it's substantial
                            return f"Business promoting {brand_name}"

        # Default brand name based on query type
        if any(word in query_lower for word in ["video", "display", "banner", "ad"]):
            return "Brand advertising products and services"
        elif any(word in query_lower for word in ["coffee", "beverage", "food"]):
            return "Food and beverage company"
        elif any(word in query_lower for word in ["tech", "software", "app", "digital"]):
            return "Technology company digital products"
        else:
            # Generic fallback that should pass AdCP validation
            return "Business advertising products and services"

    async def _create_media_buy(self, request: str, identity: ResolvedIdentity | None) -> dict:
        """Natural-language create_media_buy is not supported; explicit skill is the spec contract.

        Always raises ``AdCPCapabilityNotSupportedError``. Buyer agents reach
        the explicit-skill path via ``create_media_buy`` skill invocation
        through ``_handle_explicit_skill`` — that path runs the full
        ``_create_media_buy_impl``, produces a spec-compliant Pydantic
        response, and goes through ``_serialize_for_a2a``.

        The previous NL stub returned a flat ``{"success": False, "message": "...
        use explicit skill"}`` dict that bypassed the two-layer-envelope
        contract — storyboard runners parsing that artifact synthesized
        ``MCP_ERROR`` rather than seeing the real wire code. Raising here
        flows to the outer ``on_message_send`` error handler which attaches
        the proper two-layer envelope to the failed Task artifact.
        """
        raise AdCPCapabilityNotSupportedError()


def _derived_skills() -> list[AgentSkill]:
    """The agent card's skills, generated from :data:`TOOLS`.

    ``id`` and ``name`` are the tool name -- a REST route, an MCP tool and an A2A skill for
    one tool carry one name, so there is nothing here that could diverge from the other two
    transports. ``description`` comes from the pinned SDK, the same source MCP registration
    reads. ``tags`` come off the DTO (``DTO.TAGS``): the SDK carries none, so they are ours,
    but they describe the tool's shape like the field descriptions beside them rather than
    its wiring -- so they sit with the shape, not in the registry.

    A tool whose DTO declares no TAGS contributes none. That is not an omission to fix: the
    three task tools have never been on A2A, so nobody has written tags for them, and
    inventing some here would be a declaration this file is not entitled to make.
    """
    descriptions = {d["name"]: d["description"] for d in ADCP_TOOL_DEFINITIONS}
    return [
        AgentSkill(
            id=name,
            name=name,
            description=descriptions.get(name, (spec.impl.__doc__ or "").strip().split("\n")[0]),
            tags=list(getattr(spec.dto, "TAGS", ())),
        )
        for name, spec in TOOLS.items()
        if spec.a2a
    ]


def create_agent_card() -> AgentCard:
    """Create the agent card describing capabilities.

    Returns:
        AgentCard with Prebid Sales Agent capabilities
    """
    # Use configured domain for agent card
    # Note: This will be overridden dynamically in the endpoint handlers
    # Fallback to localhost if SALES_AGENT_DOMAIN not configured
    server_url = get_a2a_server_url() or "http://localhost:8091/a2a"

    from a2a.types import AgentCapabilities
    from adcp import get_adcp_spec_version

    # Get sales agent version from package metadata or pyproject.toml
    sales_agent_version = get_version()

    # Create AdCP extension (AdCP 2.5 spec)
    # As of adcp 2.12.1, get_adcp_spec_version() returns the protocol version (e.g., "2.5.0")
    # Previously it returned the schema version (e.g., "v1"), but this was fixed upstream
    protocol_version = get_adcp_spec_version()
    adcp_extension = AgentExtension(
        uri=f"https://adcontextprotocol.org/schemas/{protocol_version}/protocols/adcp-extension.json",
        description="AdCP protocol version and supported domains",
        params=_dict_to_struct(
            {
                "adcp_version": protocol_version,
                "protocols_supported": ["media_buy"],  # Only media_buy protocol is currently supported
            }
        ),
    )

    # Create the agent card with minimal required fields
    agent_card = AgentCard(
        name="Prebid Sales Agent",
        description="AI agent for programmatic advertising campaigns via AdCP protocol",
        version=sales_agent_version,
        supported_interfaces=[
            AgentInterface(url=server_url, protocol_version="1.0"),
        ],
        capabilities=AgentCapabilities(
            push_notifications=True,
            extensions=[adcp_extension],
        ),
        default_input_modes=["message"],
        default_output_modes=["message"],
        skills=_derived_skills(),
        documentation_url="https://github.com/your-org/adcp-sales-agent",
    )

    return agent_card


# Standalone execution removed — A2A is now integrated into the unified
# FastAPI app (src/app.py) via add_routes_to_app(). The AdCPRequestHandler
# and create_agent_card() are imported by src/app.py.
