"""Creative format parsing and asset conversion helpers."""

from typing import Any

from src.core.schemas import Creative


def _extract_format_namespace(format_value: Any) -> tuple[str, str]:
    """Extract agent_url and format ID from format_id field (AdCP v2.4).

    Args:
        format_value: FormatId dict/object with agent_url+id fields

    Returns:
        Tuple of (agent_url, format_id)

    Raises:
        ValueError: If format_value doesn't have required agent_url and id fields
    """
    if isinstance(format_value, dict):
        agent_url = format_value.get("agent_url")
        format_id = format_value.get("id")
        if not agent_url or not format_id:
            raise ValueError(f"format_id must have both 'agent_url' and 'id' fields. Got: {format_value}")
        return agent_url, format_id
    if hasattr(format_value, "agent_url") and hasattr(format_value, "id"):
        return format_value.agent_url, format_value.id
    if isinstance(format_value, str):
        raise ValueError(
            f"format_id must be an object with 'agent_url' and 'id' fields (AdCP v2.4). "
            f"Got string: '{format_value}'. "
            f"String format_id is no longer supported - all formats must be namespaced."
        )
    raise ValueError(f"Invalid format_id format. Expected object with agent_url and id, got: {type(format_value)}")


def _normalize_format_value(format_value: Any) -> str:
    """Normalize format value to string ID (for legacy code compatibility).

    Args:
        format_value: FormatId dict/object with agent_url+id fields

    Returns:
        String format identifier

    Note: This is a legacy compatibility function. New code should use _extract_format_namespace
    to properly handle the agent_url namespace.
    """
    _, format_id = _extract_format_namespace(format_value)
    return format_id


def _validate_creative_assets(assets: Any) -> dict[str, dict[str, Any]] | None:
    """Validate that creative assets are in AdCP v2.1+ dictionary format.

    AdCP v2.1+ requires assets to be a dictionary keyed by asset_id from the format's
    asset_requirements.

    Args:
        assets: Assets in dict format keyed by asset_id, or None

    Returns:
        Dictionary of assets keyed by asset_id, or None if no assets provided

    Raises:
        ValueError: If assets are not in the correct dict format, or if asset structure is invalid

    Example:
        # Correct format (AdCP v2.1+)
        assets = {
            "main_image": {"asset_type": "image", "url": "https://..."},
            "logo": {"asset_type": "image", "url": "https://..."}
        }
    """
    if assets is None:
        return None

    # Must be a dict
    if not isinstance(assets, dict):
        raise ValueError(
            f"Invalid assets format: expected dict keyed by asset_id (AdCP v2.1+), got {type(assets).__name__}. "
            f"Assets must be a dictionary like: {{'main_image': {{'asset_type': 'image', 'url': '...'}}}}"
        )

    # Validate structure of each asset
    for asset_id, asset_data in assets.items():
        # Asset ID must be a non-empty string
        if not isinstance(asset_id, str):
            raise ValueError(
                f"Asset key must be a string (asset_id from format), got {type(asset_id).__name__}: {asset_id!r}"
            )
        if not asset_id.strip():
            raise ValueError("Asset key (asset_id) cannot be empty or whitespace-only")

        # Asset data must be a dict
        if not isinstance(asset_data, dict):
            raise ValueError(
                f"Asset '{asset_id}' data must be a dict, got {type(asset_data).__name__}. "
                f"Expected format: {{'asset_type': '...', 'url': '...', ...}}"
            )

    return assets


def _convert_creative_to_adapter_asset(creative: Creative, package_assignments: list[str]) -> dict[str, Any]:
    """Convert AdCP v1.3+ Creative object to format expected by ad server adapters."""

    # Base asset object with common fields
    asset = {
        "creative_id": creative.creative_id,
        "name": creative.name,
        "format": creative.get_format_string(),  # Handle both string and FormatId object
        "package_assignments": package_assignments,
    }

    # Determine creative type using AdCP v1.3+ logic
    creative_type = creative.get_creative_type()

    if creative_type == "third_party_tag":
        # Third-party tag creative - use AdCP v1.3+ snippet fields
        snippet = creative.get_snippet_content()
        if not snippet:
            raise ValueError(f"No snippet found for third-party creative {creative.creative_id}")

        asset["snippet"] = snippet
        asset["snippet_type"] = creative.snippet_type or _detect_snippet_type(snippet)
        asset["url"] = creative.url  # Keep URL for fallback

    elif creative_type == "native":
        # Native creative - use AdCP v1.3+ template_variables field
        template_vars = creative.get_template_variables_dict()
        if not template_vars:
            raise ValueError(f"No template_variables found for native creative {creative.creative_id}")

        asset["template_variables"] = template_vars
        asset["url"] = creative.url  # Fallback URL

    elif creative_type == "vast":
        # VAST reference
        asset["snippet"] = creative.get_snippet_content() or creative.url
        asset["snippet_type"] = creative.snippet_type or ("vast_xml" if ".xml" in creative.url else "vast_url")

    else:  # hosted_asset
        # Traditional hosted asset (image/video)
        asset["media_url"] = creative.get_primary_content_url()
        asset["url"] = asset["media_url"]  # For backward compatibility

    # Add common optional fields
    if creative.click_url:
        asset["click_url"] = creative.click_url
    if creative.width:
        asset["width"] = creative.width
    if creative.height:
        asset["height"] = creative.height
    if creative.duration:
        asset["duration"] = creative.duration

    # Always preserve delivery_settings (including tracking_urls) for all creative types
    # This ensures impression trackers from buyers flow through to ad servers
    if creative.delivery_settings:
        asset["delivery_settings"] = creative.delivery_settings

    return asset


def _detect_snippet_type(snippet: str) -> str:
    """Auto-detect snippet type from content for legacy support."""
    if snippet.startswith("<?xml") or ".xml" in snippet:
        return "vast_xml"
    elif snippet.startswith("http") and "vast" in snippet.lower():
        return "vast_url"
    elif snippet.startswith("<script"):
        return "javascript"
    else:
        return "html"  # Default
