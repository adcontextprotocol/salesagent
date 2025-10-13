"""Naming template utilities for orders and line items.

Adapter-agnostic utilities that work across all ad servers (GAM, Mock, Kevel, etc.)

Supports variable substitution with fallback syntax:
- {campaign_name} - Direct substitution
- {campaign_name|promoted_offering} - Use campaign_name, fall back to promoted_offering
- {date_range} - Formatted date range (e.g., "Oct 7-14, 2025")
- {month_year} - Month and year (e.g., "Oct 2025")
- {promoted_offering} - What's being advertised
- {buyer_ref} - Buyer's reference ID
- {auto_name} - AI-generated name from full context (requires Gemini API key)
- {product_name} - Product name (for line items)
- {package_count} - Number of packages in order
- {package_index} - Package position number (1, 2, 3...)
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def format_date_range(start_time: datetime, end_time: datetime) -> str:
    """Format date range for display.

    Examples:
        - Same month: "Oct 7-14, 2025"
        - Different months: "Oct 15 - Nov 5, 2025"
        - Different years: "Dec 28, 2024 - Jan 5, 2025"
    """
    if start_time.year != end_time.year:
        return f"{start_time.strftime('%b %d, %Y')} - {end_time.strftime('%b %d, %Y')}"
    elif start_time.month != end_time.month:
        return f"{start_time.strftime('%b %d')} - {end_time.strftime('%b %d, %Y')}"
    else:
        return f"{start_time.strftime('%b %d')}-{end_time.strftime('%d, %Y')}"


def format_month_year(start_time: datetime) -> str:
    """Format month and year for display.

    Example: "Oct 2025"
    """
    return start_time.strftime("%b %Y")


def generate_auto_name(
    request,
    packages: list,
    start_time: datetime,
    end_time: datetime,
    tenant_gemini_key: str | None = None,
    max_length: int = 150,
) -> str:
    """Generate AI-powered order name using Gemini.

    Args:
        request: CreateMediaBuyRequest object
        packages: List of MediaPackage objects
        start_time: Order start datetime
        end_time: Order end datetime
        tenant_gemini_key: Tenant's Gemini API key (if configured)
        max_length: Maximum length for generated name

    Returns:
        AI-generated name, or falls back to promoted_offering if Gemini unavailable

    Example output:
        "Nike Air Max Campaign - Q4 Holiday Push"
        "Acme Corp Brand Awareness - Premium Video"
    """
    # Fallback if Gemini not configured
    if not tenant_gemini_key:
        logger.debug("No Gemini API key configured, falling back to promoted_offering")
        return request.promoted_offering or request.campaign_name or "Campaign"

    try:
        import google.generativeai as genai
        from pydantic import BaseModel, Field

        class OrderNameResponse(BaseModel):
            name: str = Field(..., max_length=max_length, description="Concise, professional order name")

        # Configure Gemini
        genai.configure(api_key=tenant_gemini_key)
        model = genai.GenerativeModel("gemini-2.0-flash-lite")

        # Build context for AI
        context_parts = [
            f"Buyer Reference: {request.buyer_ref}",
            f"Campaign: {request.campaign_name or 'N/A'}",
            f"Promoted Offering: {request.promoted_offering or 'N/A'}",
            f"Budget: ${request.budget.total:,.2f} {request.budget.currency}",
            f"Duration: {format_date_range(start_time, end_time)}",
            f"Products: {', '.join([pkg.product_id for pkg in packages])}",
        ]

        # Add brand manifest if available
        if hasattr(request, "brand_manifest") and request.brand_manifest:
            manifest = request.brand_manifest
            if hasattr(manifest, "brand_name") and manifest.brand_name:
                context_parts.insert(0, f"Brand: {manifest.brand_name}")
            if hasattr(manifest, "campaign_objectives") and manifest.campaign_objectives:
                context_parts.append(f"Objectives: {', '.join(manifest.campaign_objectives[:2])}")

        context = "\n".join(context_parts)

        prompt = f"""Generate a concise, professional order name for this advertising campaign.

Requirements:
- Maximum {max_length} characters
- Include buyer reference "{request.buyer_ref}" somewhere in the name
- Professional and scannable
- Captures the essence of the campaign

