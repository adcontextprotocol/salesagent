import sqlite3
import json
from datetime import datetime
from typing import List, Dict

import google.generativeai as genai
from fastmcp import FastMCP
from rich.console import Console

from database import init_db
from schemas import *

# --- Configuration and Initialization ---
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

config = load_config()
api_key = config.get("gemini_api_key")
if api_key:
    genai.configure(api_key=api_key)

init_db()
mcp = FastMCP(name="AdCPBuySideV2_2")
console = Console()
packages_cache: Dict[str, List[MediaPackage]] = {}

# --- MCP Tools ---

@mcp.tool
def get_publisher_creative_formats() -> GetPublisherCreativeFormatsResponse:
    # ... (implementation remains the same)
    pass

@mcp.tool
def get_packages(request: GetPackagesRequest) -> GetPackagesResponse:
    """Discovers catalog packages and generates custom packages from a brief."""
    conn = sqlite3.connect('adcp.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fetch all packages from the database
    cursor.execute("SELECT * FROM placements")
    placements = [dict(row) for row in cursor.fetchall()]
    
    all_packages = []
    for p in placements:
        pkg_data = {
            "package_id": f"pkg_{p['id']}", "name": p['name'], "description": "...",
            "type": p['type'], "delivery_type": p['delivery_type'],
            "cpm": p['base_cpm'], "pricing": json.loads(p['pricing_guidance']) if p['pricing_guidance'] else None
        }
        all_packages.append(MediaPackage(**pkg_data))

    # 2. If a brief is provided, generate additional custom packages
    if request.brief and api_key:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        Based on the following brief, generate 1-2 custom media packages.
        Brief: "{request.brief}"
        Available inventory types: In-Feed Video, Homepage Takeover, Sponsored Article.
        For each package, provide a name, description, delivery_type ('guaranteed'), and a suggested CPM.
        Respond in a JSON array format: 
        [
            {{"name": "...", "description": "...", "cpm": ...}},
            ...
        ]
        """
        response = model.generate_content(prompt)
        clean_json_str = response.text.strip().replace("```json", "").replace("```", "").strip()
        custom_packages_data = json.loads(clean_json_str)
        
        for i, custom_data in enumerate(custom_packages_data):
            custom_pkg = MediaPackage(
                package_id=f"custom_{i+1}",
                name=custom_data['name'],
                description=custom_data['description'],
                type="custom",
                delivery_type="guaranteed",
                cpm=custom_data['cpm']
            )
            all_packages.append(custom_pkg)

    conn.close()
    
    query_id = f"query_{int(datetime.now().timestamp())}"
    packages_cache[query_id] = all_packages
    console.print(f"[bold yellow]Generated Query ID:[/bold yellow] {query_id}")

    return GetPackagesResponse(query_id=query_id, packages=all_packages)

@mcp.tool
def create_media_buy(request: CreateMediaBuyRequest) -> CreateMediaBuyResponse:
    """Creates a media buy, passing the rich request to the ad server adapter."""
    # In a real implementation, this would call the ad server adapter.
    # The adapter would be responsible for translating the targeting overlay
    # and other parameters into ad server specific objects.
    console.print(f"Received request to create media buy for PO: {request.po_number}")
    console.print("Targeting Overlay:", request.targeting)
    
    media_buy_id = f"mb_{request.po_number}"
    return CreateMediaBuyResponse(media_buy_id=media_buy_id, status="pending_activation")

if __name__ == "__main__":
    mcp.run()