"""
Shared Media Buy Helpers - Single Source of Truth

This module contains shared helper functions for media buy operations used across
all adapters (GAM, Mock, etc.) to eliminate code duplication.

Key functions:
- build_order_name: Single naming logic with template support
- build_package_responses: Single package response builder
- calculate_total_budget: Single budget calculation
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import AdapterConfig, Tenant
from src.core.schemas import CreateMediaBuyRequest, MediaPackage, extract_budget_amount
from src.core.utils.naming import apply_naming_template, build_order_name_context

logger = logging.getLogger(__name__)


def build_order_name(
    request: CreateMediaBuyRequest,
    packages: list[MediaPackage],
    start_time: datetime,
    end_time: datetime,
    tenant_id: str | None = None,
    adapter_type: str = "gam",
) -> str:
    """Build order name using naming template.

    Single source of truth for order naming logic across all adapters.

    Args:
        request: Create media buy request
        packages: List of packages
        start_time: Campaign start time
        end_time: Campaign end time
        tenant_id: Tenant identifier (optional, for template lookup)
        adapter_type: Adapter type for template selection ("gam", "mock", etc.)

    Returns:
        Generated order name using template or fallback default
    """
    order_name_template = "{campaign_name|brand_name} - {date_range}"  # Default
    tenant_gemini_key = None

    if tenant_id:
        try:
            with get_db_session() as db_session:
                # Try adapter-specific template first
                stmt = select(AdapterConfig).filter_by(tenant_id=tenant_id)
                adapter_config = db_session.scalars(stmt).first()
                if adapter_config:
                    if adapter_type == "gam" and adapter_config.gam_order_name_template:
                        order_name_template = adapter_config.gam_order_name_template
                    # Add more adapter types as needed

                # Get tenant's Gemini key for auto_name generation
                tenant_stmt = select(Tenant).filter_by(tenant_id=tenant_id)
                tenant = db_session.scalars(tenant_stmt).first()
                if tenant:
                    tenant_gemini_key = tenant.gemini_api_key
                    # Also check tenant-level order_name_template (for Mock adapter)
                    if hasattr(tenant, "order_name_template") and tenant.order_name_template:
                        order_name_template = tenant.order_name_template
        except Exception as e:
            # Database not available (e.g., in unit tests) - use default template
            logger.debug(f"Could not load naming template from database: {e}")

    # Build context and apply template
    context = build_order_name_context(request, packages, start_time, end_time, tenant_gemini_key)
    order_name = apply_naming_template(order_name_template, context)

    return order_name


def build_package_responses(
    packages: list[MediaPackage],
    request: CreateMediaBuyRequest,
    line_item_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build package response dictionaries with ALL required fields.

    Single source of truth for package response building across all adapters.
    Ensures MediaPackage database records can be created properly.

    Args:
        packages: Simplified package models
        request: Original request with buyer_ref and budget
        line_item_ids: Optional platform line item IDs (for creative association)

    Returns:
        List of package dictionaries ready for CreateMediaBuyResponse
    """
    package_responses = []

    for idx, package in enumerate(packages):
        # Get matching request package for buyer_ref and other fields
        matching_req_package = None
        if request.packages and idx < len(request.packages):
            matching_req_package = request.packages[idx]

        # Build base package dict with core fields
        package_dict = {
            "package_id": package.package_id,
            "product_id": package.product_id,
            "name": package.name,
        }

        # Add delivery metrics if available
        if hasattr(package, "delivery_type") and package.delivery_type:
            package_dict["delivery_type"] = package.delivery_type
        if hasattr(package, "cpm") and package.cpm:
            package_dict["cpm"] = package.cpm
        if hasattr(package, "impressions") and package.impressions:
            package_dict["impressions"] = package.impressions

        # Add buyer_ref from request package if available
        if matching_req_package and hasattr(matching_req_package, "buyer_ref"):
            package_dict["buyer_ref"] = matching_req_package.buyer_ref

        # Add budget from request package if available (serialize to dict for JSON storage)
        if matching_req_package and hasattr(matching_req_package, "budget") and matching_req_package.budget:
            # Handle both ADCP 2.5.0 (float) and 2.3 (Budget object)
            if isinstance(matching_req_package.budget, (int, float)):
                package_dict["budget"] = {"total": float(matching_req_package.budget), "currency": "USD"}
            elif hasattr(matching_req_package.budget, "model_dump"):
                package_dict["budget"] = matching_req_package.budget.model_dump()
            else:
                # Fallback for dict or other types
                package_dict["budget"] = (
                    dict(matching_req_package.budget)
                    if isinstance(matching_req_package.budget, dict)
                    else {"total": float(matching_req_package.budget), "currency": "USD"}
                )

        # Add targeting_overlay from package if available
        if hasattr(package, "targeting_overlay") and package.targeting_overlay:
            package_dict["targeting_overlay"] = package.targeting_overlay

        # Add creative_ids from package if available (from uploaded inline creatives)
        if hasattr(package, "creative_ids") and package.creative_ids:
            package_dict["creative_ids"] = package.creative_ids

        # Add platform line item ID if provided (for creative association)
        if line_item_ids and idx < len(line_item_ids):
            package_dict["platform_line_item_id"] = str(line_item_ids[idx])

        package_responses.append(package_dict)

    return package_responses


def calculate_total_budget(
    request: CreateMediaBuyRequest,
    packages: list[MediaPackage],
    package_pricing_info: dict[str, dict] | None = None,
) -> float:
    """Calculate total budget from packages.

    Single source of truth for budget calculation across all adapters.
    Supports both AdCP v2.2.0 package-level budgets and legacy CPM * impressions.

    Args:
        request: Create media buy request (may have top-level budget in future)
        packages: List of packages with budget/cpm/impressions
        package_pricing_info: Optional pricing info from pricing options

    Returns:
        Total budget amount as float
    """
    # Use request-level method if available (AdCP v2.2.0+)
    if hasattr(request, "get_total_budget"):
        return request.get_total_budget()

    # Fallback: calculate from packages
    total_budget = 0.0

    for package in packages:
        # First try to get budget from package (AdCP v2.2.0)
        if hasattr(package, "budget") and package.budget:
            budget_amount, _ = extract_budget_amount(package.budget)
            total_budget += budget_amount
        elif hasattr(package, "delivery_type") and package.delivery_type == "guaranteed":
            # Fallback: calculate from CPM * impressions (legacy)
            # Use pricing_info if available (pricing_option_id flow), else fallback to package.cpm
            pricing_info = package_pricing_info.get(package.package_id) if package_pricing_info else None
            if pricing_info:
                # Use rate from pricing option (fixed) or bid_price (auction)
                rate = pricing_info["rate"] if pricing_info["is_fixed"] else pricing_info.get("bid_price", package.cpm)
            else:
                # Fallback to legacy package.cpm
                rate = getattr(package, "cpm", 0)

            impressions = getattr(package, "impressions", 0)
            total_budget += (rate * impressions / 1000)

    return total_budget
