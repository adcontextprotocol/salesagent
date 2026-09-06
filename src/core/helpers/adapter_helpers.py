"""Adapter instance creation and configuration helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn

from pydantic import ValidationError

if TYPE_CHECKING:
    from adcp.exceptions import ADCPError

    from src.adapters import AdServerAdapter
    from src.adapters.base import TargetingCapabilities
    from src.core.database.models import Tenant as DBTenant
    from src.core.tenant_context import TenantContext
    from src.core.testing_hooks import TestingContext

    #: Same shape as ResolvedIdentity.tenant (src/core/resolved_identity.py).
    IdentityTenant = TenantContext | dict[str, object]
    #: IdentityTenant plus the raw ORM row some call sites pass directly (e.g.
    #: media_buy_create.py's session.scalars(...).first()) instead of routing
    #: through identity.tenant.
    TenantLike = DBTenant | IdentityTenant | None


from src.adapters.google_ad_manager import GoogleAdManager
from src.adapters.kevel import Kevel
from src.adapters.mock_ad_server import MockAdServer as MockAdServerAdapter
from src.adapters.triton_digital import TritonDigital
from src.core.schemas import Principal
from src.core.testing_hooks import MockTestBehavior

logger = logging.getLogger(__name__)


# ``build_agent_config`` and its ``_HasAgentFields`` Protocol used to sit here.
# salesagent-4n88 (#1802) deleted them: both registries that built an adcp
# ``AgentConfig`` for ``ADCPMultiAgentClient`` now dial the guarded MCP seam
# (``src.core.utils.operator_mcp.call_operator_mcp_tool``), so nothing
# constructs one any more. Keeping a second, unreachable way to build agent
# auth would be the duplication the CLAUDE.md DRY invariant forbids.
# ``raise_mapped_adcp_error`` below is NOT part of that removal: the registries
# still catch the SDK's own ``ADCPError`` and delegate the mapping here.


def raise_mapped_adcp_error(exc: ADCPError, *, agent_label: str, logger: logging.Logger) -> NoReturn:
    """Translate an adcp SDK exception into the internal typed AdCPSalesAgentError taxonomy.

    Shared by CreativeAgentRegistry and SignalsAgentRegistry so the SDK-to-internal
    error mapping — and its recovery classification — has a single home: an
    authentication failure surfaces as terminal (the caller must fix credentials),
    a timeout or connection failure surfaces as a transient service outage (a retry
    may succeed), and any other AdCP error maps to a generic adapter failure.

    Always raises; the ``NoReturn`` annotation lets callers delegate from a single
    ``except ADCPError`` branch without a trailing ``raise``.

    ``exc.message`` is THIRD-PARTY free text and never reaches the wire: the SDK
    builds e.g. ``ADCPConnectionError`` as ``f"Failed to connect: {last_error}"``
    over a raw httpx error (adcp/protocols/mcp.py, a2a.py), which routinely
    carries host:port and resolver detail. AdCP 3.1.1 transport-errors.mdx
    § Security Considerations forbids that on a buyer-facing message, so the
    buyer gets the stable first-party sentence from the mapping table below and
    the raw text goes to ``internal_detail`` (logged, not serialized).
    """
    from adcp.exceptions import ADCPAuthenticationError, ADCPConnectionError, ADCPTimeoutError

    from src.core.exceptions import (
        AdCPAdapterError,
        AdCPAuthenticationError,
        AdCPSalesAgentError,
        AdCPServiceUnavailableError,
    )

    # (SDK exception, internal class, buyer-facing sentence + log label). One
    # table + one raise, rather than four copies of "log raw / raise typed"
    # differing only in the label and the class (CLAUDE.md DRY invariant).
    mapping: tuple[tuple[type[Exception], type[AdCPSalesAgentError], str], ...] = (  # (sdk, internal, mode label)
        (ADCPAuthenticationError, AdCPAuthenticationError, "Authentication failed"),
        (ADCPTimeoutError, AdCPServiceUnavailableError, "Request timed out"),
        (ADCPConnectionError, AdCPServiceUnavailableError, "Connection failed"),
    )
    error_class: type[AdCPSalesAgentError] = AdCPAdapterError
    # ONE CODE, MANY SENTENCES — resolved as an ACCEPTED MERGE, recorded not defaulted.
    # ADCPTimeoutError and ADCPConnectionError both map to AdCPServiceUnavailableError,
    # and they used to carry different buyer sentences ("Request timed out" /
    # "Connection failed"). Both are SERVICE_UNAVAILABLE/transient on the wire and the
    # buyer's action is identical (retry), so the distinction is diagnostic rather than
    # buyer-actionable: the two now share the code's table sentence, and the mode is
    # preserved under ``details`` so nothing is lost. A mode that ever needs its OWN
    # buyer sentence needs its own AppErrorCode, not a message argument.
    failure_mode = "AdCP agent request failed"
    for sdk_class, internal_class, mode_label in mapping:
        if isinstance(exc, sdk_class):
            error_class, failure_mode = internal_class, mode_label
            break

    logger.error("%s for %s: %s", failure_mode, agent_label, exc.message)
    # The mode is an operator label, i.e. prose — it belongs in the log and on
    # internal_detail, not in details. Four lines above, this file's own comment says a
    # mode needing its own buyer sentence needs its own AppErrorCode, "not a message
    # argument"; parking the sentence in details would be the same thing by another route.
    raise error_class(
        details={"agent": agent_label},
        internal_detail=f"{failure_mode}: {exc.message}",
    ) from exc


def _resolve_tenant_id_and_fallback_adapter(tenant: DBTenant | IdentityTenant) -> tuple[str, str]:
    """Extract tenant_id and the tenant.ad_server fallback adapter type.

    Supports both the ORM model (Tenant) and the dict shape (identity.tenant).
    This is the pre-AdapterConfig fallback only — callers needing the
    authoritative adapter type must go through ``resolve_tenant_adapter_type``.
    """
    if isinstance(tenant, dict):
        tenant_id = tenant["tenant_id"]
        ad_server = tenant.get("ad_server")
        return (
            tenant_id if isinstance(tenant_id, str) else str(tenant_id),
            ad_server if isinstance(ad_server, str) and ad_server else "mock",
        )
    # ORM model or TenantContext — use attribute access
    return tenant.tenant_id, tenant.ad_server or "mock"


def _resolved_tenant(tenant: TenantLike) -> DBTenant | IdentityTenant:
    """Resolve an Optional tenant param to a concrete tenant, falling back to
    the ContextVar for callers that haven't threaded identity.tenant through yet.

    Single home for the ``tenant is None`` fallback (previously duplicated --
    and, in three of the five callers below, MISSING entirely, meaning
    ``_resolve_tenant_id_and_fallback_adapter(None)`` would crash on a bare
    ``AttributeError`` the moment ``tenant: Any`` stopped hiding it).
    """
    if tenant is not None:
        return tenant
    from src.core.config_loader import get_current_tenant

    return get_current_tenant()


def resolve_tenant_adapter_type(tenant: TenantLike = None) -> str:
    """Resolve the authoritative ad-server adapter type for a tenant.

    Single source of truth for adapter-TYPE resolution: ``AdapterConfig.adapter_type``
    (via ``AdapterConfigRepository``) wins when a row exists, falling back to
    ``tenant.ad_server``/``tenant["ad_server"]`` otherwise. ``get_adapter()`` and the
    principal-free ``get_adapter_class_for_tenant()`` read path both route through
    this function so the two can never diverge (salesagent-dn2s: divergent
    tenant-adapter-type resolution copies would only half-close INV-4).

    Args:
        tenant: Tenant context (dict or ORM model). Falls back to ContextVar if not provided.
    """
    logger = logging.getLogger(__name__)

    resolved_tenant = _resolved_tenant(tenant)
    tenant_id, selected_adapter = _resolve_tenant_id_and_fallback_adapter(resolved_tenant)
    logger.info(f"[ADAPTER_SELECT] Initial selected_adapter from tenant.ad_server: {selected_adapter}")

    from src.core.database.repositories.adapter_config import read_adapter_config

    config_row = read_adapter_config(tenant_id)
    if config_row and config_row.adapter_type:
        selected_adapter = config_row.adapter_type
        logger.info(f"[ADAPTER_SELECT] Using AdapterConfig.adapter_type: {selected_adapter}")

    return selected_adapter or "mock"


def _read_mock_test_behavior(tenant_id: str, adapter_type: str) -> MockTestBehavior:
    """Read the per-tenant mock-adapter ``test_behavior`` fault-injection config.

    Single seam (salesagent-689e Core Invariant) for reading
    ``AdapterConfig.config_json["test_behavior"]`` outside an ``_impl`` file --
    ``src/core/tools/capabilities.py`` and this module are both scanned by
    ``test_architecture_repository_pattern.py``'s discovery glob, so the
    session lives in ``read_adapter_config`` (the repository layer), never
    here or in a caller (#1721 M2 -- this docstring previously
    described a per-call ``get_db_session()`` here as the sanctioned seam;
    that was itself the D2 loophole, not the fix for it). Gated on
    ``adapter_type == "mock"`` so the fault-injection channel never leaks onto
    real ad-server adapters. Returns an all-defaults ``MockTestBehavior`` when not
    applicable/configured, so every consumer reads the same "nothing configured"
    shape instead of branching on an empty mapping.
    """
    if adapter_type != "mock":
        return MockTestBehavior()

    from src.core.database.repositories.adapter_config import read_adapter_config

    row = read_adapter_config(tenant_id)
    if row and isinstance(row.config_json, dict):
        behavior = row.config_json.get("test_behavior", {})
        if isinstance(behavior, dict):
            # Invalid values are ignored rather than raised: this is a
            # fault-injection channel, and a malformed column must degrade to
            # "not configured" instead of failing a real buyer's request.
            try:
                return MockTestBehavior.model_validate(behavior)
            except ValidationError:
                logger.warning("Ignoring malformed adapter test_behavior for tenant %s", tenant_id)
    return MockTestBehavior()


@dataclass(frozen=True)
class AdapterContext:
    """Who the tenant is and which adapter answers for it — resolved once.

    Every adapter-facing helper needs the same three facts, and each used to
    re-derive them inline. That is not merely repetitive: the steps must agree,
    because ``adapter_type`` selects the class while ``tenant_id`` selects the
    config row, and two helpers resolving differently would read one tenant's
    column while acting as another's adapter.
    """

    tenant: DBTenant | IdentityTenant
    adapter_type: str
    tenant_id: str


def resolve_adapter_context(tenant: TenantLike = None) -> AdapterContext:
    """The ONE resolve every adapter helper starts from (#1721 Lane B, step 4.1)."""
    resolved_tenant = _resolved_tenant(tenant)
    adapter_type = resolve_tenant_adapter_type(resolved_tenant)
    tenant_id, _ = _resolve_tenant_id_and_fallback_adapter(resolved_tenant)
    return AdapterContext(tenant=resolved_tenant, adapter_type=adapter_type, tenant_id=tenant_id)


def _test_behavior_for(tenant: TenantLike) -> MockTestBehavior:
    """Resolve *tenant* -> its adapter type -> its fault-injection config."""
    ctx = resolve_adapter_context(tenant)
    return _read_mock_test_behavior(ctx.tenant_id, ctx.adapter_type)


def get_adapter_class_for_tenant(tenant: TenantLike = None) -> type[AdServerAdapter]:
    """Resolve the ad-server adapter CLASS for a tenant, without a Principal.

    For read-only capability/discovery paths (e.g. get_adcp_capabilities) that
    only need adapter-level CLASS attributes (default_channels,
    get_targeting_capabilities) and must work identically for anonymous and
    authenticated callers per AdCP INV-4 (capabilities describe the seller,
    not the caller). Deliberately bypasses ``Adapter.__init__`` — Kevel and
    TritonDigital unconditionally require a principal-bound config in
    ``__init__`` and would crash for a synthetic/tenant-only Principal.

    Raises when the tenant's mock-adapter ``test_behavior["unavailable"]``
    fault-injection flag is set (salesagent-689e) — deliberately pinned here,
    not in ``resolve_tenant_adapter_type()``, because that function also backs
    ``get_adapter()``/the real media-buy path for the same tenant; raising
    there would leak the fault onto ``create_media_buy`` during an e2e run.

    Args:
        tenant: Tenant context (dict or ORM model). Falls back to ContextVar if not provided.
    """
    from src.adapters import get_adapter_class

    ctx = resolve_adapter_context(tenant)
    adapter_type = ctx.adapter_type

    test_behavior = _read_mock_test_behavior(ctx.tenant_id, adapter_type)
    if test_behavior.unavailable:
        from src.core.exceptions import AdCPAdapterError

        raise AdCPAdapterError()

    return get_adapter_class(adapter_type)


def get_targeting_capabilities_override(tenant: TenantLike = None) -> TargetingCapabilities | None:
    """Return the per-tenant mock-adapter targeting-capability override, if any.

    Reads the same ``test_behavior`` seam as ``get_adapter_class_for_tenant``
    (salesagent-689e). Callers in ``_impl`` files (e.g. ``capabilities.py``)
    must use this instead of opening their own DB session — it stays legal
    under ``test_architecture_repository_pattern.py``'s empty
    ``IMPL_SESSION_ALLOWLIST`` because the session lives in this file, not theirs.
    """
    override = _test_behavior_for(tenant).targeting_capabilities
    if not override:
        return None

    from src.adapters.base import TargetingCapabilities as _TargetingCapabilities

    return _TargetingCapabilities(**override)


def get_adapter_channels_override(tenant: TenantLike = None) -> list[str] | None:
    """Return the per-tenant mock-adapter channel override, if any.

    Same ``test_behavior`` seam as :func:`get_targeting_capabilities_override`,
    and it exists for the same reason: which channels a seller offers is a
    per-tenant fact, but the adapter exposes it as a CLASS attribute
    (``AdServerAdapter.default_channels``), so without an override the answer is
    fixed per adapter type and cannot be configured for a tenant at all.

    That gap is only visible over a real transport. In-process a test can patch
    the adapter class; over HTTP the server resolves its own, so a scenario
    configuring channels silently graded the adapter's defaults instead (#1871).

    Returns None when nothing is configured, which means "use the class default".
    """
    return _test_behavior_for(tenant).default_channels or None


#: Resolved adapter type -> the AdapterConfig column backing its manual-approval
#: requirement. Triton has no such column (not modeled), so it is absent here.
_MANUAL_APPROVAL_COLUMNS: dict[str, str] = {
    "google_ad_manager": "gam_manual_approval_required",
    "kevel": "kevel_manual_approval_required",
    "mock": "mock_manual_approval_required",
}


def resolve_manual_approval_signal(tenant: IdentityTenant | None = None) -> bool:
    """Whether this tenant's configuration genuinely requires manual approval
    on new media buys -- the same signal ``_create_media_buy_impl`` enforces
    (media_buy_create.py), read tenant/DB-side so it works without a live
    adapter instance (capabilities.py only holds the adapter CLASS, per INV-4 /
    salesagent-dn2s -- ``manual_approval_required`` is an instance attribute
    set in ``Adapter.__init__`` and does not exist on the class).

    ``tenant.human_review_required`` is NOT NULL DEFAULT TRUE at the schema
    level (a real, always-present tenant setting, not a Python-level default
    papering over a missing key) -- reading it directly is an honest claim
    about real enforced behavior, not an invented default (salesagent-rldj/
    salesagent-y9ld Core Invariant). Falls back to the resolved adapter type's
    own manual-approval DB column; that column is nullable and this reader
    applies NO default when it is unset -- deliberately NOT the same
    True-when-null policy ``get_adapter()``'s live adapter_config assembly
    uses for enforcement, since that default is exactly the false-conformance
    risk this reader must avoid (salesagent-becl.72 refine).
    """
    if tenant and tenant.get("human_review_required"):
        return True

    ctx = resolve_adapter_context(tenant)
    column = _MANUAL_APPROVAL_COLUMNS.get(ctx.adapter_type)
    if not column:
        return False

    tenant_id = ctx.tenant_id

    from src.core.database.repositories.adapter_config import read_adapter_config

    row = read_adapter_config(tenant_id)
    return bool(row and getattr(row, column, None) is True)


def get_adapter(
    principal: Principal,
    dry_run: bool = False,
    testing_context: TestingContext | None = None,
    tenant: TenantLike = None,
) -> MockAdServerAdapter | GoogleAdManager | Kevel | TritonDigital:
    """Get the appropriate adapter instance for the selected adapter type.

    Args:
        principal: The authenticated principal
        dry_run: Whether to run in dry-run mode
        testing_context: Optional test context for simulations
        tenant: Tenant context (from identity.tenant). Falls back to ContextVar if not provided.
    """
    ctx = resolve_adapter_context(tenant)
    selected_adapter = ctx.adapter_type
    tenant_id = ctx.tenant_id

    # Get adapter config via repository
    from src.core.database.repositories.adapter_config import AdapterConfigRepository, read_adapter_config

    targeting_config: dict[str, object] | None = None
    naming_templates: tuple[str | None, str | None] | None = None

    config_row = read_adapter_config(tenant_id)

    adapter_config: dict[str, object] = {"enabled": True}
    if config_row:
        adapter_type = config_row.adapter_type
        logger.info(f"[ADAPTER_SELECT] adapter_type from AdapterConfig: {adapter_type}")
        if adapter_type == "mock":
            adapter_config["dry_run"] = config_row.mock_dry_run or False
            # Default to True (require approval) for safety
            adapter_config["manual_approval_required"] = (
                config_row.mock_manual_approval_required
                if config_row.mock_manual_approval_required is not None
                else True
            )
        elif adapter_type == "google_ad_manager":
            adapter_config = AdapterConfigRepository.get_gam_config(config_row)
            targeting_config = AdapterConfigRepository.get_gam_targeting_config(config_row)
            naming_templates = AdapterConfigRepository.get_gam_naming_templates(config_row)

            # Get advertiser_id from principal's platform_mappings (per-principal, not tenant-level)
            # Support both old format (nested under "google_ad_manager") and new format (root "gam_advertiser_id")
            advertiser_id: str | None = None
            if principal.platform_mappings:
                # Try nested format first
                gam_mappings = principal.platform_mappings.get("google_ad_manager", {})
                advertiser_id = gam_mappings.get("advertiser_id")
                logger.info(
                    f"[ADAPTER_CONFIG] principal_id={principal.principal_id}, platform_mappings={principal.platform_mappings}, gam_mappings={gam_mappings}, advertiser_id={advertiser_id}"
                )

                # Fall back to root-level format if nested not found
                if not advertiser_id:
                    advertiser_id = principal.platform_mappings.get("gam_advertiser_id")
                    logger.info(f"[ADAPTER_CONFIG] Fell back to root-level gam_advertiser_id: {advertiser_id}")

                adapter_config["company_id"] = advertiser_id
                logger.info(f"[ADAPTER_CONFIG] Set adapter_config['company_id']={advertiser_id}")
            else:
                adapter_config["company_id"] = None
                logger.info("[ADAPTER_CONFIG] principal.platform_mappings is None/empty, set company_id=None")
        elif adapter_type == "kevel":
            adapter_config["network_id"] = config_row.kevel_network_id or ""
            adapter_config["api_key"] = config_row.kevel_api_key or ""
            # Default to True (require approval) for safety
            adapter_config["manual_approval_required"] = (
                config_row.kevel_manual_approval_required
                if config_row.kevel_manual_approval_required is not None
                else True
            )
        elif adapter_type == "triton":
            adapter_config["station_id"] = config_row.triton_station_id or ""
            adapter_config["api_key"] = config_row.triton_api_key or ""

    if not selected_adapter:
        # Default to mock if no adapter specified
        selected_adapter = "mock"
        if not adapter_config:
            adapter_config = {"enabled": True}

    # Create the appropriate adapter instance with tenant_id and testing context
    logger.info(f"[ADAPTER_SELECT] FINAL selected_adapter: {selected_adapter}")
    if selected_adapter == "mock":
        logger.info("[ADAPTER_SELECT] Instantiating MockAdServerAdapter")
        return MockAdServerAdapter(
            adapter_config, principal, dry_run, tenant_id=tenant_id, strategy_context=testing_context
        )
    elif selected_adapter == "google_ad_manager":
        # network_code is required for GoogleAdManager
        network_code = adapter_config.get("network_code")
        if not network_code or not isinstance(network_code, str):
            raise ValueError("network_code is required for GoogleAdManager adapter")

        company_id = adapter_config.get("company_id")
        advertiser_id = company_id if isinstance(company_id, str) else None
        trafficker_id_val = adapter_config.get("trafficker_id")
        trafficker_id = trafficker_id_val if isinstance(trafficker_id_val, str) else None

        logger.info("[ADAPTER_SELECT] Instantiating GoogleAdManager")
        logger.info(
            f"[ADAPTER_SELECT] GAM params: network_code={network_code}, advertiser_id={advertiser_id}, trafficker_id={trafficker_id}, dry_run={dry_run}"
        )
        return GoogleAdManager(
            adapter_config,
            principal,
            network_code=network_code,
            advertiser_id=advertiser_id,
            trafficker_id=trafficker_id,
            dry_run=dry_run,
            tenant_id=tenant_id,
            targeting_config=targeting_config,
            naming_templates=naming_templates,
        )
    elif selected_adapter == "kevel":
        return Kevel(adapter_config, principal, dry_run, tenant_id=tenant_id)
    elif selected_adapter in ["triton", "triton_digital"]:
        return TritonDigital(adapter_config, principal, dry_run, tenant_id=tenant_id)
    else:
        # Default to mock for unsupported adapters
        return MockAdServerAdapter(
            adapter_config, principal, dry_run, tenant_id=tenant_id, strategy_context=testing_context
        )
