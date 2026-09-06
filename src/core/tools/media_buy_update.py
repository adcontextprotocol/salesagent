"""Update Media Buy tool implementation.

Handles media buy updates including:
- Campaign-level budget and date changes
- Package-level budget adjustments
- Creative assignments per package
- Activation/pause controls
- Currency limit validation
"""

import logging
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from adcp.server.helpers import MEDIA_BUY_STATE_MACHINE, is_terminal_status, valid_actions_for_status
from adcp.types import GeneratedTaskStatus as AdcpTaskStatus
from adcp.types import MediaBuyStatus

from src.core.tools.media_buy_list import _compute_status

if TYPE_CHECKING:
    from src.core.database.models import MediaBuy

# ---------------------------------------------------------------------------
# Financial policy constants (F-05)
# ---------------------------------------------------------------------------

#: Absolute upper bound for any campaign-level budget update.
#: Configurable via MAX_CAMPAIGN_BUDGET_USD env var; default 10,000,000.
MAX_CAMPAIGN_BUDGET: Decimal = Decimal(os.environ.get("MAX_CAMPAIGN_BUDGET_USD", "10000000"))

from adcp.types import ContextObject
from sqlalchemy import select

from src.core.exceptions import (
    AdCPAdapterError,
    AdCPAuthorizationError,
    AdCPBudgetExceededError,
    AdCPBudgetTooLowError,
    AdCPCapabilityNotSupportedError,
    AdCPContextNotFoundError,
    AdCPCreativeRejectedError,
    AdCPGoneError,
    AdCPInvalidRequestError,
    AdCPValidationError,
)
from src.core.webhook_validator import reject_unsafe_webhook_registration_url, webhook_url_for_log
from src.core.webhooks.registration import accept_push_notification_config

logger = logging.getLogger(__name__)

from adcp.types.generated_poc.creative.sync_creatives_request import Assignment

from src.core.audit_logger import get_audit_logger
from src.core.auth import (
    require_identity,
    require_principal_id,
    require_tenant,
    resolve_principal_or_raise,
)
from src.core.context_manager import get_context_manager
from src.core.database.models import (
    CreativeAssignment as DBAssignment,
)
from src.core.database.models import (
    MediaBuy,
    ObjectWorkflowMapping,
    PersistedMediaBuyStatus,
)
from src.core.database.models import (
    Product as DBProduct,
)
from src.core.database.repositories import MediaBuyRepository, MediaBuyUoW
from src.core.errors.details import (
    AdapterFailureDetails,
    CapabilityRefusalDetails,
    CreativeRejectionDetails,
    EntityRefDetails,
    ErrorProblem,
    InvalidStateDetails,
    ValidationDetails,
)
from src.core.helpers.adapter_helpers import get_adapter
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas import (
    AffectedPackage,
    SyncCreativesRequest,
    UpdateMediaBuyError,
    UpdateMediaBuyRequest,
    UpdateMediaBuyResult,
    UpdateMediaBuySubmitted,
    UpdateMediaBuySuccess,
)
from src.core.testing_hooks import AdCPTestContext
from src.core.tools.creatives import _sync_creatives_impl
from src.core.tools.financial_validation import (
    raise_if_validation_failed,
    validate_budget_positive,
    validate_max_daily_package_spend,
    validate_min_package_budget,
)
from src.core.utils import utc_flight_start
from src.core.validation_helpers import package_field_path
from src.services.targeting_capabilities import (
    collect_targeting_violations,
    property_list_unsupported_advisories,
    raise_if_property_targeting_violations,
    validate_property_targeting_allowed,
)


def _adcp_status_and_actions(buy: "MediaBuy", today: date | None = None) -> tuple[MediaBuyStatus | None, list[str]]:
    """Map a media buy to ``(media_buy_status, valid_actions)``, DATE-REFINED.

    Routes through ``get_media_buys``' ``_compute_status`` (``resolve_canonical_status``
    + the delivery-only ``failed`` -> ``rejected`` mapping) so the update-response
    ``media_buy_status`` agrees with ``get_media_buys`` for the same buy and reference
    date — the two surfaces must describe one buy identically (the 8plg agreement;
    ). A past-end serving buy therefore reports ``completed`` on both,
    not the un-refined persisted ``active`` (the status scheduler that transitions the
    column may lag behind the flight window).

    ``valid_actions`` is derived from the resulting AdCP status so a persisted value
    whose name differs from its AdCP value (``scheduled``/``approved``/
    ``pending_approval``/``failed``/``draft``) never feeds a non-AdCP token to
    ``valid_actions_for_status`` (which would yield ``[]`` + a null status).

    The row is REQUIRED. Every caller obtains it from
    ``MediaBuyRepository.get_by_id_or_raise``, which raises
    ``AdCPMediaBuyNotFoundError`` (with a message, a suggestion and the buyer's
    context) for a row that vanished mid-transaction — so a missing row never reaches
    an envelope and this helper does not carry a second answer for one. ``today`` defaults to the current
    UTC date (mock-time aware, matching ``get_media_buys``); callers may pass an
    explicit reference date.

    Single source of truth for the update-response status pair so the four
    ``UpdateMediaBuySuccess`` sites cannot drift — from each other or from
    ``get_media_buys``.
    """
    if today is None:
        today = datetime.now(UTC).date()
    media_buy_status: MediaBuyStatus | None = _compute_status(buy, today) if buy.status else None
    valid_actions = valid_actions_for_status(media_buy_status.value) if media_buy_status else []
    return media_buy_status, valid_actions


def _requested_actions(req: UpdateMediaBuyRequest) -> list[str]:
    """Derive the AdCP buyer-action names implied by an update request.

    Returned names align with ``MEDIA_BUY_STATE_MACHINE`` keys so they can
    be intersected against ``valid_actions_for_status(current_status)``.
    """
    actions: list[str] = []
    if req.paused is True:
        actions.append("pause")
    if req.paused is False:
        actions.append("resume")
    if req.packages and any(pkg.budget is not None for pkg in req.packages):
        actions.append("update_budget")
    if req.start_time is not None or req.end_time is not None:
        actions.append("update_dates")
    if req.packages:
        actions.append("update_packages")
    return actions


def _normalize_creative_agent_url(url: str | None) -> str | None:
    """Normalize a creative/format agent_url for comparison.

    Strips a trailing slash and an optional ``/mcp`` suffix so the two
    URL variants a buyer may use compare equal.
    """
    if not url:
        return None
    return url.rstrip("/").removesuffix("/mcp")


