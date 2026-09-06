#!/usr/bin/env python3
"""
Prebid Sales Agent A2A Server using official a2a-sdk library.
Supports both standard A2A message format and JSON-RPC 2.0.
"""

import json
import logging
import uuid
from collections.abc import AsyncGenerator

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
from adcp.types import GeneratedTaskStatus
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
                    # _serialize_for_a2a already stamped str(response) onto
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
                result = await self._dispatch_skill("get_products", {"brief": combined_text}, identity)
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
                result = await self._dispatch_skill("get_products", {"brief": combined_text}, identity)
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
                result = await self._dispatch_skill("get_adcp_capabilities", {}, identity)
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
    def _serialize_for_a2a(response: AdCPBaseModel | dict) -> dict[str, Any]:
        """Serialize a tool's response for A2A at the framework boundary.

        The single serialization point for every A2A skill response: the model dump, then the
        ``message``/``success`` stamp, in that order and nowhere else.

        ``message`` and ``success`` are not spec fields on any response model -- they are A2A
        transport-envelope markers (like MCP's ``task_id``/``adcp_version``; see
        ``tests/integration/test_harness_wire_response.py::ENVELOPE_MARKERS``), a deliberate
        A2A-binding deviation (#1868 review). ``success`` is derived from ``errors`` so a
        response carrying per-item errors reports ``success=False`` uniformly.

        A dict passes through unchanged. Nothing on the skill path produces one any more --
        the branch survives for callers holding a response built elsewhere.

        Args:
            response: Pydantic model returned by the tool, or an already-serialized dict.

        Returns:
            Dict ready for A2A DataPart.
        """
        if isinstance(response, dict):
            return response

        response_data = response.model_dump(mode="json")
        if "errors" in response_data:
            response_data["success"] = not bool(response_data["errors"])
        else:
            response_data.setdefault("success", True)
        return response_data

    async def _dispatch_skill(
        self,
        skill_name: str,
        parameters: dict,
        identity: ResolvedIdentity | None,
    ) -> dict[str, Any]:
        """Validate a parameter bag into the row's DTO, run the tool, serialize the answer.

        The whole of A2A's request path. Eleven ``_handle_<tool>_skill`` methods stood here,
        and what they had in common was these three lines; what they did NOT have in common was
        the defect. Each coerced its own parameters -- twelve call sites across
        ``to_account_reference``, ``to_brand_reference``, ``coerce_creative_filters``,
        ``upgrade_legacy_format_id`` and ``to_context_object`` -- and MCP and REST ran none of
        them, so the same bytes had two meanings. All of them are deleted.

        The coercions are gone rather than moved. Pydantic performs four of the five unaided on
        the plain dict a buyer sends, and the helpers were worse than redundant:
        ``_coerce_wire_object`` returns ``None`` for a non-dict, so where MCP and REST raised,
        A2A silently dropped -- and for the seven tools whose ``account`` is optional the
        request then proceeded with NO account scope, meaning no authorization against that
        account and a different idempotency scope. The genuine wire-compatibility rewrites
        moved to ``normalize_request_params``, which every transport shares.

        That normalizer runs HERE rather than in ``_handle_explicit_skill``, so the two natural
        language entry points take the same steps as an explicit skill invocation. This is A2A's
        whole request path, and a path that only some callers reach is the shape this change
        exists to remove.

        ``parameters`` is a plain JSON-shaped dict by the time it arrives: the A2A path is
        ``json_format.MessageToDict`` over a ``Struct``, never binary protobuf. The one Struct
        artifact is that it has no integer type, and pydantic's non-strict mode already coerces
        ``2.0`` to an ``int`` field.
        """
        response = await invoke_tool(skill_name, TOOLS[skill_name].validate(parameters), identity)
        return self._serialize_for_a2a(response)

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
        # Deprecated wire shapes are normalized in ``_dispatch_skill``, which is the one
        # place every A2A request passes through -- the NL entry points reach it too.
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

        # A row with ``a2a=True`` IS dispatchable. There is no second list and no per-tool
        # method: the registry says which tools this transport serves, and the card is derived
        # from the same rows, so the two cannot disagree. They used to -- a ``hasattr`` filter
        # over ``_handle_{name}_skill`` methods silently overrode the declaration, so
        # ``list_tasks``, ``get_task_status`` and ``complete_task`` appeared on the card and
        # answered ``MethodNotFoundError``.
        if skill_name not in TOOLS or not TOOLS[skill_name].a2a:
            available_skills = [name for name, spec in TOOLS.items() if spec.a2a]
            raise MethodNotFoundError(message=f"Unknown skill '{skill_name}'. Available skills: {available_skills}")

        try:
            return await self._dispatch_skill(skill_name, parameters, identity)
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
