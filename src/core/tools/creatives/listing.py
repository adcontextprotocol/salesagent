"""List creatives implementation, MCP wrapper, and A2A raw function."""

import logging
import time
from datetime import UTC, datetime
from typing import Any, cast

from src.core.audit_logger import get_audit_logger
from src.core.auth import require_identity, require_principal_id, require_tenant
from src.core.database.repositories.uow import CreativeUoW
from src.core.errors.codes import ErrorCode
from src.core.errors.details import EntityRefDetails
from src.core.helpers import enum_value, log_tool_activity
from src.core.logging_config import log_safe
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas import (
    Creative,
    Error,
    ListCreativesRequest,
    ListCreativesResponse,
)

logger = logging.getLogger(__name__)


def _log_blob_drop(shape: str, field_label: str, log_context: str, *, value_type: str | None = None) -> None:
    """Emit the one drop-warning template shared by every blob coercer.

    All four blob-drop sites — the non-scalar/non-dict/non-list whole-value drops and the
    null-element drop inside a list — route through this single emitter so the message shape
    cannot drift out of lockstep: a reworded stem or a new attribution field lands in one place
    instead of four. ``value_type`` present renders the "...value of type X..." form (a corrupt
    whole value); ``value_type`` absent renders the "...element..." form (a corrupt element inside
    an otherwise-valid list). ``log_context`` is the optional operator-attribution suffix built by
    :func:`_blob_log_context` (empty for the pure-function callers).
    """
    if value_type is None:
        logger.warning("Dropping %s %s element from creative listing%s", shape, field_label, log_context)
    else:
        logger.warning(
            "Dropping %s %s value of type %s from creative listing%s",
            shape,
            field_label,
            value_type,
            log_context,
        )


def _coerce_blob_scalar(value: Any, field_label: str, *, log_context: str = "") -> str | None:
    """Coerce an untyped JSON-blob value to a spec string field.

    Fields like ``concept_id``/``concept_name`` are strings per the AdCP response
    schema but live in the untyped JSON ``data`` blob, where an out-of-band producer
    may write a non-string scalar (e.g. a numeric CM360 group id). Scalars are
    stringified. A non-scalar (list/dict) is corrupt for a string field, so it is
    dropped with a warning — surfaced in logs (No Quiet Failures) rather than projected
    as a Python repr — instead of crashing the whole listing on one bad row.

    ``field_label`` is required (never defaulted) so a dropped value names its own field
    in the log rather than borrowing a sibling's attribution. ``log_context`` is an optional
    operator-attribution suffix (the corrupt row's creative/tenant/principal ids, built by
    :func:`_blob_log_context`) appended to the drop warning so the bad row can be traced and
    repaired; it defaults to empty for the pure-function callers (unit tests). Surfacing the
    drop to the buyer as a response advisory (``ListCreativesResponse.errors[]``) instead of
    log-only is a deliberate deferral, tracked in #1779.
    """
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):  # bool is an int subclass; str(True)="True" is acceptable
        return str(value)
    _log_blob_drop("non-scalar", field_label, log_context, value_type=type(value).__name__)
    return None


def _coerce_blob_dict(value: Any, field_label: str, *, log_context: str = "") -> dict[str, Any] | None:
    """Coerce an untyped JSON-blob value to a spec object (dict) field.

    ``Creative.assets`` is typed ``dict[str, Any] | None`` but is read from the untyped
    ``data`` blob, where the same out-of-band producer that can corrupt the scalar and
    list fields may write a non-object value. A non-dict is corrupt for an object field
    and dropped to ``None`` with a warning (No Quiet Failures) instead of failing
    Creative validation and crashing the whole listing on one bad row — the object-field
    sibling of :func:`_coerce_blob_scalar` / :func:`_coerce_blob_str_list`. ``log_context``
    is the same optional operator-attribution suffix documented on :func:`_coerce_blob_scalar`.

    This guarantees dict-*ness* only: a well-formed ``dict`` passes through unvalidated, so a
    corrupt inner value (a ``null`` asset value, a non-``^[a-z0-9_]+$`` key) still reaches the
    wire — inner asset-union validation against ``core/creative-asset.json`` is tracked in
    #1779. Unlike the empty-list collapse in :func:`_coerce_blob_str_list`, an empty ``{}`` is
    *preserved* (not collapsed to absent): ``assets`` is required on the sync input
    (``core/creative-asset.json``), so ``{}`` is the presence-preserving projection and
    ``exclude_none`` keeps it on the wire.
    """
    if value is None or isinstance(value, dict):
        return value
    _log_blob_drop("non-dict", field_label, log_context, value_type=type(value).__name__)
    return None


