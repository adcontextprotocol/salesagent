"""Get products tool implementation.

This module contains the get_products tool implementation following the MCP/A2A
shared implementation pattern from CLAUDE.md.
"""

import logging
import os
import time
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from pydantic import ValidationError

# Imports for implementation
from product_catalog_providers.factory import get_product_catalog_provider
from src.core.audit_logger import get_audit_logger
from src.core.auth import get_principal_from_context, get_principal_object
from src.core.config_loader import set_current_tenant
from src.core.schema_adapters import GetProductsResponse
from src.core.schema_helpers import create_get_products_request
from src.core.schemas import Product, TaskStatus
from src.core.schemas_generated._schemas_v1_media_buy_get_products_request_json import (
    GetProductsRequest as GetProductsRequestGenerated,
)
from src.core.testing_hooks import apply_testing_hooks, get_testing_context
from src.core.validation_helpers import format_validation_error, safe_parse_json_field
from src.services.policy_check_service import PolicyCheckService, PolicyStatus

logger = logging.getLogger(__name__)


async def _get_products_impl(req: GetProductsRequestGenerated, context: Context) -> GetProductsResponse:
    """Shared implementation for get_products.

    Contains all business logic for product discovery including policy checks,
    product catalog providers, dynamic pricing, and filtering.

    Args:
        req: GetProductsRequest from generated schemas
        context: FastMCP Context for tenant/principal resolution

    Returns:
        GetProductsResponse containing matching products
    """
    import sys

    print("=" * 80, file=sys.stderr, flush=True)
    print(
        f"🔧 _get_products_impl CALLED: brand_manifest={req.brand_manifest}, brief={req.brief[:50] if req.brief else 'N/A'}",
        file=sys.stderr,
        flush=True,
    )
    print("=" * 80, file=sys.stderr, flush=True)

    from src.core.tool_context import ToolContext

    start_time = time.time()

    # Handle both old Context and new ToolContext
    if isinstance(context, ToolContext):
        # New context management - everything is already extracted
        testing_ctx_raw = context.testing_context
        # Convert dict testing context back to TestingContext object if needed
        if isinstance(testing_ctx_raw, dict):
            from src.core.testing_hooks import TestingContext

            testing_ctx = TestingContext(**testing_ctx_raw)
        else:
            testing_ctx = testing_ctx_raw
        principal_id = context.principal_id
        tenant = {"tenant_id": context.tenant_id}  # Simplified tenant info
    else:
        # Legacy path - extract from FastMCP Context
        testing_ctx = get_testing_context(context)
        # For discovery endpoints, authentication is optional
        # require_valid_token=False means invalid tokens are treated like missing tokens (discovery endpoint behavior)
        logger.info("[GET_PRODUCTS] About to call get_principal_from_context")
        print("🔍 [GET_PRODUCTS DEBUG] About to call get_principal_from_context", flush=True)
        principal_id, tenant = get_principal_from_context(
            context, require_valid_token=False
        )  # Returns (None, tenant) if no/invalid auth
        logger.info(f"[GET_PRODUCTS] principal_id returned: {principal_id}, tenant: {tenant}")
        print(f"🔍 [GET_PRODUCTS DEBUG] principal_id returned: {principal_id}, tenant: {tenant}", flush=True)

        # Set tenant context explicitly in this async context (ContextVar propagation fix)
        if tenant:
            set_current_tenant(tenant)
            logger.info(f"[GET_PRODUCTS] Set tenant context: {tenant['tenant_id']}")
            print(f"🔍 [GET_PRODUCTS DEBUG] Set tenant context: {tenant['tenant_id']}", flush=True)
        elif principal_id:
            # If we have principal but no tenant, something went wrong
            logger.error(f"[GET_PRODUCTS] Principal found but no tenant context: principal_id={principal_id}")
            print("❌ [GET_PRODUCTS DEBUG] Principal found but no tenant context", flush=True)
            raise ToolError(
                f"Authentication succeeded but tenant context missing. This is a bug. principal_id={principal_id}"
            )
        # else: No auth provided, which is OK for discovery endpoints

    # Get the Principal object with ad server mappings
    principal = get_principal_object(principal_id) if principal_id else None
    principal_data = principal.model_dump() if principal else None

    # Extract offering text from brand_manifest
    offering = None
    if req.brand_manifest:
        if isinstance(req.brand_manifest, str):
            # brand_manifest is a URL - use it as-is for now
            # TODO: In future, fetch and parse the URL
            offering = f"Brand at {req.brand_manifest}"
        else:
            # brand_manifest is a BrandManifest object or dict
            # Try to access as object first, then as dict
            if hasattr(req.brand_manifest, "name"):
                offering = req.brand_manifest.name
            elif isinstance(req.brand_manifest, dict):
                offering = req.brand_manifest.get("name", "")

    if not offering:
        raise ToolError("brand_manifest must provide brand information")

    # Skip strict validation in test environments (allow simple test values)

    is_test_mode = (testing_ctx and testing_ctx.test_session_id is not None) or os.getenv("ADCP_TESTING") == "true"

    # Note: brand_manifest validation is handled by Pydantic schema, no need for runtime validation here

    # Check policy compliance first (if enabled)
    advertising_policy = safe_parse_json_field(
        tenant.get("advertising_policy"), field_name="advertising_policy", default={}
    )

    # Only run policy checks if enabled in tenant settings
    policy_check_enabled = advertising_policy.get("enabled", False)  # Default to False for new tenants
    policy_disabled_reason = None

    if not policy_check_enabled:
        # Skip policy checks if disabled
        policy_result = None
        policy_disabled_reason = "disabled_by_tenant"
        logger.info(f"Policy checks disabled for tenant {tenant['tenant_id']}")
    else:
        # Get tenant's Gemini API key for policy checks
        tenant_gemini_key = tenant.get("gemini_api_key")
        if not tenant_gemini_key:
            # No API key - cannot run policy checks
            policy_result = None
            policy_disabled_reason = "no_gemini_api_key"
            logger.warning(f"Policy checks enabled but no Gemini API key configured for tenant {tenant['tenant_id']}")
        else:
            policy_service = PolicyCheckService(gemini_api_key=tenant_gemini_key)

            # Use advertising_policy settings for tenant-specific rules
            tenant_policies = advertising_policy if advertising_policy else {}

            # Convert brand_manifest to dict if it's a BrandManifest object
            brand_manifest_dict = None
            if req.brand_manifest:
                if hasattr(req.brand_manifest, "model_dump"):
                    brand_manifest_dict = req.brand_manifest.model_dump()
                elif isinstance(req.brand_manifest, dict):
                    brand_manifest_dict = req.brand_manifest
                else:
                    brand_manifest_dict = req.brand_manifest  # URL string

            try:
                policy_result = await policy_service.check_brief_compliance(
                    brief=req.brief,
                    promoted_offering=offering,  # Use extracted offering from brand_manifest
                    brand_manifest=brand_manifest_dict,
                    tenant_policies=tenant_policies if tenant_policies else None,
                )

                # Log successful policy check
                audit_logger = get_audit_logger("AdCP", tenant["tenant_id"])
                audit_logger.log_operation(
                    operation="policy_check",
                    principal_name=principal_id or "anonymous",
                    principal_id=principal_id or "anonymous",
                    adapter_id="policy_service",
                    success=policy_result.status != PolicyStatus.BLOCKED,
                    details={
                        "brief": req.brief[:100] + "..." if len(req.brief) > 100 else req.brief,
                        "brand_name": offering[:100] + "..." if offering and len(offering) > 100 else offering,
                        "policy_status": policy_result.status,
                        "reason": policy_result.reason,
                        "restrictions": policy_result.restrictions,
                    },
                )

            except Exception as e:
                # Policy check failed - log error
                logger.error(f"Policy check failed for tenant {tenant['tenant_id']}: {e}")
                audit_logger = get_audit_logger("AdCP", tenant["tenant_id"])
                audit_logger.log_operation(
                    operation="policy_check_failure",
                    principal_name=principal_id or "anonymous",
                    principal_id=principal_id or "anonymous",
                    adapter_id="policy_service",
                    success=False,
                    details={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "brief": req.brief[:100] + "..." if len(req.brief) > 100 else req.brief,
                    },
                )

                # Fail open by default (allow campaigns) with warning in response
                policy_result = None
                policy_disabled_reason = f"service_error: {type(e).__name__}"
                logger.warning(f"Policy check failed, allowing campaign by default: {e}")

    # Handle policy result based on settings
    if policy_result and policy_result.status == PolicyStatus.BLOCKED:
        # Always block if policy says blocked
        logger.warning(f"Brief blocked by policy: {policy_result.reason}")
        # Raise ToolError to properly signal failure to client
        raise ToolError("POLICY_VIOLATION", policy_result.reason)

    # If restricted and manual review is required, create a task
    if (
        policy_result
        and policy_result.status == PolicyStatus.RESTRICTED
        and advertising_policy.get("require_manual_review", False)
    ):
        # Create a manual review task
        from src.core.database.database_session import get_db_session

        with get_db_session() as session:
            task_id = f"policy_review_{tenant['tenant_id']}_{int(datetime.now(UTC).timestamp())}"

            # Log policy violation for audit trail and compliance
            audit_logger = get_audit_logger("AdCP", tenant["tenant_id"])
            audit_logger.log_operation(
                operation="get_products_policy_violation",
                principal_name=principal_id,
                principal_id=principal_id,
                adapter_id="policy_engine",
                success=False,
                details={
                    "brief": req.brief,
                    "brand_name": offering,
                    "policy_status": policy_result.status,
                    "restrictions": policy_result.restrictions,
                    "reason": policy_result.reason,
                },
            )

        # Raise error for policy violations - explicit failure, not silent return
        raise ToolError(
            "POLICY_VIOLATION",
            f"Request violates content policy: {policy_result.reason}. Restrictions: {', '.join(policy_result.restrictions)}",
        )

    # Determine product catalog configuration based on tenant's signals discovery settings
    catalog_config = {"provider": "database", "config": {}}  # Default to database provider

    # Check if signals discovery is configured for this tenant
    if hasattr(tenant, "signals_agent_config") and tenant.get("signals_agent_config"):
        signals_config = tenant["signals_agent_config"]

        # Parse signals config if it's a string (SQLite) vs dict (PostgreSQL JSONB)
        if isinstance(signals_config, str):
            import json

            try:
                signals_config = json.loads(signals_config)
            except json.JSONDecodeError:
                logger.error(f"Invalid signals_agent_config JSON for tenant {tenant['tenant_id']}")
                signals_config = {}

        # If signals discovery is enabled, use hybrid provider
        if isinstance(signals_config, dict) and signals_config.get("enabled", False):
            logger.info(f"Using hybrid provider with signals discovery for tenant {tenant['tenant_id']}")
            catalog_config = {
                "provider": "hybrid",
                "config": {
                    "database": {},  # Use database provider defaults
                    "signals_discovery": signals_config,
                    "ranking_strategy": "signals_first",  # Prioritize signals-enhanced products
                    "max_products": 20,
                    "deduplicate": True,
                },
            }

    # Get the product catalog provider for this tenant
    provider = await get_product_catalog_provider(
        tenant["tenant_id"],
        catalog_config,
    )

    # Query products using the brief, including context for signals forwarding
    context_data = {
        "brand_name": offering,
        "tenant_id": tenant["tenant_id"],
        "principal_id": principal_id,
    }

    logger.info(f"[GET_PRODUCTS] Calling provider.get_products for tenant_id={tenant['tenant_id']}")
    print(f"🔍 [GET_PRODUCTS DEBUG] Calling provider.get_products for tenant_id={tenant['tenant_id']}", flush=True)
    products = await provider.get_products(
        brief=req.brief,
        tenant_id=tenant["tenant_id"],
        principal_id=principal_id,
        principal_data=principal_data,
        context=context_data,
    )
    logger.info(f"[GET_PRODUCTS] Got {len(products)} products from provider")
    print(f"🔍 [GET_PRODUCTS DEBUG] Got {len(products)} products from provider", flush=True)

    # Enrich products with dynamic pricing (AdCP PR #79)
    # Calculate floor_cpm, recommended_cpm, estimated_exposures from cached metrics
    try:
        from src.core.database.database_session import get_db_session
        from src.services.dynamic_pricing_service import DynamicPricingService

        # Extract country from request if available (future enhancement: parse from targeting)
        country_code = None  # TODO: Extract from targeting if provided

        with get_db_session() as pricing_session:
            pricing_service = DynamicPricingService(pricing_session)
            products = pricing_service.enrich_products_with_pricing(
                products,
                tenant_id=tenant["tenant_id"],
                country_code=country_code,
                min_exposures=getattr(req, "min_exposures", None),
            )
    except Exception as e:
        logger.warning(f"Failed to enrich products with dynamic pricing: {e}. Using defaults.")

    # Apply AdCP filters if provided
    if req.filters:
        filtered_products = []
        for product in products:
            # Filter by delivery_type
            if req.filters.delivery_type and product.delivery_type != req.filters.delivery_type:
                continue

            # Filter by is_fixed_price (check pricing_options)
            if req.filters.is_fixed_price is not None:
                # Check if product has any pricing option matching the fixed/auction filter
                has_matching_pricing = any(po.is_fixed == req.filters.is_fixed_price for po in product.pricing_options)
                if not has_matching_pricing:
                    continue

            # Filter by format_types
            if req.filters.format_types:
                # Product.formats is list[str] (format IDs), need to look up types from FORMAT_REGISTRY
                from src.core.schemas import get_format_by_id

                product_format_types = set()
                for format_id in product.formats:
                    if isinstance(format_id, str):
                        format_obj = get_format_by_id(format_id)
                        if format_obj:
                            product_format_types.add(format_obj.type)
                    elif hasattr(format_id, "type"):
                        # Already a Format object
                        product_format_types.add(format_id.type)

                if not any(fmt_type in product_format_types for fmt_type in req.filters.format_types):
                    continue

            # Filter by format_ids
            if req.filters.format_ids:
                # Product.formats is list[str] or list[dict] (format IDs)
                product_format_ids = set()
                for format_id in product.formats:
                    if isinstance(format_id, str):
                        product_format_ids.add(format_id)
                    elif isinstance(format_id, dict):
                        # Dict with 'id' key (from database)
                        product_format_ids.add(format_id.get("id"))
                    elif hasattr(format_id, "id"):
                        # FormatId object (has .id attribute, not .format_id)
                        product_format_ids.add(format_id.id)

                # req.filters.format_ids contains FormatId objects, extract .id from them
                request_format_ids = set()
                for fmt_id in req.filters.format_ids:
                    if isinstance(fmt_id, str):
                        request_format_ids.add(fmt_id)
                    elif hasattr(fmt_id, "id"):
                        # FormatId object
                        request_format_ids.add(fmt_id.id)
                    elif isinstance(fmt_id, dict):
                        request_format_ids.add(fmt_id.get("id"))

                if not any(fmt_id in product_format_ids for fmt_id in request_format_ids):
                    continue

            # Filter by standard_formats_only
            if req.filters.standard_formats_only:
                # Check if all formats are IAB standard formats
                # IAB standard formats typically follow patterns like "display_", "video_", "audio_", "native_"
                has_only_standard = True
                for format_id in product.formats:
                    format_id_str = None
                    if isinstance(format_id, str):
                        format_id_str = format_id
                    elif isinstance(format_id, dict):
                        format_id_str = format_id.get("id")
                    elif hasattr(format_id, "id"):
                        # FormatId object (has .id attribute, not .format_id)
                        format_id_str = format_id.id

                    if format_id_str and not format_id_str.startswith(("display_", "video_", "audio_", "native_")):
                        has_only_standard = False
                        break

                if not has_only_standard:
                    continue

            # Product passed all filters
            filtered_products.append(product)

        products = filtered_products
        logger.info(f"Applied filters: {req.filters.model_dump(exclude_none=True)}. {len(products)} products remain.")

    # Filter products based on policy compliance (if policy checks are enabled)
    eligible_products = []
    if policy_result and policy_check_enabled:
        # Policy checks are enabled - filter products based on policy compliance
        for product in products:
            is_eligible, reason = policy_service.check_product_eligibility(policy_result, product.model_dump())

            if is_eligible:
                # Product passed policy checks - add to eligible products
                # Note: policy_compliance field removed in AdCP v2.4
                eligible_products.append(product)
            else:
                logger.info(f"Product {product.product_id} excluded: {reason}")
    else:
        # Policy checks disabled - all products are eligible
        eligible_products = products

    # Apply min_exposures filtering (AdCP PR #79)
    min_exposures = getattr(req, "min_exposures", None)
    if min_exposures is not None:
        filtered_products = []
        for product in eligible_products:
            # For guaranteed products, check estimated_exposures
            if product.delivery_type == "guaranteed":
                if product.estimated_exposures is not None and product.estimated_exposures >= min_exposures:
                    filtered_products.append(product)
                else:
                    logger.info(
                        f"Product {product.product_id} excluded: estimated_exposures "
                        f"({product.estimated_exposures}) < min_exposures ({min_exposures})"
                    )
            else:
                # For non-guaranteed, include if recommended_cpm is set (indicates it can meet min_exposures)
                # or if no recommended_cpm is set (product doesn't provide exposure estimates)
                if product.recommended_cpm is not None:
                    filtered_products.append(product)
                else:
                    # Include non-guaranteed products without recommended_cpm (can't filter by exposure estimates)
                    filtered_products.append(product)
        eligible_products = filtered_products

    # Apply testing hooks to response
    response_data = {"products": [p.model_dump_internal() for p in eligible_products]}
    response_data = apply_testing_hooks(response_data, testing_ctx, "get_products")

    # Reconstruct products from modified data
    modified_products = [Product(**p) for p in response_data["products"]]

    # Annotate pricing options with adapter support (AdCP PR #88)
    if principal and modified_products:
        try:
            from src.adapters import get_adapter

            adapter = get_adapter(principal, dry_run=True)
            supported_models = adapter.get_supported_pricing_models()

            for product in modified_products:
                if product.pricing_options:
                    # Annotate each pricing option with "supported" flag
                    for option in product.pricing_options:
                        pricing_model = (
                            option.pricing_model.value
                            if hasattr(option.pricing_model, "value")
                            else option.pricing_model
                        )
                        # Add supported annotation (will be included in response)
                        option.supported = pricing_model in supported_models
                        if not option.supported:
                            option.unsupported_reason = (
                                f"Current adapter does not support {pricing_model.upper()} pricing"
                            )
        except Exception as e:
            logger.warning(f"Failed to annotate pricing options with adapter support: {e}")

    # Filter pricing data for anonymous users
    if principal_id is None:  # Anonymous user
        # Remove pricing data from products for anonymous users
        # Set to empty list to hide pricing (will be excluded during serialization)
        for product in modified_products:
            product.pricing_options = []

    # Set status based on operation result
    status = TaskStatus.from_operation_state(
        operation_type="discovery", has_errors=False, requires_approval=False, requires_auth=principal_id is None
    )

    # Response __str__() will generate appropriate message based on content
    return GetProductsResponse(products=modified_products, status=status)