def _validate_creatives_for_assignment(
    creative_ids: list[str],
    *,
    uow: "MediaBuyUoW",
    principal_id: str,
    product: "DBProduct | None",
    product_name: str | None = None,
    context: ContextObject | None = None,
) -> None:
    """Validate a set of creatives is assignable to a package.

    Shared by both the ``creative_ids`` and ``creative_assignments`` update
    paths so the existence / status / format-compatibility rules live in one
    place (DRY). Checks run in order and raise ``AdCPCreativeRejectedError``
    (wire code ``CREATIVE_REJECTED``, correctable) on the first failing
    category, always carrying a ``suggestion`` for buyer recovery:

    1. Existence — every ``creative_id`` exists for this principal within the
       tenant. The creatives PK is composite (creative_id, tenant_id,
       principal_id): another principal's creative resolves to "not found"
       (uniform, no field leak) — never passes this gate on their row, which
       the assignment insert would then violate on the composite FK.
    2. Status — none are in ``error`` or ``rejected`` state.
    3. Format compatibility — each creative's ``(agent_url, format)`` is
       supported by the package's product ``format_ids``. A product with no
       declared formats imposes no restriction.

    Args:
        creative_ids: Creative IDs referenced by the package update.
        uow: Tenant-scoped unit of work exposing ``creatives``.
        principal_id: The requesting buyer's principal (from ResolvedIdentity).
        product: The package's product ORM record (or ``None`` if the package
            has no resolvable product, in which case the format check is skipped).
        product_name: Display name for error messages (falls back to the
            product's name, then the product_id).
        context: AdCP context object, flowed into the error envelope.

    Raises:
        AdCPCreativeRejectedError: If any creative is not found, in a terminal
            state, or has a format incompatible with the product.
    """
    if not creative_ids:
        return

    requested_ids = list(dict.fromkeys(creative_ids))  # de-dup, preserve order

    # (a) Existence — principal-scoped multi-get via repository.
    assert uow.creatives is not None, "MediaBuyUoW.creatives required for creative validation"
    creatives_list = uow.creatives.get_by_ids(requested_ids, principal_id)
    found_by_id = {c.creative_id: c for c in creatives_list}
    missing_ids = [cid for cid in requested_ids if cid not in found_by_id]
    if missing_ids:
        # FIXME(#1598): CREATIVE_REJECTED here vs the pinned enum's
        # CREATIVE_NOT_FOUND uniformity MUST — the BR-UC-003 ext-i storyboard
        # cell grades CREATIVE_REJECTED; deferred pending upstream reconciliation.
        raise AdCPCreativeRejectedError(
            details=CreativeRejectionDetails(creative_ids=missing_ids),
            context=context,
        )

    # (b) Status — terminal-state creatives are not assignable.
    bad_state = [c for c in creatives_list if c.status in ("error", "rejected")]
    if bad_state:
        raise AdCPCreativeRejectedError(
            # The STATE per creative, not a joined sentence duplicating creative_ids.
            # Per-creative outcomes are per-ENTITY problems, not fields.
            details=CreativeRejectionDetails(
                problems=[
                    ErrorProblem(subject_type="creative", subject_id=c.creative_id, rejected_value=c.status)
                    for c in bad_state
                ]
            ),
            context=context,
        )

    # (c) Format compatibility against the package's product.
    if product is None or not product.format_ids:
        # No product or no declared formats — no format restriction.
        return

    display_name = product_name or getattr(product, "name", None) or getattr(product, "product_id", "")

    # Build the set of supported (normalized_agent_url, format_id) pairs.
    supported_formats: set[tuple[str | None, str]] = set()
    for fmt in product.format_ids:
        if isinstance(fmt, dict):
            agent_url = fmt.get("agent_url")
            format_id = fmt.get("id") or fmt.get("format_id")
            if format_id:
                supported_formats.add((_normalize_creative_agent_url(agent_url), format_id))

    if not supported_formats:
        return  # No usable format restrictions — allow all.

    incompatible: list[str] = []
    for creative in creatives_list:
        creative_pair = (_normalize_creative_agent_url(creative.agent_url), creative.format)
        if creative_pair not in supported_formats:
            display = f"{creative.agent_url}/{creative.format}" if creative.agent_url else str(creative.format)
            incompatible.append(f"{creative.creative_id} (format '{display}')")

    if incompatible:
        supported_display = ", ".join(
            f"{url}/{fmt_id}" if url else fmt_id for url, fmt_id in sorted(supported_formats, key=lambda p: p[1])
        )
        raise AdCPCreativeRejectedError(
            # FIXME(#2099): the product's DISPLAY NAME is prose, and product_id already
            # identifies it. Preserved for now because removing it changes the wire.
            details=CreativeRejectionDetails(accepted_values=[supported_display], product_id=display_name),
            context=context,
        )


def _verify_principal(
    media_buy_id: str,
    identity: "ResolvedIdentity",
    repo: MediaBuyRepository,
    *,
    context: ContextObject | None = None,
) -> None:
    """Verify that the principal from identity owns the media buy.

    Uses the provided repository for database access (no own session).

    Args:
        media_buy_id: Media buy ID to verify
        identity: ResolvedIdentity with principal info
        repo: Tenant-scoped MediaBuyRepository for DB lookups

    Raises:
        AdCPAuthenticationError: Missing principal
        AdCPMediaBuyNotFoundError: Media buy not found
        AdCPAuthorizationError: Principal doesn't own media buy
    """
    principal_id = require_principal_id(identity, context=context)

    # Tenant is resolved at the transport boundary (resolve_identity_from_context)
    tenant = require_tenant(identity, context=context)

    # Fetch the media buy (raises AdCPMediaBuyNotFoundError if absent)
    media_buy = repo.get_by_id_or_raise(media_buy_id, context=context)

    if media_buy.principal_id != principal_id:
        # Log security violation
        security_logger = get_audit_logger("AdCP", tenant["tenant_id"])
        security_logger.log_security_violation(
            operation="access_media_buy",
            principal_id=principal_id,
            resource_id=media_buy_id,
            reason=f"Principal does not own media buy (owner: {media_buy.principal_id})",
        )
        raise AdCPAuthorizationError(
            details=EntityRefDetails(principal_id=principal_id, media_buy_id=media_buy_id),
        )


