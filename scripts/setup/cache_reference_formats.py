#!/usr/bin/env python3
"""Cache format specifications from the reference creative agent.

This script fetches all formats from the AdCP reference creative agent
and caches them locally for offline use and fast validation.

Run this:
- During deployment/setup
- Periodically to refresh the cache
- When format specifications are updated

Usage:
    uv run python scripts/setup/cache_reference_formats.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


async def main():
    """Fetch and cache reference formats."""
    from src.core.format_spec_cache import refresh_format_cache

    print("Fetching formats from reference creative agent...")
    print("Agent: https://creative.adcontextprotocol.org")
    print()

    try:
        await refresh_format_cache()
        print()
        print("✅ Format cache refreshed successfully!")
        print()

        # Show what was cached
        from src.core.format_spec_cache import load_cached_format_specs

        cached = load_cached_format_specs()
        print(f"Cached {len(cached)} format specifications:")
        for format_id in sorted(cached.keys()):
            fmt_data = cached[format_id]
            fmt_type = fmt_data.get("type", "unknown")
            is_gen = bool(fmt_data.get("output_format_ids"))
            gen_marker = " (generative)" if is_gen else ""
            print(f"  - {format_id:40s} {fmt_type:10s}{gen_marker}")

    except Exception as e:
        print(f"❌ Failed to cache formats: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
