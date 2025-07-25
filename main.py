import sqlite3
import json
from datetime import datetime, timedelta
from typing import List

from fastmcp import FastMCP
from rich.console import Console

from database import init_db
from schemas import *

# --- Initialization ---
init_db()
mcp = FastMCP(name="AdCPBuySideV2_1")
console = Console()
packages_cache: Dict[str, List[MediaPackage]] = {}

# --- Helper Functions ---

def _check_creative_compatibility(creative: CreativeAsset, placement_formats: List[Dict]) -> CreativeCompatibility:
    """Checks if a creative is compatible with the formats supported by a placement."""
    for format_info in placement_formats:
        if creative.format_id == format_info['format_id']:
            # This is a simplified check. A real implementation would validate
            # the creative's spec against the format's spec.
            return CreativeCompatibility(compatible=True, requires_approval=True)
    
    return CreativeCompatibility(compatible=False, requires_approval=False, reason="No matching format_id found.")

# --- MCP Tools ---

@mcp.tool
def get_publisher_creative_formats() -> GetPublisherCreativeFormatsResponse:
    """Returns all creative formats supported by the publisher."""
    conn = sqlite3.connect('adcp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT format_id, format_type, spec FROM creative_formats")
    formats = [CreativeFormat(format_id=row['format_id'], format_type=row['format_type'], spec=json.loads(row['spec'])) for row in cursor.fetchall()]
    conn.close()
    return GetPublisherCreativeFormatsResponse(formats=formats)

@mcp.tool
def get_packages(request: GetPackagesRequest) -> GetPackagesResponse:
    """Discover all available packages based on media buy criteria."""
    conn = sqlite3.connect('adcp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM placements")
    placements = [dict(row) for row in cursor.fetchall()]
    
    media_packages = []
    for p in placements:
        cursor.execute("SELECT cf.* FROM creative_formats cf JOIN placement_formats pf ON cf.id = pf.format_id WHERE pf.placement_id = ?", (p['id'],))
        supported_formats = [dict(row) for row in cursor.fetchall()]

        compat_map = {c.id: _check_creative_compatibility(c, supported_formats) for c in request.creatives}

        pkg_data = {
            "package_id": f"pkg_{p['id']}", "name": p['name'], "description": "...",
            "type": p['type'], "delivery_type": p['delivery_type'],
            "creative_compatibility": compat_map,
            "cpm": p['base_cpm'], "pricing": json.loads(p['pricing_guidance']) if p['pricing_guidance'] else None
        }
        media_packages.append(MediaPackage(**pkg_data))

    conn.close()
    
    query_id = f"query_{int(datetime.now().timestamp())}"
    packages_cache[query_id] = media_packages
    console.print(f"[bold yellow]Generated Query ID:[/bold yellow] {query_id}")

    return GetPackagesResponse(query_id=query_id, packages=media_packages)

@mcp.tool
def create_media_buy(request: CreateMediaBuyRequest, query_id: str) -> CreateMediaBuyResponse:
    """Create a media buy from a set of selected packages."""
    # This is a simplified stub. A real implementation would call the ad server adapter.
    media_buy_id = f"mb_{int(datetime.now().timestamp())}"
    return CreateMediaBuyResponse(media_buy_id=media_buy_id, status="pending_activation")

if __name__ == "__main__":
    mcp.run()
