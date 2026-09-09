"""
Protocol-level webhook delivery service for A2A/MCP push notifications.

This service handles protocol-level push notifications (operation status updates)
as distinct from application-level webhooks (scheduled reporting delivery).

Protocol-level webhooks are configured via:
- A2A: MessageSendConfiguration.pushNotificationConfig
- MCP: (future) protocol wrapper extension

Application-level webhooks are configured via:
- AdCP: CreateMediaBuyRequest.reporting_webhook
"""

import logging
import time
from collections.abc import Mapping
from typing import Any, Protocol, cast
from uuid import uuid4

from a2a.types import Task, TaskStatusUpdateEvent
from adcp import create_a2a_webhook_payload, create_mcp_webhook_payload
from adcp.types import McpWebhookPayload
from adcp.webhooks import GeneratedTaskStatus, generate_webhook_idempotency_key
from google.protobuf.json_format import MessageToDict
from pydantic import BaseModel as PydanticBaseModel

from src.core.audit_logger import get_audit_logger
from src.core.database.database_session import get_db_session
from src.core.security.webhook_egress import adeliver_webhook
from src.core.signing import WebhookAuthConfig, delivery_signer_for_tenant
from src.core.webhook_validator import validate_webhook_task_type, webhook_url_for_log
from src.core.webhooks.delivery import WebhookDeliveryOutcome, WebhookTaskContext
from src.services.webhook_conclusion import record_conclusion


class DeliverableWebhookTarget(WebhookAuthConfig, Protocol):
    """What this sender actually needs off a push-notification config: three fields.

    Structural, and READ-ONLY on purpose. Two kinds of object arrive here — the
    stored ORM ``PushNotificationConfig`` row, and the
    ``ValidatedWebhookRegistration`` value handed straight from the A2A protocol
    stash — and both satisfy this without either knowing about the other. Before
    this, the annotation named the ORM class, so the A2A path fabricated a
    detached row with ``tenant_id=""`` / ``principal_id=""`` purely to type-check:
    a config-shaped object with empty scope ids, which is exactly how an
    unreceipted config reached a sender.

    Declared as properties rather than plain attributes because a Protocol with
    mutable attributes is invariant, and would then REFUSE a frozen(slots)
    dataclass — the read-only form admits both. The three properties are not
    restated here: they ARE
    :class:`~src.core.signing.WebhookAuthConfig`, the shape
    the signing boundary reads off a registration, so this name is a local alias
    for that contract rather than a second copy of it. Restating them would put
    the same three-field document in two modules, and a value satisfying one but
    not the other would then be constructible.
    """


logger = logging.getLogger(__name__)

#: Per-attempt ceiling handed to the egress seam. Carried over verbatim from the
#: value the SDK sender used for this service (``webhook_sender_factory``'s
#: ``_TIMEOUT_SECONDS``), so routing through the seam changed no timeout.
#:
#: There is no backoff constant here any more. The retry LADDER — which statuses
#: are retryable, how long to wait, and when the budget is spent — moved with the
#: dial into ``outbound_http``'s ``Attempts``, and it is strictly better than the
#: local one it replaces: this service's loop treated every 4xx as terminal, so a
#: 429 with a ``Retry-After`` was reported as a permanent client error and never
#: retried. Keeping a second ladder here would be a second retry policy to keep in
#: step with that one.
_DELIVERY_TIMEOUT_SECONDS = 10.0


# FIXME(gh-#1299): behaviour-identical backport of adcp 5.4.0
# ``adcp.to_wire_dict`` + ``_normalize_a2a_task_state_to_v03`` (adcp #602).
# salesagent is pinned to adcp 4.3.0, which predates that public seam.
# Delete this block and call ``adcp.to_wire_dict()`` directly once salesagent
# bumps adcp to the version that ships it.
def _normalize_message_role(message: dict[str, Any]) -> None:
    """Rewrite a2a-sdk 1.0 ``ROLE_*`` to the A2A 0.3 lowercase wire form."""
    role = message.get("role")
    if isinstance(role, str) and role.startswith("ROLE_"):
        message["role"] = role[len("ROLE_") :].lower()