async def get_products(
    brand_manifest: Any | None = None,  # BrandManifest | str | None - validated by Pydantic
    brief: str = "",
    filters: dict | None = None,
    context: Context = None,
) -> GetProductsResponse:
    """Get available products matching the brief.

    MCP tool wrapper that delegates to the shared implementation.

    Args:
        brand_manifest: Brand information manifest (inline object or URL string)
        brief: Brief description of the advertising campaign or requirements (optional)
        filters: Structured filters for product discovery (optional)
        context: FastMCP context (automatically provided)

    Returns:
        GetProductsResponse containing matching products

    Note:
        promoted_offering is deprecated - use brand_manifest instead.
        If you need backward compatibility, use the A2A interface which still supports it.
    """
    import sys

    print("=" * 80, file=sys.stderr, flush=True)
    print(
        f"🚀 MCP get_products CALLED: brand_manifest={brand_manifest}, brief={brief[:50] if brief else 'N/A'}",
        file=sys.stderr,
        flush=True,
    )
    print("=" * 80, file=sys.stderr, flush=True)

    # Build request object for shared implementation using helper
    try:
        req = create_get_products_request(
            promoted_offering=None,  # Not exposed in MCP tool (use brand_manifest)
            brief=brief,
            brand_manifest=brand_manifest,
            filters=filters,
        )
    except ValidationError as e:
        raise ToolError(format_validation_error(e, context="get_products request")) from e
    except ValueError as e:
        # Convert ValueError from helper to ToolError with clear message
        raise ToolError(f"Invalid get_products request: {e}") from e

    # Call shared implementation
    # Note: GetProductsRequest is now a flat class (not RootModel), so pass req directly
    return await _get_products_impl(req, context)


