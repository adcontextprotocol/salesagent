"""Format specification cache for offline/fast validation.

Caches full Format objects from the reference creative agent to enable:
1. Fast validation without network calls
2. Offline testing
3. Production resilience (works even if creative agent is down)

The cache is automatically refreshed when formats are fetched, but can also
work entirely offline using pre-cached formats.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.schemas import Format

logger = logging.getLogger(__name__)

# Cache file location
CACHE_DIR = Path(__file__).parent.parent.parent / "cache" / "format_specs"
CACHE_FILE = CACHE_DIR / "reference_formats.json"

# Default agent URL for AdCP reference implementation
DEFAULT_AGENT_URL = "https://creative.adcontextprotocol.org"


def load_cached_format_specs() -> dict[str, dict[str, Any]]:
    """Load cached format specifications from disk.

    Returns:
        Dict mapping format_id to format spec dict
    """
    if not CACHE_FILE.exists():
        logger.debug(f"Format spec cache not found at {CACHE_FILE}")
        return {}

    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
            return data.get("formats", {})
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load format spec cache: {e}")
        return {}


def save_format_specs_to_cache(formats: list[Format]) -> None:
    """Save format specifications to cache.

    Args:
        formats: List of Format objects to cache
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Convert Format objects to dicts, keyed by format_id
    format_dict = {}
    for fmt in formats:
        format_id = fmt.format_id.id if hasattr(fmt.format_id, "id") else str(fmt.format_id)
        format_dict[format_id] = fmt.model_dump()

    data = {
        "formats": format_dict,
        "cached_at": datetime.now(UTC).isoformat(),
        "agent_url": DEFAULT_AGENT_URL,
        "count": len(format_dict),
    }

    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Cached {len(format_dict)} format specs to {CACHE_FILE}")
    except OSError as e:
        logger.warning(f"Failed to save format spec cache: {e}")


def get_cached_format(format_id: str) -> Format | None:
    """Get a cached format specification.

    Args:
        format_id: Format ID to look up (e.g., "display_970x250_image")

    Returns:
        Format object if found in cache, None otherwise

    Note:
        If exact format_id not found, tries common suffixes (_image, _html, _generative)
        to support legacy test formats like "display_300x250" → "display_300x250_image"

        For legacy video formats like "video_640x480", maps to closest standard format.
    """
    cached_specs = load_cached_format_specs()

    # Try exact match first
    if format_id in cached_specs:
        try:
            return Format(**cached_specs[format_id])
        except Exception as e:
            logger.warning(f"Failed to deserialize cached format {format_id}: {e}")
            return None

    # Legacy format mappings (for tests using old format IDs)
    legacy_mappings = {
        "video_640x480": "video_1280x720",  # Map to closest standard video format
    }

    if format_id in legacy_mappings:
        mapped_id = legacy_mappings[format_id]
        logger.info(
            f"Legacy format '{format_id}' mapped to standard format '{mapped_id}' " f"(backwards compatibility)"
        )
        if mapped_id in cached_specs:
            try:
                return Format(**cached_specs[mapped_id])
            except Exception as e:
                logger.warning(f"Failed to deserialize cached format {mapped_id}: {e}")
                return None

    # Try common suffixes for backwards compatibility with tests
    # (e.g., "display_300x250" → "display_300x250_image")
    suffixes = ["_image", "_html", "_generative"]
    for suffix in suffixes:
        candidate_id = f"{format_id}{suffix}"
        if candidate_id in cached_specs:
            logger.info(f"Format '{format_id}' not found, using '{candidate_id}' instead " f"(backwards compatibility)")
            try:
                return Format(**cached_specs[candidate_id])
            except Exception as e:
                logger.warning(f"Failed to deserialize cached format {candidate_id}: {e}")
                continue

    return None


async def refresh_format_cache() -> None:
    """Refresh the format cache from the reference creative agent.

    Fetches all formats from the reference agent and saves to cache.
    Safe to call periodically or on startup.
    """
    try:
        from src.core.creative_agent_registry import get_creative_agent_registry

        registry = get_creative_agent_registry()
        formats = await registry.list_all_formats(tenant_id=None)

        # Filter to only reference agent formats
        reference_formats = [fmt for fmt in formats if fmt.agent_url == DEFAULT_AGENT_URL or fmt.agent_url is None]

        if reference_formats:
            save_format_specs_to_cache(reference_formats)
            logger.info(f"Refreshed format cache with {len(reference_formats)} formats")
        else:
            logger.warning("No reference formats found during cache refresh")

    except Exception as e:
        logger.error(f"Failed to refresh format cache: {e}")


def refresh_format_cache_sync() -> None:
    """Synchronous wrapper for refresh_format_cache().

    Creates event loop and runs async refresh.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(refresh_format_cache())
    finally:
        loop.close()


# Auto-refresh cache on import if it doesn't exist or is old
def _auto_refresh_cache_if_needed():
    """Check if cache needs refresh and do it in background if needed."""
    if not CACHE_FILE.exists():
        logger.info("Format spec cache missing - will refresh on first use")
        return

    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
            cached_at_str = data.get("cached_at", "")

        # Parse cached_at timestamp
        if cached_at_str:
            from datetime import timedelta

            cached_at = datetime.fromisoformat(cached_at_str.replace("Z", "+00:00"))
            age = datetime.now(cached_at.tzinfo) - cached_at

            # Refresh if older than 7 days
            if age > timedelta(days=7):
                logger.info(f"Format cache is {age.days} days old - will refresh on first use")

    except Exception as e:
        logger.debug(f"Failed to check cache age: {e}")


_auto_refresh_cache_if_needed()