def _normalize_a2a_task_state_to_v03(payload: dict[str, Any]) -> None:
    """Rewrite a2a-sdk 1.0 ``TASK_STATE_*`` / ``ROLE_*`` enums to A2A 0.3
    lowercase wire strings in-place. Buyer receivers parse the 0.3 shape
    (``"state": "completed"``); the 1.0 protobuf JSON emitter produces
    ``"state": "TASK_STATE_COMPLETED"`` by default.
    """
    status = payload.get("status")
    if isinstance(status, dict):
        state = status.get("state")
        if isinstance(state, str) and state.startswith("TASK_STATE_"):
            # Spec uses hyphens for multi-word states (e.g. "auth-required").
            status["state"] = state[len("TASK_STATE_") :].lower().replace("_", "-")
        message = status.get("message")
        if isinstance(message, dict):
            _normalize_message_role(message)
    history = payload.get("history")
    if isinstance(history, list):
        for entry in history:
            if isinstance(entry, dict):
                _normalize_message_role(entry)
    if "role" in payload:
        _normalize_message_role(payload)


def _to_wire_dict(payload: Any) -> dict[str, Any]:
    """Serialize any AdCP webhook payload to a JSON-ready dict.

    Behaviour-identical backport of adcp 5.4.0 ``adcp.to_wire_dict``:

    * a2a ``Task`` / ``TaskStatusUpdateEvent`` (protobuf, a2a-sdk 1.0+) ->
      ``MessageToDict(preserving_proto_field_name=False)`` so JSON keys are
      the A2A wire camelCase (``id``, ``contextId``, ``taskId``), then enum
      values normalized from the 1.0 form (``TASK_STATE_COMPLETED``,
      ``ROLE_AGENT``) to the 0.3-spec lowercase form (``completed``,
      ``agent``).
    * Any Pydantic model (``McpWebhookPayload`` ...) ->
      ``model_dump(mode="json", exclude_none=True)``.
    * ``Mapping`` -> coerced to ``dict`` (legacy hand-built passthrough).
    """
    if isinstance(payload, (Task, TaskStatusUpdateEvent)):
        data: dict[str, Any] = MessageToDict(payload, preserving_proto_field_name=False)
        _normalize_a2a_task_state_to_v03(data)
        return data
    if hasattr(payload, "model_dump"):
        return cast(dict[str, Any], payload.model_dump(mode="json", exclude_none=True))
    if isinstance(payload, Mapping):
        return dict(payload)
    raise TypeError(
        f"Unsupported webhook payload type {type(payload).__name__}: expected "
        "a2a Task / TaskStatusUpdateEvent (protobuf), an AdCP Pydantic model "
        "(e.g. McpWebhookPayload), or a Mapping[str, Any]."
    )