def _update_media_buy_impl(
    req: UpdateMediaBuyRequest,
    identity: ResolvedIdentity | None = None,
    context_id: str | None = None,
) -> UpdateMediaBuyResult:
    """Shared implementation for update_media_buy (used by both MCP and A2A).

    Callers construct the validated UpdateMediaBuyRequest at their boundary
    (MCP wrapper from typed FastMCP params, A2A raw from dict params).

    Uses a single MediaBuyUoW for the entire operation — one session, one transaction.

    Args:
        req: Validated UpdateMediaBuyRequest with all protocol fields
        identity: ResolvedIdentity with principal/tenant info (transport-agnostic)
        context_id: Optional workflow context ID

    Returns:
        UpdateMediaBuyResponse with updated media buy details
    """
    # Initialize tracking for affected packages (internal tracking, not part of schema)
    affected_packages_list: list[AffectedPackage] = []

    identity = require_identity(identity, context=req.context)

    principal_id = require_principal_id(identity, context=req.context)

    # Tenant is resolved at the transport boundary (resolve_identity_from_context)
    tenant = require_tenant(identity, context=req.context)

    # SSRF gate at registration — after auth so unauthenticated callers get AUTH
    # first, and ABOVE the UoW so no DB transaction is held and a refused URL is
    # VALIDATION_ERROR regardless of buy state: the buyer must fix the request
    # before state questions are reachable, so this outranks the terminal-state
    # refusal. The stored copy this guards is the workflow step's request_data,
    # which context_manager later reads back and dials.
    #
    # Deliberately the no-DNS registration gate (gh-#1697), NOT the outbound seam's
    # validate_url (gh-#1589): validate_url always resolves, so at registration it
    # would reject a buyer whose hostname has not yet propagated — and would answer
    # the same input differently from create_media_buy / sync_creatives. The seam
    # stays the SEND-time gate and re-checks with DNS when the URL is actually dialed.
    # Use str(url): library PushNotificationConfig/ReportingWebhook.url is pydantic
    # AnyUrl, not str.
    if req.push_notification_config:
        registration = accept_push_notification_config(
            req.push_notification_config,
            field_prefix="push_notification_config",
            context=req.context,
        )
        pnc_url = registration.url
        if pnc_url is not None and str(pnc_url).strip():
            # Log scheme+host+path only — never credentials / full auth blob.
            logger.info(
                "[update_media_buy] Push notification webhook URL: %s",
                webhook_url_for_log(str(pnc_url)),
            )
    if req.reporting_webhook:
        rw_url = getattr(req.reporting_webhook, "url", None)
        reject_unsafe_webhook_registration_url(
            str(rw_url) if rw_url is not None else None,
            field="reporting_webhook.url",
            context=req.context,
        )

    # ── Workflow-step bookkeeping fence ──────────────────────────────────
    # Hoist ``ctx_manager`` and ``step`` out of the try below so the
    # AdCPSalesAgentError / Exception handlers at the function end can mark the step
    # as ``failed``. Without this, a raise from any validation site
    # (property_targeting, geo, budget, …) leaves the workflow step
    # orphaned in ``in_progress`` forever, which suppresses the
    # buyer-facing ``status="failed"`` push notification fired from
    # ``context_manager.update_workflow_step``, which fires it through
    # ``_send_push_notifications``.
    # Mirrors ``media_buy_create``'s own workflow-step construction exactly.
    ctx_manager = get_context_manager()
    step = None

    with ctx_manager.audit_workflow_step_failure_ctx(lambda: step):
        # Single UoW for entire update operation — one session, one transaction
        with MediaBuyUoW(tenant["tenant_id"]) as uow:
            assert uow.media_buys is not None
            # FIXME(#2128): raw session usages below should migrate to repository methods
            assert uow.session is not None
            session = uow.session

            # media_buy_id is required by library base class
            media_buy_id_to_use = req.media_buy_id

            if not media_buy_id_to_use:
                raise AdCPValidationError()

            # Verify principal owns this media buy
            _verify_principal(media_buy_id_to_use, identity, uow.media_buys, context=req.context)

            # State-machine precondition: terminal states reject all mutations,
            # and non-terminal states only accept actions in their valid set.
            # ``AdCPGoneError`` carries the spec-mandated ``INVALID_STATE`` code
            # for both terminal states and disallowed actions — see
            # ``adcp.server.helpers.MEDIA_BUY_STATE_MACHINE`` for the source of truth.
            _current_mb = uow.media_buys.get_by_id(media_buy_id_to_use)
            _current_status = _current_mb.status if _current_mb else ""
            if is_terminal_status(_current_status):
                raise AdCPGoneError(
                    details=InvalidStateDetails(current_status=_current_status),
                    field="media_buy_id",
                )

            _requested = _requested_actions(req)
            _allowed = set(valid_actions_for_status(_current_status))
            # Only enforce state machine for statuses defined in the spec.
            # Pre-confirmation internal states (e.g., "draft") are not in the
            # SDK state machine — allow all actions on those.
            if _allowed or _current_status in MEDIA_BUY_STATE_MACHINE:
                _disallowed = [a for a in _requested if a not in _allowed]
                if _requested and _disallowed:
                    raise AdCPGoneError(
                        details=InvalidStateDetails(disallowed_actions=_disallowed, current_status=_current_status),
                        field="media_buy_id",
                    )

            # Extract testing context early (needed for dry_run check)
            testing_ctx = identity.testing_context if identity.testing_context else AdCPTestContext()

            # Create or get persistent context and workflow step
            # (ctx_manager + step were hoisted before the try block so the
            # AdCPSalesAgentError / Exception handlers can mark the step as failed)
            ctx_id = context_id  # Extracted at transport boundary, passed in
            persistent_ctx = None

            if not testing_ctx.dry_run:
                persistent_ctx = ctx_manager.get_or_create_context(
                    tenant_id=tenant["tenant_id"],
                    principal_id=principal_id,  # Now guaranteed to be str
                    context_id=ctx_id,
                    is_async=True,
                )

                # Verify persistent_ctx is not None. In the async path this is
                # only None when a buyer-supplied context_id does not resolve —
                # a not-found condition, not a transient adapter outage.
                if persistent_ctx is None:
                    raise AdCPContextNotFoundError(
                        details=EntityRefDetails(context_id=ctx_id), field="context_id", context=req.context
                    )

                # Create workflow step for this tool call
                step = ctx_manager.create_workflow_step(
                    context_id=persistent_ctx.context_id,  # Now safe to access
                    step_type="tool_call",
                    owner="principal",
                    status="in_progress",
                    tool_name="update_media_buy",
                    request_data=req,
                    request_metadata={"protocol": identity.protocol},
                )

            principal = resolve_principal_or_raise(principal_id, tenant_id=identity.tenant_id, context=req.context)

            adapter = get_adapter(principal, dry_run=testing_ctx.dry_run, testing_context=testing_ctx, tenant=tenant)
            today = date.today()

            # AdCP 3.0.0 spec (core/product.json `property_targeting_allowed`): reject property_list targeting
            # on products with property_targeting_allowed=False. Runs before the dry_run
            # early return so dry_run requests are also rejected (parity with create).
            # Raise shape is shared with create via ``raise_if_property_targeting_violations``
            # so both paths emit byte-identical error envelopes (same code, same field,
            # same details). The boundary's AdCPSalesAgentError handler updates any in-flight
            # workflow step to status="failed" for the audit trail.
            if req.packages:
                assert uow.products is not None, "MediaBuyUoW.products required for product targeting validation"
                # Run the same per-package targeting validators the create path runs, so a buyer
                # can't bypass unknown-field rejection, managed-only dimension checks, or
                # same-value geo inclusion/exclusion overlap by sending changes through update.
                overlay_violations: dict[str, object] = {}
                for pkg_update in req.packages:
                    if pkg_update.targeting_overlay is None:
                        continue
                    overlay_violations.update(collect_targeting_violations(pkg_update.targeting_overlay))
                if overlay_violations:
                    # Canonical code per the generated storyboard (UC-002 @ext-f and UC-003
                    # @*-targeting-overlay both grade targeting validation as INVALID_REQUEST);
                    # converges with the create path (#1417).
                    raise AdCPInvalidRequestError(
                        details=ValidationDetails(**overlay_violations),
                        field="targeting_overlay",
                    )

                property_targeting_violations: list[str] = []
                for pkg_update in req.packages:
                    if (
                        pkg_update.targeting_overlay is None
                        or pkg_update.targeting_overlay.property_list is None
                        or not pkg_update.package_id
                    ):
                        continue
                    media_package = uow.media_buys.get_package(req.media_buy_id, pkg_update.package_id)
                    if media_package is None:
                        continue
                    package_product_id = (media_package.package_config or {}).get("product_id")
                    if not package_product_id:
                        continue
                    product = uow.products.get_by_id(package_product_id)
                    violation = validate_property_targeting_allowed(product, pkg_update.targeting_overlay)
                    if violation:
                        property_targeting_violations.append(violation)
                raise_if_property_targeting_violations(property_targeting_violations)

            # Dry-run mode: Return simulated response without any database writes
            # Validation has passed (principal verified, media buy exists), so we return what WOULD be updated
            if testing_ctx.dry_run:
                logger.info(f"[DRY_RUN] Returning simulated update response for media_buy_id={req.media_buy_id}")

                # Build simulated affected packages from request
                simulated_affected: list[AffectedPackage] = []
                if req.packages:
                    for pkg_update in req.packages:
                        simulated_affected.append(
                            AffectedPackage(
                                package_id=pkg_update.package_id or "",
                                paused=pkg_update.paused if pkg_update.paused is not None else False,
                                buyer_package_ref=pkg_update.package_id,
                                changes_applied={"dry_run": True, "would_update": pkg_update},
                            )
                        )

                # Look up current status for valid_actions (date-refined for
                # parity with get_media_buys — see _adcp_status_and_actions).
                _dry_run_mb = uow.media_buys.get_by_id_or_raise(req.media_buy_id or "", context=req.context)

                # Build simulated response.
                # The wire status="completed" is KEPT for dry_run and is
                # spec-correct (PR #1567): spec 3.1.1
                # update-media-buy-response.json has exactly three variants
                # (Success/Error/Submitted) and NO simulation envelope; dry_run is a
                # (deprecated) testing hook (X-Dry-Run header), not a wire field, and the
                # spec is SILENT on a dry_run response status -> production authoritative.
                # Unlike pending-approval (-> UpdateMediaBuySubmitted) and reject
                # (-> Error), a dry_run buyer asked to SIMULATE the would-be
                # outcome, which IS completion -> "completed" is a truthful preview, not a
                # lie. Guarded by tests/integration/test_media_buy_dry_run_status.py.
                _dry_run_revision = _dry_run_mb.revision
                _dry_run_mbs, _dry_run_actions = _adcp_status_and_actions(_dry_run_mb)
                dry_run_response = UpdateMediaBuySuccess(
                    media_buy_id=req.media_buy_id or "",
                    # A dry run applies nothing, so it reports the CURRENT token, not a bump.
                    revision=_dry_run_revision,
                    media_buy_status=_dry_run_mbs,  # AdCP 3.1: mirrors `status`
                    affected_packages=simulated_affected,
                    valid_actions=_dry_run_actions,
                    context=req.context,
                    errors=property_list_unsupported_advisories(req.packages, adapter),
                )

                return UpdateMediaBuyResult(response=dry_run_response, status=AdcpTaskStatus.completed.value)

            # Type narrowing: after dry_run early return, step and persistent_ctx are guaranteed to exist
            assert step is not None, "step should be created when not in dry_run mode"
            assert persistent_ctx is not None, "persistent_ctx should be created when not in dry_run mode"

            # Check if manual approval is required
            manual_approval_required = adapter.manual_approval_required
            manual_approval_operations = adapter.manual_approval_operations

            if manual_approval_required and "update_media_buy" in manual_approval_operations:
                # Store the original request alongside the response so the approval
                # execution path can re-execute the update after human approval.
                # This mirrors create_media_buy's raw_request pattern.
                # Spec 3.1.1 models a not-yet-applied (pending human approval) update as the
                # UpdateMediaBuySubmitted response variant: protocol-envelope status="submitted"
                # + a task_id the buyer polls for the outcome. Returning UpdateMediaBuySuccess
                # here would emit the adcp-6.6 default status="completed", falsely asserting the
                # update was applied. task_id is the workflow step the admin approval flow acts on.
                approval_response = UpdateMediaBuySubmitted(
                    task_id=step.step_id,
                    context=req.context,
                    errors=property_list_unsupported_advisories(req.packages, adapter),
                )
                ctx_manager.audit_workflow_step_result(
                    step.step_id,
                    approval_response,
                    status="requires_approval",
                    request_obj=req,
                    add_comment={
                        "user": "system",
                        "comment": "Publisher requires manual approval for all media buy updates",
                    },
                )

                # Create ObjectWorkflowMapping so the admin approval flow can
                # find this update and execute it after human approval.
                mapping = ObjectWorkflowMapping(
                    step_id=step.step_id,
                    object_type="media_buy",
                    object_id=req.media_buy_id,
                    action="update",
                )
                session.add(mapping)

                return UpdateMediaBuyResult(response=approval_response, status=AdcpTaskStatus.submitted.value)

            # Validate currency limits if flight dates or budget changes
            # This prevents workarounds where buyers extend flight to bypass daily max
            if req.start_time or req.end_time or (req.packages and any(pkg.budget for pkg in req.packages)):
                media_buy = uow.media_buys.get_by_id(req.media_buy_id)

                if media_buy:
                    # The buy's own currency: a package budget is denominated by its pricing
                    # option, and there is no campaign-level budget to carry a currency.
                    request_currency = str(media_buy.currency) if media_buy.currency else "USD"

                    assert uow.currency_limits is not None
                    currency_limit = uow.currency_limits.get_for_currency(request_currency)

                    if not currency_limit:
                        raise AdCPCapabilityNotSupportedError(
                            details=CapabilityRefusalDetails(capability="currency", rejected_value=request_currency),
                            context=req.context,
                        )

                    start = req.start_time if req.start_time else media_buy.start_time
                    end = req.end_time if req.end_time else media_buy.end_time

                    from datetime import datetime as dt

                    start_dt: datetime
                    end_dt: datetime

                    if isinstance(start, str):
                        if start == "asap":
                            start_dt = dt.now(UTC)
                        else:
                            start_dt = dt.fromisoformat(start.replace("Z", "+00:00"))
                    elif isinstance(start, datetime):
                        start_dt = start
                    else:
                        start_dt = dt.now(UTC)

                    if isinstance(end, str):
                        end_dt = dt.fromisoformat(end.replace("Z", "+00:00"))
                    elif isinstance(end, datetime):
                        end_dt = end
                    else:
                        end_dt = start_dt + timedelta(days=1)

                    flight_days = (end_dt - start_dt).days
                    if flight_days <= 0:
                        flight_days = 1

                    if currency_limit.max_daily_package_spend and req.packages:
                        for pkg_update in req.packages:
                            if pkg_update.budget is not None:
                                pkg_budget_amount: float
                                if isinstance(pkg_update.budget, int | float):
                                    pkg_budget_amount = float(pkg_update.budget)
                                else:
                                    pkg_budget_amount = float(pkg_update.budget.total)

                                package_daily_spend_error: str | None = validate_max_daily_package_spend(
                                    package_budget=Decimal(str(pkg_budget_amount)),
                                    flight_days=flight_days,
                                    max_daily_spend=currency_limit.max_daily_package_spend,
                                    currency=request_currency,
                                )
                                raise_if_validation_failed(
                                    package_daily_spend_error,
                                    exc_type=AdCPBudgetExceededError,
                                    context=req.context,
                                )

            # Handle campaign-level updates
            if req.paused is not None:
                # adcp 2.12.0+: paused=True means pause, paused=False means resume
                action = "pause_media_buy" if req.paused else "resume_media_buy"
                result = adapter.update_media_buy(
                    media_buy_id=req.media_buy_id,
                    action=action,
                    package_id=None,
                    budget=None,
                    today=utc_flight_start(today),
                )
                # Manual approval case - convert adapter result to appropriate Success/Error
                # adcp v1.2.1 oneOf pattern: Check if result is Error variant (has errors field)
                if isinstance(result, UpdateMediaBuyError) and result.errors:
                    error_response = UpdateMediaBuyError(errors=result.errors)
                    ctx_manager.audit_workflow_step_result(
                        step.step_id,
                        error_response,
                        status="failed",
                        error_message=result.errors[0].message if result.errors else "Pause/resume failed",
                    )
                    return UpdateMediaBuyResult(response=error_response, status=AdcpTaskStatus.failed.value)
                else:
                    # UpdateMediaBuySuccess extends adcp v1.2.1 with internal fields
                    # Use getattr to safely access discriminated union fields
                    media_buy_id = getattr(result, "media_buy_id", req.media_buy_id or "")
                    affected_pkgs = getattr(result, "affected_packages", [])

                    # Derive post-action status from the DB (date-refined for parity
                    # with get_media_buys — see _adcp_status_and_actions) so
                    # valid_actions reflects what the buyer can actually do next.
                    # Fall back to the current state-machine target only if the DB
                    # row is missing (e.g., adapter deleted it under us) — no row
                    # means no dates to refine.
                    # Persist the pause/resume OURSELVES. The adapter call above changes the
                    # ad server, not our row -- and this branch wrote nothing, so two things
                    # were silently lost. ``is_paused`` is read by _adcp_status_and_actions
                    # to derive the status we report, so a paused buy kept reporting as
                    # un-paused; and ``revision`` is the buyer's optimistic-concurrency
                    # token, which update-media-buy-response.json defines as "Revision
                    # number after this update", so the response returned the value from
                    # BEFORE the write. update_fields sets the column, bumps the revision and
                    # flushes, so the read below sees both.
                    uow.media_buys.update_fields(media_buy_id, is_paused=bool(req.paused))

                    _post_action_mb = uow.media_buys.get_by_id_or_raise(media_buy_id, context=req.context)
                    _post_action_revision = _post_action_mb.revision
                    _post_action_mbs, _post_action_actions = _adcp_status_and_actions(_post_action_mb)
                    success_response = UpdateMediaBuySuccess(
                        media_buy_id=media_buy_id,
                        revision=_post_action_revision,
                        media_buy_status=_post_action_mbs,  # AdCP 3.1: mirrors `status`
                        affected_packages=affected_pkgs,
                        valid_actions=_post_action_actions,
                        errors=property_list_unsupported_advisories(req.packages, adapter),
                    )
                    # Log successful update_media_buy (pause/resume)
                    audit_logger = get_audit_logger("AdCP", tenant["tenant_id"])
                    audit_logger.log_operation(
                        operation="update_media_buy",
                        principal_name=principal_id or "anonymous",
                        principal_id=principal_id or "anonymous",
                        adapter_id="mcp_server",
                        success=True,
                        details={
                            "media_buy_id": req.media_buy_id,
                            "action": action,
                            "affected_packages_count": len(affected_pkgs),
                        },
                    )
                    ctx_manager.audit_workflow_step_result(step.step_id, success_response)
                    return UpdateMediaBuyResult(response=success_response, status=AdcpTaskStatus.completed.value)

            # Handle package-level updates
            if req.packages:
                # enumerate so a per-package rejection can name WHICH package failed:
                # the pointer is packages[N].package_id, never packages[].package_id,
                # which named neither the array nor an element.
                for pkg_index, pkg_update in enumerate(req.packages):
                    # Handle paused state
                    if pkg_update.paused is not None:
                        # adcp 2.12.0+: paused=True means pause, paused=False means resume
                        action = "pause_package" if pkg_update.paused else "resume_package"
                        result = adapter.update_media_buy(
                            media_buy_id=req.media_buy_id,
                            action=action,
                            package_id=pkg_update.package_id,
                            budget=None,
                            today=utc_flight_start(today),
                        )
                        # adcp v1.2.1 oneOf pattern: Check if result is Error variant
                        if isinstance(result, UpdateMediaBuyError) and result.errors:
                            error_message = (
                                result.errors[0].message
                                if (result.errors and len(result.errors) > 0)
                                else "Update failed"
                            )
                            response_data = UpdateMediaBuyError(errors=result.errors)
                            ctx_manager.audit_workflow_step_result(
                                step.step_id,
                                response_data,
                                status="failed",
                                error_message=error_message,
                            )
                            return UpdateMediaBuyResult(response=response_data, status=AdcpTaskStatus.failed.value)

                    # Handle budget updates
                    if pkg_update.budget is not None:
                        # Validate package_id is provided (required for budget updates)
                        if not pkg_update.package_id:
                            raise AdCPValidationError(
                                field=package_field_path("package_id", pkg_index),
                                context=req.context,
                            )
                        # Extract budget amount - handle both float and Budget object
                        budget_amount: float
                        currency: str
                        if isinstance(pkg_update.budget, int | float):
                            budget_amount = float(pkg_update.budget)
                            # F-07: preserve existing DB currency rather than defaulting to USD
                            _existing_mb = uow.media_buys.get_by_id(req.media_buy_id)
                            currency = str(_existing_mb.currency) if _existing_mb and _existing_mb.currency else "USD"
                        else:
                            # Budget object with .total and .currency attributes
                            budget_amount = float(pkg_update.budget.total)
                            currency = str(pkg_update.budget.currency) if pkg_update.budget.currency else "USD"

                        # A zero or negative budget is BUDGET_TOO_LOW, not a fall-through.
                        # This check existed only on the campaign-level path, which AdCP
                        # 3.1.1 does not define -- so removing that path took the only
                        # positivity guard with it, and `if pkg_update.budget:` skipped 0.0 as
                        # falsy, leaving a zero budget to surface later as INVALID_STATE.
                        budget_positive_err = validate_budget_positive(
                            Decimal(str(budget_amount)), field=package_field_path("budget", pkg_index)
                        )
                        if budget_positive_err:
                            raise AdCPBudgetTooLowError(
                                field=package_field_path("budget", pkg_index),
                                context=req.context,
                            )

                        assert uow.currency_limits is not None
                        _cl = uow.currency_limits.get_for_currency(currency)
                        if _cl and _cl.min_package_budget:
                            # `currency` is keyword-only and REQUIRED; this call omitted it.
                            # It never raised because the enclosing guard was
                            # `if pkg_update.budget:` -- truthy-only, so a 0 budget (the one
                            # value that reliably reaches the minimum check) was skipped and
                            # the broken call was unreachable. Fixing the guard to
                            # `is not None` exposed it.
                            package_min_budget_error: str | None = validate_min_package_budget(
                                package_budget=Decimal(str(budget_amount)),
                                min_package_budget=Decimal(str(_cl.min_package_budget)),
                                currency=currency,
                            )
                            raise_if_validation_failed(
                                package_min_budget_error,
                                exc_type=AdCPBudgetTooLowError,
                                context=req.context,
                            )

                        # The package must exist in the media buy before we hand the
                        # budget change to the adapter — otherwise the adapter silently
                        # no-ops (quiet failure). Checked after the budget-value
                        # validation so a malformed budget still surfaces BUDGET_TOO_LOW.
                        # Raise PACKAGE_NOT_FOUND (BR-UC-003 ext-l).
                        uow.media_buys.get_package_or_raise(
                            req.media_buy_id, pkg_update.package_id, context=req.context
                        )

                        result = adapter.update_media_buy(
                            media_buy_id=req.media_buy_id,
                            action="update_package_budget",
                            package_id=pkg_update.package_id,
                            budget=int(budget_amount),
                            today=utc_flight_start(today),
                        )
                        # adcp v1.2.1 oneOf pattern: Check if result is Error variant
                        if isinstance(result, UpdateMediaBuyError) and result.errors:
                            error_message = (
                                result.errors[0].message
                                if (result.errors and len(result.errors) > 0)
                                else "Update failed"
                            )
                            response_data = UpdateMediaBuyError(errors=result.errors)
                            ctx_manager.audit_workflow_step_result(
                                step.step_id,
                                response_data,
                                status="failed",
                                error_message=error_message,
                            )
                            return UpdateMediaBuyResult(response=response_data, status=AdcpTaskStatus.failed.value)

                        # Track budget update in affected_packages
                        # At this point, pkg_update.package_id is guaranteed to be str (checked above)
                        affected_packages_list.append(
                            AffectedPackage(
                                package_id=pkg_update.package_id,  # Required by AdCP (guaranteed str)
                                paused=False,  # Package not paused (active)
                                buyer_package_ref=pkg_update.package_id,  # Internal field (for backward compat)
                                changes_applied={
                                    "budget": {"updated": budget_amount, "currency": currency}
                                },  # Internal field
                            )
                        )

                    # Handle creative_ids updates (AdCP v2.2.0+)
                    if pkg_update.creative_ids is not None:
                        # Validate package_id is provided
                        if not pkg_update.package_id:
                            raise AdCPValidationError(
                                field=package_field_path("package_id", pkg_index),
                                context=req.context,
                            )

                        # Resolve media_buy_id
                        media_buy_obj = uow.media_buys.get_by_id_or_raise(req.media_buy_id, context=req.context)

                        # Use the actual internal media_buy_id
                        actual_media_buy_id = media_buy_obj.media_buy_id

                        # Validate creatives (existence, status, format) via the
                        # shared helper so the rules match the creative_assignments path.
                        db_package = uow.media_buys.get_package(actual_media_buy_id, pkg_update.package_id)
                        product_id = (
                            db_package.package_config.get("product_id")
                            if db_package and db_package.package_config
                            else None
                        )
                        assert uow.products is not None
                        product = uow.products.get_by_id(product_id) if product_id else None
                        _validate_creatives_for_assignment(
                            pkg_update.creative_ids,
                            uow=uow,
                            principal_id=principal_id,
                            product=product,
                            context=req.context,
                        )

                        # Get existing assignments for this package
                        assignment_stmt = select(DBAssignment).where(
                            DBAssignment.tenant_id == tenant["tenant_id"],
                            DBAssignment.media_buy_id == actual_media_buy_id,
                            DBAssignment.package_id == pkg_update.package_id,
                        )
                        existing_assignments = session.scalars(assignment_stmt).all()
                        existing_creative_ids = {a.creative_id for a in existing_assignments}

                        # Determine added and removed creative IDs
                        requested_ids = set(pkg_update.creative_ids)
                        added_ids = requested_ids - existing_creative_ids
                        removed_ids = existing_creative_ids - requested_ids

                        # Remove old assignments
                        for assignment in existing_assignments:
                            if assignment.creative_id in removed_ids:
                                session.delete(assignment)

                        # Add new assignments
                        import uuid

                        for creative_id in added_ids:
                            assignment_id = f"assign_{uuid.uuid4().hex[:12]}"
                            assignment = DBAssignment(
                                assignment_id=assignment_id,
                                tenant_id=tenant["tenant_id"],
                                principal_id=principal_id,
                                media_buy_id=actual_media_buy_id,
                                package_id=pkg_update.package_id,
                                creative_id=creative_id,
                            )
                            session.add(assignment)

                        # If media buy was approved (approved_at set) but is in draft status
                        # (meaning it was approved without creatives), transition to pending_creatives
                        # Check whenever creative_ids are being set (not just when new ones added)
                        if (
                            pkg_update.creative_ids
                            and media_buy_obj.status == "draft"
                            and media_buy_obj.approved_at is not None
                        ):
                            uow.media_buys.update_status(actual_media_buy_id, PersistedMediaBuyStatus.PENDING_CREATIVES)
                            logger.info(
                                f"[UPDATE] Media buy {actual_media_buy_id} transitioned from draft to pending_creatives "
                                f"(creative_ids: {pkg_update.creative_ids})"
                            )

                        # Flush to persist assignment changes within the session
                        session.flush()

                        # Store results for affected_packages response
                        affected_packages_list.append(
                            AffectedPackage(
                                package_id=pkg_update.package_id,  # Required by AdCP
                                paused=False,  # Package not paused (active)
                                buyer_package_ref=pkg_update.package_id,  # Internal field (for backward compat)
                                changes_applied={  # Internal field
                                    "creative_ids": {
                                        "added": list(added_ids),
                                        "removed": list(removed_ids),
                                        "current": pkg_update.creative_ids,
                                    }
                                },
                            )
                        )

                    # Handle creatives (inline upload) - AdCP 2.5
                    if pkg_update.creatives:
                        # Validate package_id is provided
                        if not pkg_update.package_id:
                            raise AdCPValidationError(
                                field=package_field_path("package_id", pkg_index),
                                context=req.context,
                            )

                        # Sync creatives (upload/update)
                        # Built through the SAME builder the three transports use, rather
                        # than handed to _impl as loose fields. _sync_creatives_impl takes a
                        # request; an in-process caller that could not produce one was
                        # reaching into the tool instead of invoking it.
                        #
                        # account and idempotency_key are the OUTER request's, not invented:
                        # these creatives belong to that account, and that key is the
                        # client-generated identifier of the operation they are part of.
                        # Borrowing the key is harmless because idempotency lives at the
                        # transport boundary: this call enters the implementation directly,
                        # so it never touches the (agent, account, key) cache scope.
                        # A buyer's malformed inline creative raises here and travels
                        # untouched to the transport boundary, which names their field --
                        # nothing between this frame and that one may reclassify it.
                        sync_req = SyncCreativesRequest(
                            creatives=pkg_update.creatives,
                            account=req.account,
                            idempotency_key=req.idempotency_key,
                            context=req.context,
                            # The typed Assignment the request model declares, not the
                            # {creative_id: [package_id]} map this used to build. That
                            # map was a second, internal-only spelling of the same
                            # relation, and it forced _sync_creatives_impl to accept a
                            # dict as well as the spec's list -- so the one internal
                            # caller widened the type for every transport.
                            assignments=[
                                Assignment(creative_id=c.creative_id, package_id=pkg_update.package_id)
                                for c in pkg_update.creatives
                                if c.creative_id
                            ],
                        )
                        sync_response = _sync_creatives_impl(
                            req=sync_req,
                            identity=identity,
                        )

                        # Check for sync errors
                        failed_creatives = [r for r in sync_response.creatives if r.action == "failed"]
                        if failed_creatives:
                            raise AdCPAdapterError(
                                context=req.context,
                                # ``e.code`` rather than ``e.message``: the message is a
                                # function of the code through CODE_TABLE, so the code is
                                # the fact and the sentence is derivable from it. Sending
                                # the sentence made the buyer parse prose to learn which
                                # creative failed and why.
                                details=AdapterFailureDetails(
                                    problems=[
                                        ErrorProblem(
                                            code=err.code,
                                            subject_type="creative",
                                            subject_id=r.creative_id,
                                        )
                                        for r in failed_creatives
                                        for err in r.errors or []
                                    ]
                                ),
                            )

                        # Track in affected_packages
                        synced_ids = [
                            r.creative_id for r in sync_response.creatives if r.action in ["created", "updated"]
                        ]
                        affected_packages_list.append(
                            AffectedPackage(
                                package_id=pkg_update.package_id,
                                paused=False,
                                buyer_package_ref=pkg_update.package_id,
                                changes_applied={"creatives_uploaded": synced_ids},
                            )
                        )

                    # Handle creative_assignments (weight/placement updates) - adcp#208
                    if pkg_update.creative_assignments:
                        # Validate package_id is provided
                        if not pkg_update.package_id:
                            raise AdCPValidationError(
                                field=package_field_path("package_id", pkg_index),
                                context=req.context,
                            )

                        # Resolve media_buy_id
                        media_buy_obj = uow.media_buys.get_by_id_or_raise(req.media_buy_id, context=req.context)

                        actual_media_buy_id = media_buy_obj.media_buy_id

                        # Validate referenced creatives (existence, status, format) BEFORE
                        # building any assignment rows — otherwise a not-found creative_id
                        # would surface as a composite-FK IntegrityError. Same rules as the
                        # creative_ids path via the shared helper.
                        ca_package = uow.media_buys.get_package(actual_media_buy_id, pkg_update.package_id)
                        ca_product_id = (
                            ca_package.package_config.get("product_id")
                            if ca_package and ca_package.package_config
                            else None
                        )
                        assert uow.products is not None
                        ca_product = uow.products.get_by_id(ca_product_id) if ca_product_id else None
                        _validate_creatives_for_assignment(
                            [ca.creative_id for ca in pkg_update.creative_assignments],
                            uow=uow,
                            principal_id=principal_id,
                            product=ca_product,
                            context=req.context,
                        )

                        # Validate placement_ids against product's available placements (adcp#208)
                        # Build set of placement_ids from all creative_assignments
                        all_requested_placement_ids: set[str] = set()
                        for ca in pkg_update.creative_assignments:
                            if ca.placement_ids:
                                all_requested_placement_ids.update(ca.placement_ids)

                        if all_requested_placement_ids:
                            # Get package to find product_id
                            pkg_record = uow.media_buys.get_package_or_raise(
                                actual_media_buy_id, pkg_update.package_id, context=req.context
                            )

                            product_id = (
                                pkg_record.package_config.get("product_id") if pkg_record.package_config else None
                            )

                            if product_id:
                                # Get product's placements
                                prod_stmt = select(DBProduct).where(
                                    DBProduct.tenant_id == tenant["tenant_id"],
                                    DBProduct.product_id == product_id,
                                )
                                product_obj = session.scalars(prod_stmt).first()

                                if product_obj and product_obj.placements:
                                    available_placement_ids: set[str] = {
                                        str(p.get("placement_id"))
                                        for p in product_obj.placements
                                        if p.get("placement_id")
                                    }
                                    invalid_ids = all_requested_placement_ids - available_placement_ids
                                    if invalid_ids:
                                        raise AdCPValidationError(
                                            field="creative_assignments[].placement_ids",
                                            context=req.context,
                                        )
                                elif product_obj and not product_obj.placements:
                                    # Product doesn't define placements, so placement targeting not supported
                                    raise AdCPCapabilityNotSupportedError(
                                        details=CapabilityRefusalDetails(product_id=product_id),
                                        context=req.context,
                                    )

                        updated_assignments = []
                        new_assignments_created = []

                        # BR-RULE-024 INV-2: creative_assignments replaces ALL existing
                        # assignments for this package. Delete existing assignments not
                        # in the new list, matching the creative_ids handler pattern.
                        requested_creative_ids = {ca.creative_id for ca in pkg_update.creative_assignments}
                        existing_stmt = select(DBAssignment).where(
                            DBAssignment.tenant_id == tenant["tenant_id"],
                            DBAssignment.media_buy_id == actual_media_buy_id,
                            DBAssignment.package_id == pkg_update.package_id,
                        )
                        existing_assignments = session.scalars(existing_stmt).all()
                        for existing in existing_assignments:
                            if existing.creative_id not in requested_creative_ids:
                                session.delete(existing)

                        for ca in pkg_update.creative_assignments:
                            # Schema validates and coerces dict inputs to LibraryCreativeAssignment
                            creative_id = ca.creative_id
                            weight = ca.weight
                            placement_ids = ca.placement_ids

                            # Find or create assignment record. principal_id is part of
                            # the match key: the same creative_id can exist under two
                            # principals (composite creatives PK), and the create branch
                            # below inserts under the requester's principal.
                            assign_stmt = select(DBAssignment).where(
                                DBAssignment.tenant_id == tenant["tenant_id"],
                                DBAssignment.principal_id == principal_id,
                                DBAssignment.media_buy_id == actual_media_buy_id,
                                DBAssignment.package_id == pkg_update.package_id,
                                DBAssignment.creative_id == creative_id,
                            )
                            db_assignment = session.scalars(assign_stmt).first()

                            if db_assignment:
                                # Update existing assignment
                                if weight is not None:
                                    db_assignment.weight = int(weight)
                                # adcp#208: persist placement_ids for placement-specific targeting
                                if placement_ids is not None:
                                    db_assignment.placement_ids = placement_ids
                                updated_assignments.append(creative_id)
                            else:
                                # Create new assignment with weight and placement_ids
                                import uuid as uuid_module

                                assignment_id = f"assign_{uuid_module.uuid4().hex[:12]}"
                                new_assignment = DBAssignment(
                                    assignment_id=assignment_id,
                                    tenant_id=tenant["tenant_id"],
                                    principal_id=principal_id,
                                    media_buy_id=actual_media_buy_id,
                                    package_id=pkg_update.package_id,
                                    creative_id=creative_id,
                                    weight=int(weight) if weight is not None else 100,
                                    # adcp#208: placement-specific targeting
                                    placement_ids=placement_ids,
                                )
                                session.add(new_assignment)
                                updated_assignments.append(creative_id)
                                new_assignments_created.append(creative_id)

                        # If media buy was approved (approved_at set) but is in draft status
                        # (meaning it was approved without creatives), transition to pending_creatives
                        # Check whenever creative_assignments are being set (not just when new ones created)
                        if (
                            pkg_update.creative_assignments
                            and media_buy_obj.status == "draft"
                            and media_buy_obj.approved_at is not None
                        ):
                            uow.media_buys.update_status(actual_media_buy_id, PersistedMediaBuyStatus.PENDING_CREATIVES)
                            logger.info(
                                f"[UPDATE] Media buy {actual_media_buy_id} transitioned from draft to pending_creatives "
                                f"(creative_assignments processed: {updated_assignments})"
                            )

                        # Flush to persist assignment changes within the session
                        session.flush()

                        # Track in affected_packages
                        affected_packages_list.append(
                            AffectedPackage(
                                package_id=pkg_update.package_id,
                                paused=False,
                                buyer_package_ref=pkg_update.package_id,
                                changes_applied={"creative_assignments_updated": updated_assignments},
                            )
                        )

                    # Handle targeting_overlay updates
                    if pkg_update.targeting_overlay is not None:
                        # Validate package_id is provided
                        if not pkg_update.package_id:
                            raise AdCPValidationError(
                                field=package_field_path("package_id", pkg_index),
                                context=req.context,
                            )

                        from sqlalchemy.orm import attributes

                        # Get the package via repository
                        media_package = uow.media_buys.get_package_or_raise(
                            req.media_buy_id, pkg_update.package_id, context=req.context
                        )

                        # property_targeting_allowed validation runs earlier (before dry_run gate);
                        # by this point the request is known-valid against that rule.

                        # Store Targeting model directly — engine's pydantic_core.to_json serializer handles it
                        media_package.package_config["targeting_overlay"] = pkg_update.targeting_overlay
                        # Flag the JSON field as modified so SQLAlchemy persists it
                        attributes.flag_modified(media_package, "package_config")
                        session.flush()
                        logger.info(
                            f"[update_media_buy] Updated package {pkg_update.package_id} targeting: {pkg_update.targeting_overlay}"
                        )

                        # Track targeting update in affected_packages
                        affected_packages_list.append(
                            AffectedPackage(
                                package_id=pkg_update.package_id,
                                paused=False,  # Package not paused (active)
                                changes_applied={"targeting": pkg_update.targeting_overlay},
                                buyer_package_ref=pkg_update.package_id,  # Legacy compatibility
                            )
                        )

            # A campaign-level budget update is not expressible in AdCP 3.1.1: the request
            # schema declares no top-level budget, so the block that lived here -- validating
            # and persisting req.budget, then marking every package affected -- had no way to
            # be reached by a conformant buyer. Package budgets are handled above, per
            # package, where the spec puts them (package-update.json /properties/budget).
            # Handle start_time/end_time updates
            if req.start_time is not None or req.end_time is not None:
                # TODO: Sync date changes to GAM order
                # Currently only updates database - does NOT sync to GAM API
                # This creates data inconsistency between our database and GAM
                # Need to implement: adapter.orders_manager.update_order_dates(order_id, start_time, end_time)

                update_values: dict[str, Any] = {}
                if req.start_time is not None:
                    # Parse start_time (handle 'asap' and datetime strings)
                    if isinstance(req.start_time, str):
                        if req.start_time == "asap":
                            update_values["start_time"] = datetime.now(UTC)
                        else:
                            update_values["start_time"] = datetime.fromisoformat(req.start_time.replace("Z", "+00:00"))
                    elif isinstance(req.start_time, datetime):
                        update_values["start_time"] = req.start_time

                if req.end_time is not None:
                    # Parse end_time (datetime string or datetime object)
                    if isinstance(req.end_time, str):
                        update_values["end_time"] = datetime.fromisoformat(req.end_time.replace("Z", "+00:00"))
                    elif isinstance(req.end_time, datetime):
                        update_values["end_time"] = req.end_time

                if update_values:
                    # Get existing media buy to check date range consistency
                    existing_mb = uow.media_buys.get_by_id_or_raise(req.media_buy_id, context=req.context)

                    # Validate date range: end_time must be after start_time
                    # Type guard: Ensure we're working with datetime objects (not SQLAlchemy DateTime)
                    start_val = update_values.get("start_time", existing_mb.start_time)
                    end_val = update_values.get("end_time", existing_mb.end_time)

                    # Convert to Python datetime if needed (handle SQLAlchemy DateTime)
                    final_start_time: datetime | None = None
                    final_end_time: datetime | None = None

                    if start_val is not None:
                        final_start_time = (
                            start_val if isinstance(start_val, datetime) else datetime.fromisoformat(str(start_val))
                        )
                    if end_val is not None:
                        final_end_time = (
                            end_val if isinstance(end_val, datetime) else datetime.fromisoformat(str(end_val))
                        )

                    if final_start_time and final_end_time and final_end_time <= final_start_time:
                        raise AdCPValidationError(
                            field="end_time",
                            context=req.context,
                        )

                    uow.media_buys.update_fields(req.media_buy_id, **update_values)
                    logger.warning(
                        f"Updated MediaBuy {req.media_buy_id} dates in database ONLY: "
                        f"start_time={update_values.get('start_time')}, end_time={update_values.get('end_time')}"
                    )
                    logger.warning("GAM sync NOT implemented - GAM still has old dates")

            # Create ObjectWorkflowMapping to link media buy update to workflow step
            # This enables webhook delivery when the update completes
            mapping = ObjectWorkflowMapping(
                step_id=step.step_id,
                object_type="media_buy",
                object_id=req.media_buy_id,
                action="update",
            )
            session.add(mapping)

            # Build final response first
            logger.info(f"[update_media_buy] Final affected_packages before return: {affected_packages_list}")

            # UpdateMediaBuySuccess extends adcp v1.2.1 with internal fields (workflow_step_id, affected_packages)
            # affected_packages_list contains AffectedPackage objects with both:
            # - AdCP-required fields (package_id) for spec compliance
            # - Internal tracking fields (buyer_package_ref, changes_applied) excluded via exclude=True

            _final_mb = uow.media_buys.get_by_id_or_raise(req.media_buy_id or "", context=req.context)
            _final_revision = _final_mb.revision
            _final_mbs, _final_actions = _adcp_status_and_actions(_final_mb)
            final_response = UpdateMediaBuySuccess(
                media_buy_id=req.media_buy_id or "",
                revision=_final_revision,
                media_buy_status=_final_mbs,  # AdCP 3.1: mirrors `status`
                affected_packages=affected_packages_list,
                valid_actions=_final_actions,
                context=req.context,
                errors=property_list_unsupported_advisories(req.packages, adapter),
            )

            # Log successful update_media_buy call
            audit_logger = get_audit_logger("AdCP", tenant["tenant_id"])
            audit_logger.log_operation(
                operation="update_media_buy",
                principal_name=principal_id or "anonymous",
                principal_id=principal_id or "anonymous",
                adapter_id="mcp_server",
                success=True,
                details={
                    "media_buy_id": req.media_buy_id,
                    "affected_packages_count": len(affected_packages_list),
                    "has_budget_update": bool(req.packages and any(pkg.budget is not None for pkg in req.packages)),
                    "has_pause_update": req.paused is not None,
                    "has_packages_update": req.packages is not None and len(req.packages) > 0,
                },
            )

            # Persist success with response data, then return
            # Use mode="json" to ensure enums are serialized as strings for JSONB storage
            ctx_manager.audit_workflow_step_result(step.step_id, final_response)

        return UpdateMediaBuyResult(response=final_response, status=AdcpTaskStatus.completed.value)


def _normalize_pacing(pacing: str | None) -> Literal["even", "asap", "daily_budget"]:
    """Coerce the flat pacing string to the Budget literal, defaulting to even."""
    if pacing == "asap":
        return "asap"
    if pacing == "daily_budget":
        return "daily_budget"
    return "even"