def _coerce_blob_str_list(value: Any, field_label: str, *, log_context: str = "") -> list[str] | None:
    """Coerce an untyped JSON-blob value to a spec ``list[str]`` field.

    ``Creative.tags`` is typed ``list[str] | None`` but is read from the untyped
    ``data`` blob, where a malformed value (a bare string, or a list with numeric /
    object / null elements) would fail Creative validation and crash the whole listing
    on one bad row — the same untyped-blob hazard :func:`_coerce_blob_scalar` handles for
    the scalar concept fields. A non-list value is corrupt for a list field and dropped
    to ``None`` with a warning. Within a list a ``null`` element is corrupt for an
    ``items: {type: string}`` list (a JSON ``null`` is not an absent value here) and is
    dropped with a warning; every other element is coerced via :func:`_coerce_blob_scalar`
    (scalars stringified, non-scalars dropped+logged), so ``[1, 2] -> ["1", "2"]`` and
    ``[{...}]`` drops the bad element. ``log_context`` is the same optional
    operator-attribution suffix documented on :func:`_coerce_blob_scalar`.

    Finally an empty (or fully-emptied) list collapses to ``None`` so ``exclude_none``
    omits the key: the pinned 3.1.1 ``creative/list-creatives-response`` schema permits
    both ``[]`` and omission, and this list field standardizes on omission (the object-field
    sibling :func:`_coerce_blob_dict` instead *preserves* an empty ``{}`` — see its docstring).
    That collapse is a valid-input serialization choice, not a corruption drop, so — unlike
    the drops above — it is logged at ``debug`` (traceability), never ``warning``.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        _log_blob_drop("non-list", field_label, log_context, value_type=type(value).__name__)
        return None
    coerced: list[str] = []
    for element in value:
        if element is None:
            _log_blob_drop("null", field_label, log_context)
            continue
        scalar = _coerce_blob_scalar(element, field_label, log_context=log_context)
        if scalar is not None:
            coerced.append(scalar)
    if not coerced:
        logger.debug("Collapsing empty %s list to absent in creative listing", field_label)
        return None
    return coerced


def _blob_log_context(creative_id: str, tenant_id: str, principal_id: str) -> str:
    """Operator-attribution suffix appended to a blob-coercion drop warning.

    Names the corrupt row (creative/tenant/principal) so an operator can trace and repair the
    out-of-band data defect — the drop warnings are otherwise per-field but per-*row* anonymous.
    Passed by the ``_list_creatives_impl`` row loop; the coercers default the suffix to empty so
    their pure-function unit tests stay attribution-free.

    Each id is passed through :func:`log_safe` before interpolation: ``creative_id`` (buyer-supplied)
    and the tenant/principal ids reach this log line, so an embedded CR/LF would forge log entries
    (CodeQL ``py/log-injection``). Neutralizing CR/LF here — the single choke point every drop
    warning routes through — closes the taint on all four drop sites at once.
    """
    return (
        f" (creative_id={log_safe(creative_id)} tenant_id={log_safe(tenant_id)} principal_id={log_safe(principal_id)})"
    )


def _list_creatives_impl(
    req: "ListCreativesRequest",
    identity: ResolvedIdentity | None = None,
) -> ListCreativesResponse:
    """List and search creative library (AdCP v2.5 spec endpoint).

    Advanced filtering and search endpoint for the centralized creative library.
    Supports pagination, sorting, and multiple filter criteria.

    Args:
        req: Typed list-creatives request — EVERY request value, including the two
            internal ``format`` / ``page`` fields, which are why this is typed to
            ListCreativesRequest and not to the buyer-facing ListCreativesRequest
        identity: ResolvedIdentity with principal/tenant info (transport-agnostic)

    Returns:
        ListCreativesResponse with filtered creative assets and pagination info
    """
    from typing import Literal

    # Derive flat DB-query params from the structured request.
    req_filters = req.filters
    # Internal fields, read off the request like every other value it carries. They were
    # ``_impl`` PARAMETERS until this was fixed, which meant a caller could hand the reader
    # a page or a format the request it was answering did not describe.
    # Always 1: nothing in src/ ever set the internal knob this replaced. Buyers page
    # through the spec's ``pagination``.
    page = 1
    # This status string is matched against the RAW persisted `creatives.status` column
    # (CreativeRepository.get_by_principal), while the value rendered on the wire is
    # derived from it below — and for a row whose stored status is not a CreativeStatus
    # member, the reader substitutes a placeholder. The two therefore disagree on
    # purpose: an unreadable row appears in an UNFILTERED read (rendered `processing`,
    # plus an errors[] advisory) and is ABSENT from `list_creatives(status="processing")`.
    # That asymmetry is deliberate, and it is the opposite of the choice made for the
    # unfiltered read on purpose: a filtered read is scoped to a status the buyer NAMED,
    # and a row we could not parse is not KNOWN to be that status, so excluding it answers
    # the buyer's actual question. Omitting it from the unfiltered read would instead be a
    # second lie ("this creative does not exist") and would desynchronise
    # query_summary.returned from total_matching. Do NOT "fix" this by mapping the
    # placeholder back onto the filter — that would report the row as confirmed
    # `processing`. Graded by
    # tests/integration/test_list_creatives_unrecognized_status.py::TestFilteredReadExcludesTheUnreadableRow.
    status = enum_value(req_filters.statuses[0]) if req_filters and req_filters.statuses else None
    tags = req_filters.tags if req_filters else None
    created_after_dt = req_filters.created_after if req_filters else None
    created_before_dt = req_filters.created_before if req_filters else None
    search = req_filters.name_contains if req_filters else None
    effective_media_buy_ids = list(req_filters.media_buy_ids) if req_filters and req_filters.media_buy_ids else []
    # v3.1 concept_ids filter has no flat equivalent — it arrives only via the structured
    # filters object and must be threaded into the DB query (not merely reported in
    # filters_applied), or it would be silently dropped. (#1493)
    effective_concept_ids = req_filters.concept_ids if req_filters else None

    sort_by = enum_value(req.sort.field) if req.sort and req.sort.field else "created_date"
    valid_sort_order: Literal["asc", "desc"] = cast(
        Literal["asc", "desc"],
        enum_value(req.sort.direction) if req.sort and req.sort.direction else "desc",
    )

    effective_limit = min(req.pagination.max_results, 1000) if req.pagination and req.pagination.max_results else 50
    # Page is out-of-band (cursor-based pagination has no page index); preserve offset math.
    limit = effective_limit
    offset = (page - 1) * effective_limit

    start_time = time.time()

    # Authentication - REQUIRED (creatives contain sensitive data)
    # Unlike discovery endpoints (list_creative_formats), this returns actual creative assets
    # which are principal-specific and must be access-controlled
    # require_principal_id first so the canonical auth message surfaces for missing/anonymous auth;
    # require_identity narrows the type for the tenant lookup below.
    principal_id = require_principal_id(identity, context=req.context)
    identity = require_identity(identity, context=req.context)
    tenant = require_tenant(identity, context=req.context)

    creatives = []
    total_count = 0
    # Advisories for rows whose stored status this reader cannot parse. Bound here (not a
    # parameter) so the loop handler below has a container to surface into; emitted on the
    # response's errors[] at the bottom of this function.
    unreadable_status_advisories: list[Error] = []

    with CreativeUoW(tenant["tenant_id"]) as uow:
        assert uow.creatives is not None
        result = uow.creatives.get_by_principal(
            principal_id,
            status=status,
            format=None,
            tags=tags,
            created_after=created_after_dt,
            created_before=created_before_dt,
            search=search,
            media_buy_ids=effective_media_buy_ids or None,
            concept_ids=effective_concept_ids,
            sort_by=sort_by,
            sort_order=valid_sort_order,
            offset=offset,
            limit=effective_limit,
        )
        db_creatives = result.creatives
        total_count = result.total_count

        # Convert to schema objects
        for db_creative in db_creatives:
            # Handle content_uri - required field even for snippet creatives
            # For snippet creatives, provide an HTML-looking URL to pass validation
            snippet = db_creative.data.get("snippet") if db_creative.data else None
            if snippet:
                content_uri = (
                    db_creative.data.get("url") or "<script>/* Snippet-based creative */</script>"
                    if db_creative.data
                    else "<script>/* Snippet-based creative */</script>"
                )
            else:
                content_uri = (
                    db_creative.data.get("url") or "https://placeholder.example.com/missing.jpg"
                    if db_creative.data
                    else "https://placeholder.example.com/missing.jpg"
                )

            # Build Creative directly with explicit types to satisfy mypy
            from src.core.schemas import FormatId, url

            # Build FormatId with optional parameters (AdCP 2.5 format templates)
            format_kwargs: dict[str, Any] = {
                "agent_url": url(db_creative.agent_url),
                "id": db_creative.format or "",
            }
            # Add format parameters if present
            if db_creative.format_parameters:
                params = db_creative.format_parameters
                if "width" in params:
                    format_kwargs["width"] = params["width"]
                if "height" in params:
                    format_kwargs["height"] = params["height"]
                if "duration_ms" in params:
                    format_kwargs["duration_ms"] = params["duration_ms"]

            format_obj = FormatId(**format_kwargs)

            # Ensure datetime fields are timezone-aware (database may store naive datetimes)
            if isinstance(db_creative.created_at, datetime):
                created_at_dt = (
                    db_creative.created_at.replace(tzinfo=UTC)
                    if db_creative.created_at.tzinfo is None
                    else db_creative.created_at
                )
            else:
                created_at_dt = datetime.now(UTC)

            if isinstance(db_creative.updated_at, datetime):
                updated_at_dt = (
                    db_creative.updated_at.replace(tzinfo=UTC)
                    if db_creative.updated_at.tzinfo is None
                    else db_creative.updated_at
                )
            else:
                updated_at_dt = datetime.now(UTC)

            # AdCP v1 spec compliant - only spec fields
            # Get assets dict from database (all production data uses AdCP v2.4 format)
            assets_dict = db_creative.data.get("assets", {}) if db_creative.data else {}

            # Convert string status to CreativeStatus enum
            from src.core.schemas import CreativeStatus

            try:
                status_enum = CreativeStatus(db_creative.status)
            except ValueError:
                # A stored status that is not a CreativeStatus member. AdCP 3.1.1
                # list-creatives-response.json makes `status` REQUIRED on every item and
                # $refs a CLOSED 6-member enum with no `unknown`, so some value must be
                # emitted — every choice makes some claim, which is why the errors[]
                # advisory below, not the placeholder, is the honest part of this handler.
                # `processing` is the placeholder because it is the only member asserting
                # no completed evaluation, no deliverability and no seller MUST;
                # `pending_review` is the worst choice (it asserts processing already
                # succeeded AND that the seller owes a decision, i.e. "wait for us").
                #
                # The advisory code is PINNED to CONFIGURATION_ERROR: normalize_advisory_errors
                # used to collapse any unclassified code to SERVICE_UNAVAILABLE /
                # recovery=transient — which would tell the buyer to retry a permanently
                # bad row forever. Honest caveat: CONFIGURATION_ERROR's pinned prose says
                # "prevents handling the request" and here the request IS handled; it is
                # nonetheless the only wire-standard code whose recovery (`terminal`) and
                # remediation ("surface to a human at the seller — the buyer cannot resolve
                # a seller-side deployment misconfiguration and MUST NOT auto-retry") both
                # match. INVALID_STATE is `correctable` (implies the buyer can fix the
                # request — false); SERVICE_UNAVAILABLE is `transient` (implies retry).
                logger.warning(
                    "Creative %s (tenant %s) has unreadable stored status %r; reporting it as "
                    "'processing' and surfacing an advisory",
                    db_creative.creative_id,
                    tenant["tenant_id"],
                    db_creative.status,
                )
                unreadable_status_advisories.append(
                    # The stored status is INTERNAL state -- by definition not in the
                    # AdCP creative vocabulary, which is why this branch fired -- so it
                    # does not go on the buyer's wire. The logger above already records
                    # it for the operator. The buyer gets the code (whose sentence and
                    # recovery come from CODE_TABLE) plus the one specific they can act
                    # on: which creative is affected.
                    Error.of(  # structural-guard: advisory per-creative result in ListCreativesResponse.errors[]
                        ErrorCode.CONFIGURATION_ERROR,
                        details=EntityRefDetails(creative_id=db_creative.creative_id),
                    )
                )
                status_enum = CreativeStatus.processing

            # v3.1 concept grouping. AdCP exposes concept_id/concept_name on the
            # list_creatives RESPONSE (a creative's concept membership, sourced from
            # the buyer's creative-management platform — Flashtalking/Celtra/CM360),
            # but standardizes no concept INPUT on sync_creatives, so the field is
            # populated out-of-band into the data blob. (A seller-side mapping of GAM
            # creative groups -> these fields is a separate enrichment/fallback
            # follow-up (#1506), not the authoritative buyer-side concept.) The blob is
            # untyped and an external producer may write numeric group ids, so coerce
            # each field to the spec's string type via _coerce_blob_scalar (with the
            # field's own label) rather than letting a non-string value fail Creative
            # validation and crash the whole listing.
            data_blob = db_creative.data or {}
            # Operator-attribution for any coercion drop below: names this row so a corrupt
            # blob value can be traced and repaired (the drops are otherwise per-row anonymous).
            # Keyword args so the id→label mapping is explicit at the call site (a transposition
            # would be a visible mislabel, and the wiring test pins it either way).
            row_log_context = _blob_log_context(
                creative_id=db_creative.creative_id,
                tenant_id=tenant["tenant_id"],
                principal_id=db_creative.principal_id,
            )

            creative = Creative(
                creative_id=db_creative.creative_id,
                name=db_creative.name,
                format_id=format_obj,
                # assets is read from the same untyped blob; a stored non-dict value
                # would fail Creative validation and crash the whole listing, so coerce
                # it (drop+log a non-dict) — the object-field sibling of the tags/concept
                # coercion (#1508).
                assets=_coerce_blob_dict(assets_dict, "assets", log_context=row_log_context),
                # tags is typed list[str] but read from the untyped blob, where an
                # external producer may write a malformed value (a bare string, or
                # [1, 2]) that would fail Creative validation and crash the whole
                # listing — coerce it (stringify scalars, drop+log corrupt data), the
                # same hazard _coerce_blob_scalar handles for the concept fields (#1508).
                tags=_coerce_blob_str_list(data_blob.get("tags"), "tags", log_context=row_log_context),
                # AdCP spec fields (listing Creative)
                status=status_enum,
                created_date=created_at_dt,
                updated_date=updated_at_dt,
                concept_id=_coerce_blob_scalar(data_blob.get("concept_id"), "concept_id", log_context=row_log_context),
                concept_name=_coerce_blob_scalar(
                    data_blob.get("concept_name"), "concept_name", log_context=row_log_context
                ),
                # Internal field (our extension)
                principal_id=db_creative.principal_id,
            )
            creatives.append(creative)

    # Calculate pagination info (page and limit have defaults from factory function)
    has_more = (page * limit) < total_count
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 0

    # Build filters_applied list from structured filters (typed CreativeFilters model)
    filters_applied: list[str] = []
    if req.filters:
        if req.filters.media_buy_ids:
            filters_applied.append(f"media_buy_ids={','.join(req.filters.media_buy_ids)}")
        if req.filters.statuses:
            filters_applied.append(f"statuses={','.join(str(s) for s in req.filters.statuses)}")
        if req.filters.format_ids:
            filters_applied.append(f"format_ids={','.join(str(f) for f in req.filters.format_ids)}")
        if req.filters.tags:
            filters_applied.append(f"tags={','.join(req.filters.tags)}")
        if req.filters.concept_ids:
            filters_applied.append(f"concept_ids={','.join(req.filters.concept_ids)}")
        if req.filters.created_after:
            filters_applied.append(f"created_after={req.filters.created_after.isoformat()}")
        if req.filters.created_before:
            filters_applied.append(f"created_before={req.filters.created_before.isoformat()}")
        if req.filters.name_contains:
            filters_applied.append(f"search={req.filters.name_contains}")

    # Build sort_applied dict from structured sort
    sort_applied = None
    if req.sort and req.sort.field and req.sort.direction:
        sort_applied = {"field": req.sort.field.value, "direction": req.sort.direction.value}

    # Audit logging
    audit_logger = get_audit_logger("AdCP", tenant["tenant_id"])
    audit_logger.log_operation(
        operation="list_creatives",
        principal_name=principal_id,
        principal_id=principal_id,
        adapter_id="N/A",
        success=True,
        details={
            "result_count": len(creatives),
            "total_count": total_count,
            "page": page,
            "filters_applied": filters_applied if filters_applied else None,
        },
    )

    # Log activity
    # Activity logging imported at module level
    if identity is not None:
        log_tool_activity(identity, "list_creatives", start_time)

    message = f"Found {len(creatives)} creatives"
    if total_count > len(creatives):
        message += f" (page {page} of {total_pages} total)"

    # Calculate offset for pagination
    offset_calc = (page - 1) * limit

    # Import required schema classes
    from src.core.schemas import Pagination as SchemaPagination
    from src.core.schemas import QuerySummary

    return ListCreativesResponse(
        query_summary=QuerySummary(
            total_matching=total_count,
            returned=len(creatives),
            filters_applied=filters_applied,
            sort_applied=sort_applied,
        ),
        pagination=SchemaPagination(
            has_more=has_more,
            total_count=total_count,
        ),
        creatives=creatives,
        format_summary=None,
        status_summary=None,
        errors=unreadable_status_advisories or None,
        context=req.context,
        message=(
            f"Found {len(creatives)} creative{'s' if len(creatives) != 1 else ''}."
            if len(creatives) == total_count
            else f"Showing {len(creatives)} of {total_count} creatives."
        ),
    )
