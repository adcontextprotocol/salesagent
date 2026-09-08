"""Background order approval polling service for GAM.

GAM requires time (0-120 seconds) to run inventory forecasting before an order
can be approved. This service polls GAM in the background and notifies via webhook
when approval completes or fails.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import SyncJob
from src.core.security.webhook_egress import deliver_webhook
from src.core.signing import delivery_signer_for_tenant
from src.core.thread_registry import ThreadRegistry
from src.core.webhook_validator import webhook_url_for_log
from src.core.webhooks.delivery import WebhookDeliveryOutcome

logger = logging.getLogger(__name__)

#: The per-attempt timeout and attempt budget this sender asks the seam for.
#: Both were previously the SDK sender's own (``webhook_sender_factory._TIMEOUT_SECONDS``
#: = 10.0) and this module's hand-rolled ``range(3)`` ladder respectively; naming them
#: here keeps the ASK visible at the one call site while the seam keeps the schedule.
_DELIVERY_TIMEOUT_SECONDS = 10.0
_DELIVERY_MAX_ATTEMPTS = 3

# Global registry of running approval threads. ThreadRegistry reaps dead
# threads on every read — same defensive cleanup as the sync registry
# (production memory-leak triage #5).
_active_approvals = ThreadRegistry()

# The parallel stop-signal dict, the same dual-dict shape delivery_simulator.py
# and gam/managers/reporting.py already use and that ThreadRegistry's own
# docstring sanctions. Without it the registry could observe a thread but never
# stop one: the retry path below sleeps 2**attempt behind HTTP POSTs that time
# out after 10 s, so a started approval outlived the request that began it by
# tens of seconds. Measured (#2056): a thread from one unit test called sleep(1)
# and sleep(2) inside two OTHER tests ~1500 tests later, landing in their mocks
# because src/core/webhook_delivery.py imports `time` and patching
# src.core.webhook_delivery.time.sleep replaces it process-wide.
_stop_signals: dict[str, threading.Event] = {}
_stop_signals_lock = threading.Lock()  # Protects _stop_signals iteration


def _on_approval_reaped(approval_id: str) -> None:
    """Drop the parallel _stop_signals entry when a dead approval is reaped.

    Lock-free by design, exactly as delivery_simulator._on_simulation_reaped is:
    ``dict.pop`` is atomic under the GIL, and the reap path runs
    registry-lock -> here while the accessors take _stop_signals_lock ->
    registry. Taking the lock here would invert that order and risk an ABBA
    deadlock.
    """
    _stop_signals.pop(approval_id, None)


_active_approvals.add_reap_callback(_on_approval_reaped)


def get_approval_stop_signal(approval_id: str) -> threading.Event | None:
    """The stop signal for a running approval, or None if it is not running."""
    with _stop_signals_lock:
        return _stop_signals.get(approval_id)


def cancel_order_approval(approval_id: str) -> bool:
    """Ask a running approval thread to stop; True if one was signalled.

    Cooperative: it sets the Event the worker's interruptible sleep waits on, so
    the thread stops at its next sleep boundary rather than being killed. Join
    it with ``_active_approvals.get(approval_id)`` when the caller needs the
    thread actually finished.
    """
    signal = get_approval_stop_signal(approval_id)
    if signal is None:
        return False
    signal.set()
    return True


def start_order_approval_background(
    order_id: str,
    media_buy_id: str,
    tenant_id: str,
    principal_id: str,
    webhook_url: str | None = None,
    max_attempts: int = 12,
    poll_interval_seconds: int = 10,
) -> str:
    """Start background order approval polling.

    Args:
        order_id: GAM order ID to approve
        media_buy_id: Associated media buy ID
        tenant_id: Tenant identifier
        principal_id: Principal identifier
        webhook_url: Optional webhook URL to notify on completion
        max_attempts: Maximum polling attempts (default: 12 = 2 minutes)
        poll_interval_seconds: Seconds between polling attempts (default: 10)

    Returns:
        approval_id: The approval job ID for tracking progress

    Raises:
        ValueError: If an approval is already running for this order
    """
    # Check if approval already running
    with get_db_session() as db:
        stmt = select(SyncJob).where(
            SyncJob.sync_type == "order_approval",
            SyncJob.status == "running",
        )
        existing_approvals = db.scalars(stmt).all()

        # Check if any existing approval is for this order
        for approval in existing_approvals:
            if approval.progress and approval.progress.get("order_id") == order_id:
                raise ValueError(f"Approval already running for order {order_id}: {approval.sync_id}")

        # Create new approval job
        approval_id = f"approval_{order_id}_{int(datetime.now(UTC).timestamp())}"

        approval_job = SyncJob(
            sync_id=approval_id,
            tenant_id=tenant_id,
            adapter_type="google_ad_manager",
            sync_type="order_approval",
            status="running",
            started_at=datetime.now(UTC),
            triggered_by="order_creation",
            triggered_by_id=media_buy_id,
            progress={
                "order_id": order_id,
                "media_buy_id": media_buy_id,
                "principal_id": principal_id,
                "webhook_url": webhook_url,
                "attempts": 0,
                "max_attempts": max_attempts,
                "phase": "Starting approval polling",
            },
        )
        db.add(approval_job)
        db.commit()

    # Reserve the stop signal BEFORE starting the thread, so a cancel racing the
    # start still lands: the worker reads the signal, and a caller that cancels
    # between add() and the worker's first sleep finds an Event already there.
    # Never call into the registry while holding this lock — the registry has its
    # own, and the reap callback re-enters _stop_signals (ABBA avoidance).
    with _stop_signals_lock:
        _stop_signals[approval_id] = threading.Event()

    # Start background thread
    thread = threading.Thread(
        target=_run_approval_thread,
        args=(
            approval_id,
            order_id,
            media_buy_id,
            tenant_id,
            principal_id,
            webhook_url,
            max_attempts,
            poll_interval_seconds,
        ),
        daemon=True,
        name=f"approval-{approval_id}",
    )

    _active_approvals.add(approval_id, thread)

    thread.start()
    logger.info(f"Started background approval polling thread: {approval_id}")

    return approval_id


def _run_approval_thread(
    approval_id: str,
    order_id: str,
    media_buy_id: str,
    tenant_id: str,
    principal_id: str,
    webhook_url: str | None,
    max_attempts: int,
    poll_interval_seconds: int,
):
    """Run the actual approval polling in a background thread.

    This function runs in a separate thread and polls GAM every 10 seconds
    for up to 2 minutes (12 attempts) to approve the order. Updates the SyncJob
    record as it progresses.
    """
    try:
        logger.info(f"[{approval_id}] Starting order approval polling for order {order_id}")

        # Import here to avoid circular dependencies
        from src.adapters.gam.managers.orders import GAMOrdersManager

        # Get adapter config via repository
        with get_db_session() as db:
            from src.core.database.repositories.adapter_config import AdapterConfigRepository

            adapter_repo = AdapterConfigRepository(db, tenant_id)
            adapter_config = adapter_repo.find_by_tenant()

            if not adapter_config or not adapter_config.gam_network_code:
                _mark_approval_failed(
                    approval_id, "GAM not configured for tenant", webhook_url, tenant_id, principal_id, media_buy_id
                )
                return

            gam_config = adapter_repo.get_gam_config(adapter_config)

        # Create GAM client
        from src.adapters.gam.client import GAMClientManager

        client_manager = GAMClientManager(gam_config, adapter_config.gam_network_code)
        orders_manager = GAMOrdersManager(client_manager, dry_run=False)

        # Poll GAM approval endpoint
        for attempt in range(1, max_attempts + 1):
            try:
                _update_approval_progress(
                    approval_id, {"attempts": attempt, "phase": f"Approval attempt {attempt}/{max_attempts}"}
                )

                logger.info(f"[{approval_id}] Approval attempt {attempt}/{max_attempts} for order {order_id}")

                # Attempt approval
                success = orders_manager.approve_order(order_id, max_retries=1)

                if success:
                    # Approval succeeded
                    _mark_approval_complete(
                        approval_id,
                        {
                            "order_id": order_id,
                            "media_buy_id": media_buy_id,
                            "attempts": attempt,
                            "duration_seconds": attempt * poll_interval_seconds,
                        },
                        webhook_url,
                        tenant_id,
                        principal_id,
                        media_buy_id,
                    )
                    logger.info(f"[{approval_id}] Order {order_id} approved after {attempt} attempts")
                    return

                # Check if we should retry
                if attempt < max_attempts:
                    logger.info(
                        f"[{approval_id}] Approval not ready yet, waiting {poll_interval_seconds}s before retry"
                    )
                    time.sleep(poll_interval_seconds)
                else:
                    # Max attempts reached
                    error_msg = f"Order approval failed after {max_attempts} attempts (2 minutes). GAM forecasting may still be in progress."
                    _mark_approval_failed(approval_id, error_msg, webhook_url, tenant_id, principal_id, media_buy_id)
                    return

            except Exception as e:
                error_str = str(e)

                # Check for non-retryable errors
                if "NO_FORECAST_YET" not in error_str and "ForecastingError" not in error_str:
                    # Non-retryable error
                    _mark_approval_failed(
                        approval_id,
                        f"Non-retryable error: {error_str}",
                        webhook_url,
                        tenant_id,
                        principal_id,
                        media_buy_id,
                    )
                    return

                # Retryable error - continue polling
                if attempt < max_attempts:
                    logger.warning(f"[{approval_id}] Retryable error: {error_str}, will retry")
                    time.sleep(poll_interval_seconds)
                else:
                    # Max attempts reached
                    _mark_approval_failed(
                        approval_id,
                        f"Order approval timed out after {max_attempts} attempts: {error_str}",
                        webhook_url,
                        tenant_id,
                        principal_id,
                        media_buy_id,
                    )
                    return

    except Exception as e:
        logger.error(f"[{approval_id}] Approval polling failed: {e}", exc_info=True)
        _mark_approval_failed(approval_id, str(e), webhook_url, tenant_id, principal_id, media_buy_id)

    finally:
        # Remove from active approvals
        _active_approvals.remove(approval_id)


def _update_approval_progress(approval_id: str, progress_data: dict[str, Any]):
    """Update approval job progress in database."""
    try:
        with get_db_session() as db:
            stmt = select(SyncJob).where(SyncJob.sync_id == approval_id)
            approval_job = db.scalars(stmt).first()
            if approval_job:
                # Merge with existing progress
                if approval_job.progress:
                    approval_job.progress.update(progress_data)
                else:
                    approval_job.progress = progress_data
                db.commit()
    except Exception as e:
        logger.warning(f"Failed to update approval progress: {e}")


def _mark_approval_complete(
    approval_id: str,
    summary: dict[str, Any],
    webhook_url: str | None,
    tenant_id: str,
    principal_id: str,
    media_buy_id: str,
):
    """Mark approval as completed and send webhook notification."""
    try:
        with get_db_session() as db:
            import json

            stmt = select(SyncJob).where(SyncJob.sync_id == approval_id)
            approval_job = db.scalars(stmt).first()
            if approval_job:
                approval_job.status = "completed"
                approval_job.completed_at = datetime.now(UTC)
                approval_job.summary = json.dumps(summary) if summary else None
                db.commit()

        # Send webhook notification
        if webhook_url:
            _send_approval_webhook(
                webhook_url=webhook_url,
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                status="approved",
                message="Order approved successfully",
                order_id=summary.get("order_id"),
                attempts=summary.get("attempts"),
                stop_signal=get_approval_stop_signal(approval_id),
            )

    except Exception as e:
        logger.error(f"Failed to mark approval complete: {e}")


def _mark_approval_failed(
    approval_id: str,
    error_message: str,
    webhook_url: str | None,
    tenant_id: str,
    principal_id: str,
    media_buy_id: str,
):
    """Mark approval as failed and send webhook notification."""
    try:
        # Read the progress fields BEFORE the session closes. ``db.commit()``
        # expires every attribute on ``approval_job``, so touching ``.progress``
        # after the ``with`` block raises DetachedInstanceError — which the
        # ``except`` below then swallowed, and the buyer was never told the order
        # had failed at all (salesagent-98t2, reproduced by
        # tests/integration/test_order_approval_webhook_signing.py).
        order_id: str | None = None
        attempts: int | None = None

        with get_db_session() as db:
            stmt = select(SyncJob).where(SyncJob.sync_id == approval_id)
            approval_job = db.scalars(stmt).first()
            if approval_job:
                approval_job.status = "failed"
                approval_job.completed_at = datetime.now(UTC)
                approval_job.error_message = error_message
                db.commit()

                progress = approval_job.progress or {}
                order_id = progress.get("order_id")
                attempts = progress.get("attempts")

        # Send webhook notification
        if webhook_url:
            _send_approval_webhook(
                webhook_url=webhook_url,
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                status="failed",
                message=error_message,
                order_id=order_id,
                attempts=attempts,
                stop_signal=get_approval_stop_signal(approval_id),
            )

    except Exception as e:
        logger.error(f"Failed to mark approval failed: {e}")


@dataclass(frozen=True, slots=True)
class ApprovalWebhookAuth:
    """The buyer's registration, PROJECTED to primitives — the row never escapes.

    Carries exactly what the egress seam takes — ``authentication_type`` /
    ``authentication_token``, which :func:`~src.core.security.webhook_egress.deliver_webhook`
    accepts as the stored PRIMITIVES ``scheme=`` / ``credentials=`` — plus ``url`` for
    provenance and ``validation_token`` for the one extra header this service adds.
    Nothing here interprets those two values: the seam validates the pair against the
    pinned ``Authentication`` type and picks the arm, which is why this projection has no
    "is it HMAC" helper for a caller to disagree with the seam through.

    WHY A PROJECTION AND NOT THE ORM ROW (#1878). The loader used to return the live row
    and carried a paragraph explaining why that was safe: "Detaching it at the end of the
    session is safe — ``get_db_session`` closes without committing, so the loaded columns
    survive; the expiry hazard ... needs a ``commit()``." That is correctness resting on a
    subtle SQLAlchemy behaviour explained in a comment — and it is why the loader could not
    simply move to a unit of work, since ``BaseUoW.__exit__`` DOES commit
    (``uow.py`` :107-108) and no session sets ``expire_on_commit=False`` (``uow.py`` :379),
    which would expire the row before these fields are read.

    Copying the values inside the session removes the hazard rather than documenting it:
    the unit of work may commit and expire whatever it likes, because nothing downstream
    holds anything that can expire.
    """

    url: str
    authentication_type: str | None
    authentication_token: str | None
    validation_token: str | None


def _load_approval_webhook_config(tenant_id: str, principal_id: str, webhook_url: str) -> ApprovalWebhookAuth | None:
    """The buyer's registration for this URL, read through the repository's unit of work.

    That registration is the ONE selector for how this notification is authenticated
    (#1291 C1, salesagent-98t2): it feeds both :func:`_approval_webhook_headers` and the
    delivery boundary's auth-strategy choice, so it is read once here rather than at each
    of those two points.

    Projected to :class:`ApprovalWebhookAuth` INSIDE the unit of work — see that class for
    why the ORM row must not leave it.
    """
    from src.core.database.repositories.uow import PushNotificationConfigUoW

    with PushNotificationConfigUoW(tenant_id) as uow:
        assert uow.push_notification_configs is not None
        row = uow.push_notification_configs.get_active_by_url(principal_id, webhook_url)
        if row is None:
            return None
        return ApprovalWebhookAuth(
            url=row.url,
            authentication_type=row.authentication_type,
            authentication_token=row.authentication_token,
            validation_token=row.validation_token,
        )


def _approval_webhook_headers(config: ApprovalWebhookAuth | None) -> dict[str, str]:
    """The genuinely EXTRA headers for an order-approval webhook POST.

    Neither ``Content-Type`` nor the authentication header belongs here. The egress
    seam (``src.core.security.webhook_egress``) frames the body it serialized —
    ``prepare_signed_request`` ``setdefault``\\ s ``application/json``, and its RFC 9421
    arm REFUSES any other spelling because the signer covers that exact value — and it
    derives the auth arm from this same ``config`` row: legacy HMAC, legacy bearer, or
    the RFC 9421 profile when no ``authentication`` block was registered. Setting
    either header here would authenticate the delivery twice, in two disagreeing ways,
    and a hand-written ``Content-Type`` would additionally trip the seam's own guard.

    ``validation_token`` is a receiver-side echo, not an auth scheme, so it
    stays a plain extra header. It is also sender-local — this sender emits it
    and ``protocol_webhook_service`` does not — so it deliberately stays out of
    any shared auth resolver rather than silently changing one sender's headers
    under cover of unification.
    """
    headers = {"User-Agent": "AdCP-Sales-Agent/1.0 (Order Approval Notifications)"}
    if config and config.validation_token:
        headers["X-Webhook-Token"] = config.validation_token
    return headers


def _post_approval_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    config: ApprovalWebhookAuth | None,
    tenant_id: str,
    stop_signal: threading.Event | None = None,
) -> WebhookDeliveryOutcome | None:
    """Deliver the approval payload through the ONE egress seam and say what became of it.

    GH #1802. Everything this function used to own is now the seam's, and the deletions
    are the point rather than a side effect:

    * the hand-rolled ``for attempt in range(3)`` / ``time.sleep(2 ** attempt)`` ladder —
      ``deliver_webhook`` owns the attempt budget, the BR-RULE-029 backoff and which
      statuses are worth another attempt, so a fourth sender can no longer retry on a
      schedule the other three do not;
    * the ``validate_url`` pre-flight in :func:`_send_approval_webhook` — ``send``'s own
      ``EgressPolicy.resolve_for_dial`` applies the identical policy and is the resolution
      that actually gets pinned, so the pre-flight was a second copy of address policy
      whose only unique contribution was a DNS-rebinding window between the two lookups;
    * the ``except Exception`` transport arm — transport failure is now an OUTCOME kind,
      not an exception each sender re-derives its own literals from.

    Authentication is likewise one decision, made once, at the seam. The stored PRIMITIVES
    go over as ``scheme=`` / ``credentials=`` (never a type this caller constructed and
    would have to interpret a ``ValidationError`` from), and ``signer=`` carries the
    tenant's RFC 9421 strategy for the arm the pinned schema selects by the ABSENCE of an
    ``authentication`` block. Handing over a strategy rather than a signature is
    load-bearing: the seam invokes ``build_auth_headers`` once PER ATTEMPT over
    ``request.content``, so every retry carries a fresh ``nonce`` over the exact bytes
    httpx is about to transmit — a signature computed once above a retry loop is one a
    conformant receiver must reject on attempt two.

    What stays local is the logging contract: every message names the SANITIZED URL, never
    the raw one, so a webhook URL carrying userinfo credentials or a query token cannot
    reach the logs; the level comes from ``outcome.log_level`` so this sender cannot log a
    refused destination at a different severity than the other three; and ``outcome.detail``
    is pre-sanitized at construction, so no resolved address is interpolated here.

    What stays local is the logging contract: every message names the SANITIZED
    URL, never the raw one, so a webhook URL carrying credentials or a token in
    its query string cannot reach the logs.

    ``stop_signal`` is the last boundary a cancelled approval can still stop at
    inside this module. It is passed in rather than looked up from the registry
    so this helper stays ignorant of approval bookkeeping — it only needs "has
    the caller been asked to stop". Its reach narrowed when the retry loop moved
    behind the seam: the interruptible ``Event.wait`` that replaced
    ``time.sleep(2 ** attempt)`` has no loop left to sit in, because the seam
    owns attempt count and backoff and exposes no cancellation hook. So the
    check happens HERE, before the hand-off — a cancelled approval never enters
    a three-attempt delivery it could no longer be pulled out of. It does NOT
    abort a delivery already in flight; do not read it as if it did.

    Returns ``None`` — never a fabricated outcome — when the approval was cancelled
    before the dial. ``WebhookDeliveryOutcome.kind`` is a closed Literal
    (delivered / refused_destination / refused_auth / client_error / exhausted) and
    none of them means "not attempted"; reusing ``refused_destination`` would claim a
    policy refused a URL that was never judged. Absence is the honest answer.
    """
    safe_url = webhook_url_for_log(webhook_url)
    if stop_signal is not None and stop_signal.is_set():
        # The cancel landed before we dialled, which is the only moment this
        # module still controls. Logged at INFO, not WARNING: a cancelled
        # approval not sending its webhook is the requested outcome, not a fault.
        logger.info("Approval webhook to %s not sent: the approval was cancelled", safe_url)
        return None
    # The tenant's RFC 9421 strategy, resolved on a session the signing layer opens and
    # CLOSES here, before ``deliver_webhook`` below can dial anything (#1757). One shared
    # ``delivery_signer_for_tenant`` rather than a local composition of ``signing_repo`` +
    # ``webhook_delivery_signer``: all three webhook senders needed the identical
    # open-read-close, and three copies is how the key a delivery is signed with starts
    # depending on which transport carried it.
    #
    # No ``try``, and that is the no-silent-downgrade rule. ``None`` is returned only for
    # the DECIDED postures (no tenant/repository, or published capabilities that already
    # say ``webhook_signing.supported=false``), which mean "this receiver was told not to
    # expect a Signature header" and are delivered plain by the seam. Every other outcome
    # RAISES out of the helper — notably ``AdCPConfigurationError`` when the key's ``alg``
    # contradicts the declared ``webhook_signing.algorithms`` — and PROPAGATES past the
    # call below, so nothing is serialized and nothing is sent. This sender lets it reach
    # the two polling-thread callers that already wrap their call; the other two senders
    # book the same raise their own way, which is why the helper resolves and never handles.
    #
    # Resolved UNCONDITIONALLY, without first asking whether ``config`` selects a legacy
    # arm. That is the seam's stated contract (``deliver_webhook``'s ``signer`` docstring:
    # "a caller reading a stored row cannot know which arm the row selects, so it passes
    # the tenant's signer unconditionally and this match decides"), and re-deriving the arm
    # here is precisely the duplicated selector GH #1802 exists to delete. Consequence,
    # stated rather than discovered: a tenant whose 9421 declaration is inconsistent now
    # fails loudly even on a legacy-registered delivery, where the old SDK path returned
    # early and never looked.
    signer = delivery_signer_for_tenant(tenant_id)

    outcome = deliver_webhook(
        webhook_url,
        payload,
        # No ``field=``-style provenance is available and none is fabricated: this URL is
        # read back out of a stored registration, so there is no live request document to
        # name a path into.
        scheme=config.authentication_type if config else None,
        credentials=config.authentication_token if config else None,
        headers=headers,
        timeout=_DELIVERY_TIMEOUT_SECONDS,
        max_attempts=_DELIVERY_MAX_ATTEMPTS,
        signer=signer,
    )

    safe_url = webhook_url_for_log(webhook_url)
    if outcome.kind == "delivered":
        logger.log(
            outcome.log_level,
            "Approval webhook sent to %s (status: %s, http: %s, attempts: %s)",
            safe_url,
            payload.get("status"),
            outcome.http_status,
            outcome.attempts,
        )
    elif outcome.kind == "refused_destination":
        # TERMINAL and EXPLICIT, and not an exception to be mistaken for a transport
        # blip: ``send`` raised ``OutboundRequestBlocked`` out of ``resolve_for_dial``
        # BEFORE it built a request, so ``attempts`` is zero, ``signer`` was never
        # invoked and no unsigned body was ever produced to fall back to. Nothing about
        # the destination changes on a second look, so there is nothing to retry. The
        # sentence is the one every sender uses and names ONLY the sanitized URL — the
        # underlying refusal names the resolved address (``egress/policy.py``), which
        # must not reach a log.
        logger.log(outcome.log_level, "Approval webhook to %s was refused by egress policy", safe_url)
    elif outcome.kind == "refused_auth":
        # FAIL-CLOSED. The buyer's stored registration asks for an authentication this
        # seller cannot produce conformantly; nothing was dialled. ``detail``/``reason``
        # are the seam's closed vocabulary, pre-sanitized at construction.
        logger.log(
            outcome.log_level,
            "Approval webhook to %s was refused: %s",
            safe_url,
            outcome.detail or outcome.reason,
        )
    else:
        logger.log(
            outcome.log_level,
            "Approval webhook to %s did not deliver (%s, http: %s, attempts: %s): %s",
            safe_url,
            outcome.kind,
            outcome.http_status,
            outcome.attempts,
            outcome.detail,
        )
    return outcome


def _send_approval_webhook(
    webhook_url: str,
    tenant_id: str,
    principal_id: str,
    media_buy_id: str,
    status: str,
    message: str,
    order_id: str | None = None,
    attempts: int | None = None,
    stop_signal: threading.Event | None = None,
) -> WebhookDeliveryOutcome | None:
    """Send webhook notification for approval status update.

    Returns the seam's :class:`~src.core.webhooks.delivery.WebhookDeliveryOutcome` rather
    than ``None``. That is what stops a refused destination being indistinguishable from a
    delivery to everything upstream — the defect the deleted
    ``_reject_unsafe_approval_webhook_url`` bool had, and which a bare ``return`` after a
    log line would quietly reinstate.

    There is deliberately no blanket ``except Exception`` around this body any more. It
    used to reduce EVERY failure to one log line, including the two that must not be
    reduced: a tenant whose RFC 9421 signer cannot be built (see
    :func:`~src.core.signing.delivery_signer_for_tenant`, resolved in
    :func:`_post_approval_webhook` — that must fail the delivery, never downgrade it to
    an unsigned send) and a failure to read the registration at all. Transport failure no
    longer needs the guard, because it is an outcome rather than an exception. Both
    callers, :func:`_mark_approval_complete` and :func:`_mark_approval_failed`, already
    wrap their call, so nothing escapes into the polling thread.

    Args:
        webhook_url: Webhook URL to POST to
        tenant_id: Tenant identifier
        principal_id: Principal identifier
        media_buy_id: Media buy identifier
        status: Approval status (approved, failed)
        message: Status message
        order_id: GAM order ID (if available)
        attempts: Number of polling attempts (if available)
        stop_signal: The approval's cancel Event, when one is running. Checked
            before the delivery is handed to the egress seam; None means
            "nothing to cancel", which is what every non-worker caller passes.
    """
    from adcp.webhooks import generate_webhook_idempotency_key

    payload: dict[str, Any] = {
        "event": "order_approval_update",
        "media_buy_id": media_buy_id,
        "status": status,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "principal_id": principal_id,
        # Carried in the BODY, exactly where the SDK sender this call replaces injected
        # it (``WebhookSender.send_raw``: ``{**payload, "idempotency_key": key}``), so
        # routing through the seam does not quietly cost the receiver its dedup key.
        # ONE key per distinct EVENT: the seam serializes once and retries those same
        # bytes, so every attempt of this event carries this key and no other.
        "idempotency_key": generate_webhook_idempotency_key(),
    }

    if order_id:
        payload["order_id"] = order_id
    if attempts is not None:
        payload["attempts"] = attempts

    config = _load_approval_webhook_config(tenant_id, principal_id, webhook_url)
    return _post_approval_webhook(
        webhook_url,
        payload,
        _approval_webhook_headers(config),
        config,
        tenant_id,
        stop_signal=stop_signal,
    )


def get_active_approvals() -> list[str]:
    """Get list of approval IDs currently running in background threads.

    Reaps dead threads on read so the returned list reflects live state
    even if the worker's ``finally`` cleanup didn't fire.
    """
    return _active_approvals.list_active()


def is_approval_running(approval_id: str) -> bool:
    """Check if an approval is currently running in a background thread.

    Reaps dead threads on read — an approval_id with a dead thread is no
    longer running, so this returns False (and the entry is pruned).
    """
    return _active_approvals.contains(approval_id)


def get_approval_status(approval_id: str) -> dict[str, Any] | None:
    """Get current status of an approval job.

    Args:
        approval_id: Approval job identifier

    Returns:
        Dictionary with approval status or None if not found
    """
    try:
        with get_db_session() as db:
            stmt = select(SyncJob).where(SyncJob.sync_id == approval_id)
            approval_job = db.scalars(stmt).first()

            if not approval_job:
                return None

            started_at_iso = None
            if approval_job.started_at is not None:
                # Handle both datetime and SQLAlchemy DateTime objects
                if hasattr(approval_job.started_at, "isoformat"):
                    started_at_iso = approval_job.started_at.isoformat()
                else:
                    started_at_iso = str(approval_job.started_at)

            completed_at_iso = None
            if approval_job.completed_at is not None:
                # Handle both datetime and SQLAlchemy DateTime objects
                if hasattr(approval_job.completed_at, "isoformat"):
                    completed_at_iso = approval_job.completed_at.isoformat()
                else:
                    completed_at_iso = str(approval_job.completed_at)

            return {
                "approval_id": approval_id,
                "status": approval_job.status,
                "started_at": started_at_iso,
                "completed_at": completed_at_iso,
                "progress": approval_job.progress,
                "error_message": approval_job.error_message,
                "summary": approval_job.summary,
            }
    except Exception as e:
        logger.error(f"Error getting approval status: {e}")
        return None