Campaign Details:
{context}

Return ONLY the order name, nothing else."""

        # Call Gemini with timeout
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=100,
                temperature=0.3,  # Fairly deterministic
            ),
            request_options={"timeout": 2.0},  # 2 second timeout
        )

        generated_name = response.text.strip().strip('"').strip("'")

        # Validate length
        if len(generated_name) > max_length:
            logger.warning(f"Generated name too long ({len(generated_name)} > {max_length}), truncating")
            generated_name = generated_name[:max_length].rsplit(" ", 1)[0] + "..."

        logger.info(f"Generated auto_name: {generated_name}")
        return generated_name

    except Exception as e:
        logger.warning(f"Failed to generate auto_name with Gemini: {e}, falling back")
        # Fallback to promoted_offering or campaign_name
        return request.promoted_offering or request.campaign_name or "Campaign"


def apply_naming_template(
    template: str,
    context: dict,
) -> str:
    """Apply naming template with variable substitution and fallback support.

    Args:
        template: Template string with {variable} or {var1|var2|var3} syntax
        context: Dictionary of available variables

    Returns:
        Formatted string with variables substituted

    Examples:
        >>> apply_naming_template("{campaign_name} - {date_range}", {
        ...     "campaign_name": "Q1 Launch",
        ...     "date_range": "Oct 7-14, 2025"
        ... })
        "Q1 Launch - Oct 7-14, 2025"

        >>> apply_naming_template("{campaign_name|promoted_offering}", {
        ...     "campaign_name": None,
        ...     "promoted_offering": "Nike Shoes"
        ... })
        "Nike Shoes"
    """
    # Ensure template is a string (handle MagicMock in tests)
    if not isinstance(template, str):
        template = str(template)

    result = template

    # Find all {variable} or {var1|var2} patterns
    import re

    pattern = r"\{([^}]+)\}"

    for match in re.finditer(pattern, result):
        full_match = match.group(0)  # e.g., "{campaign_name|promoted_offering}"
        variables = match.group(1).split("|")  # e.g., ["campaign_name", "promoted_offering"]

        # Try each variable in order until we find a non-None, non-empty value
        value = None
        for var_name in variables:
            var_name = var_name.strip()
            if var_name in context:
                candidate = context[var_name]
                if candidate is not None and candidate != "":
                    value = str(candidate)
                    break

        # If no value found, use empty string (or could use first variable name as placeholder)
        if value is None:
            value = ""

        result = result.replace(full_match, value)

    return result


def build_order_name_context(
    request,
    packages: list,
    start_time: datetime,
    end_time: datetime,
    tenant_gemini_key: str | None = None,
) -> dict:
    """Build context dictionary for order name template.

    Args:
        request: CreateMediaBuyRequest object
        packages: List of MediaPackage objects
        start_time: Order start datetime
        end_time: Order end datetime
        tenant_gemini_key: Optional Gemini API key for auto_name generation

    Returns:
        Dictionary of variables available for template substitution
    """
    # Generate auto_name if template uses it (lazy evaluation via dict access is fine)
    # Note: This gets called only if {auto_name} is in the template
    auto_name = generate_auto_name(
        request=request,
        packages=packages,
        start_time=start_time,
        end_time=end_time,
        tenant_gemini_key=tenant_gemini_key,
    )

    return {
        "campaign_name": request.campaign_name,
        "promoted_offering": request.promoted_offering,
        "buyer_ref": request.buyer_ref,
        "auto_name": auto_name,
        "date_range": format_date_range(start_time, end_time),
        "month_year": format_month_year(start_time),
        "package_count": len(packages),
        "start_date": start_time.strftime("%Y-%m-%d"),
        "end_date": end_time.strftime("%Y-%m-%d"),
    }


def build_line_item_name_context(
    order_name: str,
    product_name: str,
    package_index: int | None = None,
) -> dict:
    """Build context dictionary for line item name template.

    Args:
        order_name: Name of the parent order
        product_name: Name of the product/package
        package_index: Optional index of package in order (1-based)

    Returns:
        Dictionary of variables available for template substitution
    """
    context = {
        "order_name": order_name,
        "product_name": product_name,
    }

    if package_index is not None:
        context["package_index"] = str(package_index)

    return context
