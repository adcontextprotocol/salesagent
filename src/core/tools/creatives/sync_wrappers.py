"""MCP and A2A wrapper functions for sync_creatives."""

from fastmcp.server.context import Context

from src.core.idempotency_canonical import canonical_request_hash
from src.core.schemas.creative import SyncCreativesRequest
from src.core.tool_context import ToolContext
from src.core.transport_helpers import NOT_PROVIDED, IdentityOrNotProvided, resolve_identity_if_not_provided

from ._sync import _sync_creatives_impl


def sync_creatives_raw(
    req: SyncCreativesRequest,
    ctx: Context | ToolContext | None = None,
    identity: IdentityOrNotProvided = NOT_PROVIDED,
):
    """Sync creative assets to the centralized creative library (raw function for A2A server use).

    Delegates to the shared implementation.

    Args:
        req: The built SyncCreativesRequest — every protocol field travels on it. The
            per-field parameters this docstring used to list (creatives, assignments,
            creative_ids, delete_missing, dry_run, validation_mode,
            push_notification_config, context) are fields of that request.
        ctx: FastMCP context (automatically provided)
        identity: ResolvedIdentity (transport-agnostic, preferred over ctx)

    Returns:
        SyncCreativesResponse with synced creatives and assignments
    """
    identity = resolve_identity_if_not_provided(identity, ctx)

    # Account resolution at the boundary, read OFF the request rather than from a separate
    # parameter beside it -- account is a SyncCreativesRequest field, so one carrier.
    from src.core.transport_helpers import enrich_identity_with_account

    identity = enrich_identity_with_account(identity, req.account)

    return _sync_creatives_impl(
        req=req,
        identity=identity,
        # Canonicalised HERE, from the built request, because _impl must not call
        # model_dump (the no-model-dump-in-impl guard) and must not rebuild the request.
        # It is the ONE argument that travels beside the request rather than on it: the
        # hash is a property of the TRANSMISSION (the RFC 8785 canonical form of what
        # arrived), not a field the buyer sends, and nothing in the pinned
        # creative/sync-creatives-request.json declares it.
        request_hash=canonical_request_hash(req) if req.idempotency_key and not req.dry_run else None,
    )