async def get_products_raw(
    brief: str,
    promoted_offering: str | None = None,
    brand_manifest: Any | None = None,  # BrandManifest | str | None - validated by Pydantic
    adcp_version: str = "1.0.0",
    min_exposures: int | None = None,
    filters: dict | None = None,
    strategy_id: str | None = None,
    context: Context = None,
) -> GetProductsResponse:
    """Get available products matching the brief.

    Raw function without @mcp.tool decorator for A2A server use.

    Args:
        brief: Brief description of the advertising campaign or requirements
        promoted_offering: DEPRECATED: Use brand_manifest instead (still supported for backward compatibility)
        brand_manifest: Brand information manifest (inline object or URL string)
        adcp_version: AdCP schema version for this request (default: 1.0.0)
        min_exposures: Minimum impressions needed for measurement validity (optional)
        filters: Structured filters for product discovery (optional)
        strategy_id: Optional strategy ID for linking operations (optional)
        context: FastMCP context (automatically provided)

    Returns:
        GetProductsResponse containing matching products
    """
    # Create request object using helper (handles generated schema variants)
    req = create_get_products_request(
        brief=brief or "",
        promoted_offering=promoted_offering,
        brand_manifest=brand_manifest,
        filters=filters,
    )

    # Call shared implementation
    return await _get_products_impl(req, context)
