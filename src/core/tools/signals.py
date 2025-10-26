"""AdCP tool implementation.

This module contains tool implementations following the MCP/A2A shared
implementation pattern from CLAUDE.md.
"""

import logging
import time
import uuid

from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context

logger = logging.getLogger(__name__)

from src.core.auth import get_principal_from_context, get_principal_object
from src.core.config_loader import get_current_tenant
from src.core.schema_adapters import ActivateSignalResponse, GetSignalsResponse
from src.core.schemas import GetSignalsRequest, Signal, SignalDeployment, SignalPricing
from src.core.testing_hooks import get_testing_context


def _get_principal_id_from_context(context: Context | None) -> str | None:
    """Extract principal ID from the FastMCP context."""
    if not context:
        return None
    principal_id, _ = get_principal_from_context(context, require_valid_token=False)
    return principal_id


async def get_signals(req: GetSignalsRequest, context: Context = None) -> GetSignalsResponse:
    """Optional endpoint for discovering available signals (audiences, contextual, etc.)

    Args:
        req: Request containing query parameters for signal discovery
        context: FastMCP context (automatically provided)

    Returns:
        GetSignalsResponse containing matching signals
    """

    _get_principal_id_from_context(context)

    # Get tenant information
    tenant = get_current_tenant()
    if not tenant:
        raise ToolError("No tenant context available")

    # Mock implementation - in production, this would query from a signal provider
    # or the ad server's available audience segments
    signals = []

    # Sample signals for demonstration using AdCP-compliant structure
    sample_signals = [
        Signal(
            signal_agent_segment_id="auto_intenders_q1_2025",
            name="Auto Intenders Q1 2025",
            description="Users actively researching new vehicles in Q1 2025",
            signal_type="marketplace",
            data_provider="Acme Data Solutions",
            coverage_percentage=85.0,
            deployments=[
                SignalDeployment(
                    platform="google_ad_manager",
                    account="123456",
                    is_live=True,
                    scope="account-specific",
                    decisioning_platform_segment_id="gam_auto_intenders",
                    estimated_activation_duration_minutes=0,
                )
            ],
            pricing=SignalPricing(cpm=3.0, currency="USD"),
        ),
        Signal(
            signal_agent_segment_id="luxury_travel_enthusiasts",
            name="Luxury Travel Enthusiasts",
            description="High-income individuals interested in premium travel experiences",
            signal_type="marketplace",
            data_provider="Premium Audience Co",
            coverage_percentage=75.0,
            deployments=[
                SignalDeployment(
                    platform="google_ad_manager",
                    is_live=True,
                    scope="platform-wide",
                    estimated_activation_duration_minutes=15,
                )
            ],
            pricing=SignalPricing(cpm=5.0, currency="USD"),
        ),
        Signal(
            signal_agent_segment_id="sports_content",
            name="Sports Content Pages",
            description="Target ads on sports-related content",
            signal_type="owned",
            data_provider="Publisher Sports Network",
            coverage_percentage=95.0,
            deployments=[
                SignalDeployment(
                    platform="google_ad_manager",
                    is_live=True,
                    scope="account-specific",
                    decisioning_platform_segment_id="sports_contextual",
                )
            ],
            pricing=SignalPricing(cpm=1.5, currency="USD"),
        ),
        Signal(
            signal_agent_segment_id="finance_content",
            name="Finance & Business Content",
            description="Target ads on finance and business content",
            signal_type="owned",
            data_provider="Financial News Corp",
            coverage_percentage=88.0,
            deployments=[SignalDeployment(platform="google_ad_manager", is_live=True, scope="platform-wide")],
            pricing=SignalPricing(cpm=2.0, currency="USD"),
        ),
        Signal(
            signal_agent_segment_id="urban_millennials",
            name="Urban Millennials",
            description="Millennials living in major metropolitan areas",
            signal_type="marketplace",
            data_provider="Demographics Plus",
            coverage_percentage=78.0,
            deployments=[
                SignalDeployment(
                    platform="google_ad_manager",
                    is_live=True,
                    scope="account-specific",
                    estimated_activation_duration_minutes=30,
                )
            ],
            pricing=SignalPricing(cpm=1.8, currency="USD"),
        ),
        Signal(
            signal_agent_segment_id="pet_owners",
            name="Pet Owners",
            description="Households with dogs or cats",
            signal_type="marketplace",
            data_provider="Lifestyle Data Inc",
            coverage_percentage=92.0,
            deployments=[SignalDeployment(platform="google_ad_manager", is_live=True, scope="platform-wide")],
            pricing=SignalPricing(cpm=1.2, currency="USD"),
        ),
    ]

    # Filter based on request parameters using new AdCP-compliant fields
    for signal in sample_signals:
        # Apply signal_spec filter (natural language description matching)
        if req.signal_spec:
            spec_lower = req.signal_spec.lower()
            if (
                spec_lower not in signal.name.lower()
                and spec_lower not in signal.description.lower()
                and spec_lower not in signal.signal_type.lower()
            ):
                continue

        # Apply filters if provided
        if req.filters:
            # Filter by catalog_types (equivalent to old 'type' field)
            if req.filters.catalog_types and signal.signal_type not in req.filters.catalog_types:
                continue

            # Filter by data_providers
            if req.filters.data_providers and signal.data_provider not in req.filters.data_providers:
                continue

            # Filter by max_cpm (using signal's pricing.cpm)
            if req.filters.max_cpm is not None and signal.pricing and signal.pricing.cpm > req.filters.max_cpm:
                continue

            # Filter by min_coverage_percentage
            if (
                req.filters.min_coverage_percentage is not None
                and signal.coverage_percentage < req.filters.min_coverage_percentage
            ):
                continue

        signals.append(signal)

    # Apply max_results limit (AdCP-compliant field name)
    if req.max_results:
        signals = signals[: req.max_results]

    # Per AdCP PR #113 and official schema, protocol fields (message, context_id)
    # are added by the protocol layer, not the domain response.
    return GetSignalsResponse(signals=signals)