class ProtocolWebhookService:
    """
    Service for sending protocol-level push notifications to clients.

    How a delivery is authenticated is NOT decided here. The receiver's own
    ``PushNotificationConfig`` row selects exactly one mode, and since
    salesagent-47n9 that selection is made by
    ``src.core.security.webhook_egress``'s three-arm match — legacy HMAC-SHA256,
    Bearer, or (selected by the ABSENCE of an ``authentication`` block, the pinned
    schema's own selector, security.mdx @ v3.1.1 :1424) the RFC 9421 profile. The
    key that arm signs with still comes from the one signing seam, reached through
    ``src.core.signing.delivery_signer_for_tenant``. This service owns delivery
    logging and the audit trail, and nothing else.

    Retry is NOT owned here either, not any more. The seam serializes once, signs
    those exact bytes ONCE PER ATTEMPT (an RFC 9421 ``nonce`` a conformant receiver
    must reject on replay makes a signature computed above a retry loop invalid on
    attempt two), dials, retries and reports ONE
    :class:`~src.core.webhooks.delivery.WebhookDeliveryOutcome`.

    It owns NO connection state. It used to hold one long-lived
    ``httpx.AsyncClient`` and donate it to the SDK sender so protocol notifications
    could keep a pool across deliveries; that pool is gone (#1802). A donated client
    is trusted completely by ``adcp``'s ``WebhookSender`` — the SDK skips its own
    resolve-validate-and-pin step whenever one is supplied — so a client shared
    across destinations meant every protocol webhook went out with NO address check
    at all once the send-time validator was deleted in favour of the egress seam.
    Pinning is per-destination by definition: a pool that outlives one destination
    cannot carry a pin for the next.

    Each delivery therefore builds a transport pinned to its own destination and
    discards it — inside ``outbound_http.asend``, one transport per call, never
    cached. There is nothing left to close, and nothing left that COULD be held:
    this module imports no HTTP client at all (``ruff-egress.toml`` bans ``httpx``
    in ``src/``), so "owns no connection state" is a property of the import graph
    rather than a rule someone has to keep remembering.
    """

    async def notify(
        self,
        push_notification_config: DeliverableWebhookTarget,
        *,
        task: WebhookTaskContext,
        status: GeneratedTaskStatus,
        result: PydanticBaseModel | dict[str, Any],
        protocol: str,
        context_id: str = "",
    ) -> bool:
        """Deliver one protocol notification from VALUES, choosing the dialect here.

        THE delivery entry point. Every sender used to re-derive the same two
        decisions at its own call site: which payload builder to call
        (``create_a2a_webhook_payload`` vs ``create_mcp_webhook_payload``, forked
        on ``protocol``), and what to put in a free-form ``metadata`` dict. Seven
        files forked the dialect and six built the dict, which is how
        ``delivery_webhook_scheduler`` came to import only the MCP builder — a
        buyer registered over A2A receives an MCP-shaped delivery report from it.

        Taking a typed :class:`WebhookTaskContext` instead of ``metadata:
        dict[str, Any]`` is what closes the other half. ``records_delivery_log``
        needs ``tenant_id`` and ``principal_id``; the admin sender passed
        ``{"task_type": ...}`` alone, so admin-originated deliveries wrote no
        ``webhook_delivery_log`` row and said nothing about it. A caller now has
        to name those fields to construct the context, so omitting one is a
        visible decision at the call site rather than an absence in a dict.

        The dialect is selected ONCE, here, from ``protocol``. A caller passes
        values and cannot choose a builder.
        """
        payload: Task | TaskStatusUpdateEvent | McpWebhookPayload
        if protocol == "a2a":
            payload = create_a2a_webhook_payload(
                task_id=task.task_id,
                status=status,
                result=result,
                context_id=context_id,
            )
        else:
            payload = create_mcp_webhook_payload(
                task_id=task.task_id,
                status=status,
                task_type=validate_webhook_task_type(task.task_type or ""),
                result=result,
            )

        return await self.send_notification(
            push_notification_config=push_notification_config,
            payload=payload,
            task=task,
        )

    async def send_notification(
        self,
        push_notification_config: DeliverableWebhookTarget,
        payload: Task | TaskStatusUpdateEvent | McpWebhookPayload,
        task: WebhookTaskContext,
    ) -> bool:
        """
        Send a protocol-level push notification to the configured webhook.

        Args:
            push_notification_config: Push notification configuration from protocol layer
            payload: For A2A it can be Task or TaskStatusUpdateEvent types for MCP it wil be McpWebhookPayload.
                Use create_a2a_webhook_payload or create_mcp_webhook_payload from adcp's official python client to get the payload for particular task and status
            task: The delivery's task identity, typed. Threaded through to the
                logger unchanged -- it used to be flattened to a loose dict here
                and rebuilt from the PAYLOAD downstream, which silently reset
                sequence_number to 1 and notification_type to None on every row
                the payload did not happen to carry them in.

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not push_notification_config or not push_notification_config.url:
            # TODO: @yusuf - Double check logging actually works for Task, TaskStatusUpdateEvent and McpWebhookPayload types
            logger.debug(
                f"No webhook URL configured in the push notification. Here's payload: {payload}, skipping notification"
            )
            return False

        # The buyer's URL is delivered verbatim, and this function decides NOTHING
        # about the destination. Test stacks that need a reachable callback register
        # a reachable hostname instead — the e2e stack runs a long-lived
        # webhook-capture service behind the shared TLS front (see
        # tests/e2e/webhook_capture_service.py).
        #
        # No separate send-time SSRF gate here (#1697 added one in front of the old
        # requests.Session POST, and it is deleted along with
        # ``reject_unsafe_outbound_webhook_url`` itself). The pre-connection check
        # inside the delivery act IS that gate and strictly more: the egress seam
        # dials on a transport ``outbound_http`` builds PER DESTINATION and never
        # caches, which resolves the host, runs the full reserved/private/metadata
        # refusal, enforces the scheme and port policy and then PINS the socket to
        # the address it validated — so the resolve-then-connect rebinding window a
        # separate validator leaves open does not exist. It also refuses BEFORE any
        # request object is built, so on that path the signer is never invoked and a
        # hostile URL never causes a signature to be computed. Re-validating here
        # would be a second copy of address policy, which is what deleting the
        # hand-rolled validator (formerly src/core/security/url_validator.py; the
        # shared predicate now lives in src/core/security/egress/policy.py) was for.
        #
        # There is no rewrite hop either: one used to swap ``localhost`` for
        # ``host.docker.internal``, so the gate approved one destination and the
        # process dialled another the gate refuses, making the gate advisory. It
        # matters for signing too — ``@target-uri`` and ``@authority`` are covered
        # components of the RFC 9421 signature, so the signed URI is the registered
        # one rather than a post-rewrite variant.
        url = push_notification_config.url

        # Content-Type is the sender's (it frames the body it serialized), and the
        # auth headers are the boundary's. Only genuinely extra headers go here.
        #
        # It is load-bearing rather than decoration now that the seam transmits
        # ``content=`` bytes: httpx sets no Content-Type of its own on that path,
        # while ``JwkSignerStrategy`` covers the ``content-type`` component — so it
        # ships here or the signature covers a header that never left, which a
        # conformant verifier rejects with
        # ``webhook_signature_components_incomplete`` (security.mdx @ v3.1.1 :1476).
        # ``application/json`` is the ONE spelling the 9421 arm accepts; the seam
        # refuses any other value loudly rather than signing a lie.
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AdCP-Sales-Agent/1.0",
        }

        # Log sanitized config (exclude sensitive authentication_token)
        safe_config = {
            "url": push_notification_config.url if hasattr(push_notification_config, "url") else None,
            "authentication_type": (
                push_notification_config.authentication_type
                if hasattr(push_notification_config, "authentication_type")
                else None
            ),
            # DO NOT log authentication_token - security risk
        }
        logger.info(f"push_notification_config (sanitized): {safe_config}")

        # Serialize payload to dict at the delivery boundary (for HMAC signing
        # and JSON send). Single seam: a2a protobuf -> camelCase + A2A 0.3
        # lowercase enum values; Pydantic -> model_dump; Mapping -> dict.
        payload_dict: dict[str, Any] = _to_wire_dict(payload)

        # No authentication decision here. The registration travels whole down to
        # ``_deliver``, which hands the egress seam the stored PRIMITIVES it takes;
        # the seam decides ONE mode from them — RFC 9421 by default, legacy
        # HMAC-SHA256 or Bearer only when the buyer explicitly registered one — the
        # same decision, made the same way, for every sender. This function used to
        # resolve it, project it into a secret-or-header and sign inline, which is
        # how it became the only sender that silently dropped a stored Basic row.
        # The config stays whole down to that one call site rather than being split
        # into a scheme/credential pair here: splitting it early would put the pluck
        # back at every intermediate frame, and what a delivery reads off a
        # registration is exactly the three fields ``DeliverableWebhookTarget``
        # names.
        # Send notification with logging; the seam owns the retry ladder.
        return await self._send_with_retry_and_logging(
            url=url,
            payload=payload_dict,
            headers=headers,
            task=task,
            config=push_notification_config,
        )

    def _conclude(
        self,
        *,
        ctx: WebhookTaskContext,
        log_id: str,
        url: str,
        outcome: WebhookDeliveryOutcome,
        start_time: float,
        audit_logger: Any,
    ) -> bool:
        """Book one delivery: the row, the audit entry, and the bool the caller gets.

        THE single conclusion for this sender. Every arm — refused destination,
        client error, exhausted retries, an unexpected exception, and success —
        ends here, because a refusal, a failure and a delivery differ only in
        what they KNOW (attempts, status, wording), not in what they must record.
        An arm that concludes on its own is an arm that can be written without
        recording anything, which for a refusal means a misconfigured destination
        leaving no trace at all — the absence lane salesagent-gra7.1 closes.

        The outcome IS the conclusion: the returned bool is derived from it, not
        decided here, and the row is written from it rather than from arguments
        each arm re-derived.
        """
        response_time_ms = int((time.time() - start_time) * 1000)

        # Persistence is observability; it does not get a vote on delivery. A DB
        # error must not propagate out of a function contracted ``-> bool`` and
        # turn a webhook that WAS delivered into a failure (and, upstream, into a
        # retry). The swallow used to live at the write helper; it lives at the
        # one conclusion now, which is the only place it is needed.
        # Gated on the ELIGIBILITY property, not merely on tenant_id: record_outcome
        # is a no-op for an ineligible ctx, so gating any wider would check out a
        # session and commit an empty transaction for every task status update this
        # sender fires — a per-webhook round trip that did not exist before.
        if ctx.records_delivery_log:
            # records_delivery_log already requires tenant_id truthy; the assert
            # only narrows mypy's view from str | None to str and can never fire.
            assert ctx.tenant_id
            try:
                with get_db_session() as session:
                    record_conclusion(
                        session,
                        tenant_id=ctx.tenant_id,
                        ctx=ctx,
                        log_id=log_id,
                        webhook_url=url,
                        outcome=outcome,
                        response_time_ms=response_time_ms,
                    )
            except Exception as e:
                logger.error(f"Failed to write webhook delivery log: {e}")

        if audit_logger:
            if outcome.kind == "delivered":
                audit_logger.log_success(
                    f"{ctx.task_type} webhook delivered successfully (sequence #{ctx.sequence_number}, "
                    f"{response_time_ms}ms, {outcome.payload_size_bytes or 0} bytes)"
                )
            else:
                audit_logger.log_warning(
                    f"{ctx.task_type} webhook failed for task {ctx.task_id}: {outcome.detail or outcome.kind}"
                )

        return outcome.kind == "delivered"

    async def _send_with_retry_and_logging(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict,
        task: WebhookTaskContext,
        config: DeliverableWebhookTarget | None = None,
        max_attempts: int = 3,
    ) -> bool:
        """Deliver one webhook through the signing boundary, with logging and audit trail.

        This function never serializes ``payload``. The boundary serializes it
        ONCE, signs those exact bytes, and transmits those exact bytes with
        ``content=`` — the single act #1441 exists to keep single. A second
        ``json.dumps`` here would be a second serialization that could disagree
        with the signed one.
        """
        # The caller's typed context, used as given. It used to be rebuilt here
        # from a four-key dict plus the payload, and the rebuild was lossy in both
        # directions that mattered: as_metadata never emitted sequence_number or
        # notification_type, and from_metadata recovered them from the PAYLOAD's
        # result -- so a payload that did not carry them yielded 1 and None, and
        # those were the values PERSISTED to webhook_delivery_log. A buyer reading
        # the log saw a webhook claiming to be first in its sequence and carrying
        # no notification type, when the server had sent the seventh and marked it
        # final.
        ctx = task

        # Create webhook delivery log entry
        log_id = str(uuid4())
        start_time = time.time()

        # ONE key per distinct event, reused across this event's retries — a fresh
        # one per attempt would defeat the receiver's dedup (adcp webhooks.mdx).
        idempotency_key = generate_webhook_idempotency_key()

        # Log to audit system (start)
        audit_logger = None
        if ctx.tenant_id:
            audit_logger = get_audit_logger("webhook", ctx.tenant_id)
            audit_logger.log_info(
                f"Sending {ctx.task_type} webhook for task {ctx.task_id} (sequence #{ctx.sequence_number})"
            )

        # ONE call through the egress seam, which is where authentication,
        # serialization, signing, the dial and the retry ladder are a single act.
        # Nothing about the destination is decided here.
        #
        # No client is passed anywhere, and that is the security property this call
        # depends on. The seam takes a per-attempt ``sign`` CALLBACK instead of a
        # client precisely so a signing caller never receives something it could
        # point elsewhere: it builds a transport for THIS destination — resolve, run
        # the full reserved/private/metadata refusal, enforce the scheme and port
        # policy, pin the socket to the validated address, refuse redirects — and it
        # refuses before any request object exists, so the signature is computed only
        # for a destination already accepted. A pin is per-destination by
        # construction, so nothing connection-shaped may outlive this call: the
        # long-lived pool that used to live on this service made every protocol
        # webhook skip that check.
        #
        # The redirect refusal is what #1697 reached for with ``allow_redirects=False``:
        # a 302 toward metadata or a private address cannot carry us past the
        # validated destination.
        #
        # No ``field=``: the URL is read back out of a stored PushNotificationConfig,
        # not off a request document a buyer just sent — the buyer-actionable
        # refusal already happened at ingest (src/core/webhook_validator.py, reject_unsafe_webhook_registration_url).
        #
        # The URL is logged sanitized (scheme://host/path): a buyer's webhook URL
        # may carry credentials in userinfo or a token in the query string, and a
        # log line is the one place they would sit in cleartext (#1697).
        logger.info("Sending webhook for task %s to %s", ctx.task_id, webhook_url_for_log(url))
        try:
            outcome = await self._deliver(
                url=url,
                payload=payload,
                headers=headers,
                idempotency_key=idempotency_key,
                config=config,
                tenant_id=ctx.tenant_id,
                max_attempts=max_attempts,
            )
        except Exception as e:
            # Deliberately kept, and it carries MORE weight after the rewire. The
            # seam maps its own failure taxonomy onto the outcome, so nothing it
            # raises lands here — but two things still can, and neither may escape a
            # function contracted ``-> bool`` into a delivery scheduler that
            # re-raises what it catches. The pinned transport's own wrong-host guard
            # raises a bare RuntimeError; and a tenant that CAN sign but cannot
            # honestly resolve its material raises out of
            # ``delivery_signer_for_tenant`` BEFORE the seam is called at all. The second is the fail-closed half of
            # "never downgrade to unsigned": it lands here as an ``unexpected``
            # outcome with zero attempts, which is the literal truth — nothing was
            # serialized, nothing was dialled — and it is RECORDED (delivery-log row
            # plus audit warning) rather than logged and forgotten.
            logger.error(f"Unexpected error sending webhook for task {ctx.task_id}: {e}", exc_info=True)
            # Nothing reached the wire, and no outcome kind covers a NON-transport
            # failure — so this arm builds the one it means: exhausted with zero
            # attempts. The arm no longer decides what gets recorded; it only says
            # what became of the delivery, and the epilogue books it.
            return self._conclude(
                ctx=ctx,
                log_id=log_id,
                url=url,
                outcome=WebhookDeliveryOutcome.unexpected(type(e).__name__),
                start_time=start_time,
                audit_logger=audit_logger,
            )

        if outcome.kind == "refused_auth":
            # FAIL-CLOSED. This used to fall through to an unsigned delivery: the
            # buyer asked for authentication and received none, with no error on any
            # surface. log-and-return, and NO delivery-log row and no audit entry —
            # nothing was attempted, so a row claiming an attempt would misreport a
            # refusal as a delivery that failed on the wire. The refusal a buyer can
            # act on already happened at ingest.
            #
            # It still concludes through the epilogue, so this arm cannot be the one
            # that forgets to. Both absences survive the move and are the RULING,
            # not an oversight: record_outcome maps no status for ``refused_auth``
            # (so no row), and _conclude is passed no audit_logger (so no entry).
            #
            # REACHABLE as of this rewire, where before it was not. While delivery
            # went through ``webhook_sender_factory``, an unusable legacy pair was
            # answered by ``legacy_auth_mode`` with LEGACY_UNCREDENTIALED — an
            # UNSIGNED delivery plus a loud warning — and no code path could produce
            # ``refused_auth`` for this sender at all. The egress seam decides it
            # differently and emits the refusal: ``_authentication_or_refusal``
            # constructs the PINNED ``Authentication`` type from the stored pair, and
            # every way that construction fails is an outcome, not a downgrade —
            # ``no_credentials`` (a scheme with no credential), ``credentials_too_short``
            # (under the spec's ``minLength: 32``), ``scheme_not_in_spec``
            # (e.g. a stored ``basic`` row, or the wrong casing), ``multi_scheme``,
            # and ``no_scheme`` (a credential stored with no scheme). Each returns
            # ``kind="refused_auth"`` with ``attempts=0`` before anything is
            # serialized, so this arm now books real refusals instead of standing by
            # for one. That is the point of the rewire: a buyer who asked for an
            # authentication this seller cannot conformantly produce gets no
            # delivery, rather than an unauthenticated POST it can neither verify nor
            # attribute.
            logger.error(
                "Refusing to send webhook for task %s to %s: %s",
                ctx.task_id,
                webhook_url_for_log(url),
                outcome.detail or outcome.reason,
            )
            return self._conclude(
                ctx=ctx,
                log_id=log_id,
                url=url,
                outcome=outcome,
                start_time=start_time,
                audit_logger=None,
            )

        if outcome.kind == "refused_destination":
            # Refused before a connection was opened. It still writes a row and an
            # audit entry — a misconfigured destination that leaves no trace is
            # indistinguishable from one nobody configured. The honest attempt count
            # (0) and the ``refused`` spelling are the recorder's, not this arm's.
            # Severity carried on the outcome, not chosen here (salesagent-pldmk.39).
            logger.log(outcome.log_level, f"Webhook for task {ctx.task_id} was refused by egress policy")
        elif outcome.kind != "delivered":
            logger.error(
                f"Webhook for task {ctx.task_id} {outcome.detail or f'failed after {outcome.attempts} attempts'}"
            )
        else:
            logger.info(f"Successfully sent webhook for task {ctx.task_id} (status: {outcome.http_status})")

        return self._conclude(
            ctx=ctx,
            log_id=log_id,
            url=url,
            outcome=outcome,
            start_time=start_time,
            audit_logger=audit_logger,
        )

    async def _deliver(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        idempotency_key: str,
        config: DeliverableWebhookTarget | None,
        tenant_id: str | None,
        max_attempts: int,
    ) -> WebhookDeliveryOutcome:
        """Hand one webhook to the egress seam and return what became of it. ONE call.

        Split out so the caller above books exactly one conclusion. The retry ladder
        used to be that caller's body, with the delivery-log write repeated inside
        each of its five arms; the arms differed only in what they KNEW, which is
        what :class:`WebhookDeliveryOutcome` carries instead. The ladder itself is
        gone from this file entirely now — ``adeliver_webhook`` retries, classifies
        and reports the same outcome type this function used to hand-build, so the
        five arms are not reimplemented here, they are simply not written.

        **Why the seam rather than the SDK sender.** The signing path and the egress
        path are the same path now that ``_headers_for`` has an RFC 9421 arm. That
        removes the choice this function used to be stuck between: ``adcp``'s
        ``WebhookSender`` trusts an operator-supplied client completely and SKIPS its
        own address policy for it, so signing through the SDK meant either donating a
        client (and losing the address check — the pool #1802 deleted) or accepting a
        per-delivery SDK client. Now the signature is a ``sign=`` CALLBACK applied
        INSIDE ``outbound_http.asend``, over ``request.content``, so a signed delivery
        keeps the seam's resolve-once-and-pin, redirect refusal, scheme/port policy,
        body cap and retry, unchanged. No client is created, donated or held anywhere
        on this path; this module imports none.

        ``signer=`` is passed UNCONDITIONALLY and that is not a dropped decision. A
        stored row does not tell its reader which arm it selects, so every sender
        hands the seam the tenant's strategy and the seam's one match decides: with an
        ``authentication`` block present the block selects the legacy arm and the
        signer is ignored (security.mdx @ v3.1.1 :1424, and :1425 forbids answering a
        legacy registration with an RFC 9421 signature); with the block ABSENT — the
        pinned schema's own selector for the 9421 profile — the signer signs. Deciding
        here which of those a row is would put mode selection in a fourth place.

        ``idempotency_key`` is merged into the body, exactly as
        ``WebhookSender.send_raw`` did (``{**payload, "idempotency_key": key}``, kwarg
        last so the two cannot disagree), so the wire document is unchanged by the
        move. It is constant across the attempts of one event so the receiver can
        dedup them; the SIGNATURE is not, because the seam signs each attempt afresh
        and RFC 9421's ``nonce`` must never repeat. The merge happens HERE and not at
        the caller for the same reason: the seam serializes exactly the dict it is
        given, once, and signs those bytes, so the key has to be in the dict before it
        crosses.

        Nothing is classified here. 4xx is permanent, 5xx and 429 are transient, a
        blocked address is ``refused_destination`` before any request exists, and an
        unusable registration is ``refused_auth`` before anything is serialized — all
        of it the seam's single taxonomy. Writing a second one here would need the
        httpx exception types, and ``httpx`` is banned outside the egress seam
        (ruff-egress.toml) precisely so that taxonomy lives in one place.
        """
        if max_attempts < 1:
            # Kept although the seam would also fail: with ``max_attempts=0`` its loop
            # simply never runs and it reports an ``exhausted`` delivery, which would
            # dress a programming error up as a receiver problem in the delivery log.
            raise ValueError(f"max_attempts must be at least 1, got {max_attempts}")

        return await adeliver_webhook(
            url,
            {**payload, "idempotency_key": idempotency_key},
            scheme=config.authentication_type if config is not None else None,
            credentials=config.authentication_token if config is not None else None,
            headers=headers,
            timeout=_DELIVERY_TIMEOUT_SECONDS,
            max_attempts=max_attempts,
            # Resolved as an ARGUMENT, so the signing session opens, is read and CLOSES
            # before ``adeliver_webhook`` is entered and any socket exists (#1757) — the
            # rule a connection held across a POST to a buyer-supplied URL would break.
            # WHICH key is not this sender's decision: ``delivery_signer_for_tenant`` is
            # the ONE open-read-close all three webhook senders share, so two transports
            # cannot sign one tenant's deliveries with two different keys.
            #
            # No silent downgrade. ``None`` is not a failure and never a fallback: it is
            # the decided posture of a tenant whose advertised
            # ``webhook_signing.supported`` is already ``false``, so its receivers have
            # been told not to expect a ``Signature`` header. A tenant that CAN sign but
            # whose material cannot be honestly used — a key that will not resolve, or an
            # algorithm contradicting the published declaration — RAISES out of the
            # helper, which catches nothing, so the ``adeliver_webhook`` call below is
            # never reached: there is no plain body to fall back to because none was ever
            # serialized. THIS sender's disposition of that raise is local to it — the
            # caller's ``except`` books it as an ``unexpected`` outcome with zero attempts
            # — and the other two senders book it their own way.
            signer=delivery_signer_for_tenant(tenant_id),
        )


# Global service instance
_webhook_service: ProtocolWebhookService | None = None


def get_protocol_webhook_service() -> ProtocolWebhookService:
    """Get or create global webhook service instance.

    The service owns no connection state, so there is nothing to close and no
    shutdown callback to register. Each delivery builds a transport pinned to its
    own destination and discards it: a pooled client shared across destinations
    would resolve once and then serve a hostname it was never validated for,
    which is the whole reason the pin exists.
    """
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = ProtocolWebhookService()
    return _webhook_service


def get_webhook_service_or_none() -> ProtocolWebhookService | None:
    """Return the current singleton instance, or None if never constructed.

    Distinct from :func:`get_protocol_webhook_service`: this does NOT trigger
    construction. Use it from shutdown hooks where you only want to close an
    *existing* instance, not create one just to inspect it.

    Resolving the singleton through this function call is location-independent:
    it reads the live module global at call time, so callers may import it at
    module top-level without the lazy-import tripwire that a direct
    ``from ... import _webhook_service`` would introduce (a hoisted private
    import binds the initial ``None`` forever).
    """
    return _webhook_service