async def activate_signal(
    signal_id: str,
    campaign_id: str = None,
    media_buy_id: str = None,
    context: Context = None,
) -> ActivateSignalResponse:
    """Activate a signal for use in campaigns.

    Args:
        signal_id: Signal ID to activate
        campaign_id: Optional campaign ID to activate signal for
        media_buy_id: Optional media buy ID to activate signal for
        context: FastMCP context (automatically provided)

    Returns:
        ActivateSignalResponse with activation status
    """
    start_time = time.time()

    # Authentication required for signal activation
    principal_id = _get_principal_id_from_context(context)

    # Get tenant information
    tenant = get_current_tenant()
    if not tenant:
        raise ToolError("No tenant context available")

    # Get the Principal object with ad server mappings
    if not principal_id:
        raise ToolError("Authentication required for signal activation")
    principal = get_principal_object(principal_id)

    # Apply testing hooks
    if not context:
        raise ToolError("Context required for signal activation")
    testing_ctx = get_testing_context(context)
    campaign_info = {"endpoint": "activate_signal", "signal_id": signal_id}
    # Note: apply_testing_hooks modifies response data dict, not called here as no response yet

    try:
        # In a real implementation, this would:
        # 1. Validate the signal exists and is available
        # 2. Check if the principal has permission to activate the signal
        # 3. Communicate with the signal provider's API to activate the signal
        # 4. Update the campaign or media buy configuration to include the signal

        # Mock implementation for demonstration
        activation_success = True
        requires_approval = signal_id.startswith("premium_")  # Mock rule: premium signals need approval

        task_id = f"task_{uuid.uuid4().hex[:12]}"

        if requires_approval:
            # Create a human task for approval
            status = "pending"
            errors = [
                {
                    "code": "APPROVAL_REQUIRED",
                    "message": f"Signal {signal_id} requires manual approval before activation",
                }
            ]
        elif activation_success:
            status = "processing"  # Activation in progress
            estimated_activation_duration_minutes = 15.0
            decisioning_platform_segment_id = f"seg_{signal_id}_{uuid.uuid4().hex[:8]}"
        else:
            status = "failed"
            errors = [{"code": "ACTIVATION_FAILED", "message": "Signal provider unavailable"}]

        # Build response with adapter schema fields
        if requires_approval or not activation_success:
            return ActivateSignalResponse(
                task_id=task_id,
                status=status,
                errors=errors,
            )
        else:
            return ActivateSignalResponse(
                task_id=task_id,
                status=status,
                decisioning_platform_segment_id=decisioning_platform_segment_id if activation_success else None,
                estimated_activation_duration_minutes=(
                    estimated_activation_duration_minutes if activation_success else None
                ),
            )

    except Exception as e:
        logger.error(f"Error activating signal {signal_id}: {e}")
        return ActivateSignalResponse(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            status="failed",
            errors=[{"code": "ACTIVATION_ERROR", "message": str(e)}],
        )


async def get_signals_raw(req: GetSignalsRequest, context: Context = None) -> GetSignalsResponse:
    """Optional endpoint for discovering available signals (raw function for A2A server use).

    Delegates to the shared implementation.

    Args:
        req: Request containing query parameters for signal discovery
        context: FastMCP context (automatically provided)

    Returns:
        GetSignalsResponse containing matching signals
    """
    return await get_signals(req, context)
