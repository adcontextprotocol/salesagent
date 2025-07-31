#!/usr/bin/env python3
"""AI-driven product configuration service.

This service takes natural language descriptions and automatically configures
products by:
1. Analyzing external (buyer-facing) descriptions
2. Processing internal implementation details
3. Querying ad server APIs for available inventory
4. Intelligently mapping to appropriate configurations
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import aiohttp
from bs4 import BeautifulSoup
import google.generativeai as genai
import os
from urllib.parse import urlparse

from db_config import get_db_connection
from schemas import CreativeFormat
from targeting_capabilities import TargetingCapabilities

logger = logging.getLogger(__name__)

@dataclass
class ProductDescription:
    """External and internal product descriptions."""
    name: str
    external_description: str  # What buyers see
    internal_details: Optional[str] = None  # Publisher's implementation notes
    
@dataclass
class AdServerInventory:
    """Available inventory from ad server."""
    placements: List[Dict[str, Any]]
    ad_units: List[Dict[str, Any]]
    targeting_options: Dict[str, List[Any]]
    creative_specs: List[Dict[str, Any]]
    properties: Optional[Dict[str, Any]] = None

class AIProductConfigurationService:
    """Service that uses AI to automatically configure products."""
    
    def __init__(self):
        # Initialize Gemini
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
    async def create_product_from_description(
        self,
        tenant_id: str,
        description: ProductDescription,
        adapter_type: str
    ) -> Dict[str, Any]:
        """Create a complete product configuration from descriptions."""
        
        # 1. Fetch ad server inventory
        inventory = await self._fetch_ad_server_inventory(tenant_id, adapter_type)
        
        # 2. Get existing formats from database (standard + custom for this tenant)
        creative_formats = self._get_available_formats(tenant_id)
        
        # 3. Use AI to generate configuration
        config = await self._generate_product_configuration(
            description=description,
            inventory=inventory,
            creative_formats=creative_formats,
            adapter_type=adapter_type
        )
        
        return config
    
    async def _fetch_ad_server_inventory(
        self, 
        tenant_id: str, 
        adapter_type: str
    ) -> AdServerInventory:
        """Fetch available inventory from ad server."""
        
        # Get adapter configuration and principal
        conn = get_db_connection()
        
        # Get tenant config
        cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
        tenant_config_row = cursor.fetchone()
        if not tenant_config_row:
            conn.close()
            raise ValueError(f"Tenant {tenant_id} not found")
        
        # PostgreSQL returns JSONB as dict, SQLite returns string
        tenant_config = tenant_config_row[0] if isinstance(tenant_config_row[0], dict) else json.loads(tenant_config_row[0])
        
        # Get a principal for this tenant (use first available)
        cursor = conn.execute(
            "SELECT principal_id, name, access_token, platform_mappings FROM principals WHERE tenant_id = ? LIMIT 1",
            (tenant_id,)
        )
        principal_row = cursor.fetchone()
        conn.close()
        
        if not principal_row:
            # Create a temporary principal for inventory fetching
            from schemas import Principal
            principal = Principal(
                principal_id="ai_config_temp",
                name="AI Configuration Service",
                access_token="ai_config_token",
                platform_mappings={}
            )
        else:
            from schemas import Principal
            mappings = principal_row[3] if isinstance(principal_row[3], dict) else json.loads(principal_row[3])
            principal = Principal(
                principal_id=principal_row[0],
                name=principal_row[1],
                access_token=principal_row[2],
                platform_mappings=mappings
            )
        
        # Get adapter instance
        from adapters import get_adapter_class
        adapter_class = get_adapter_class(adapter_type)
        
        # Get adapter config
        adapter_config = tenant_config.get('adapters', {}).get(adapter_type, {})
        
        # Create adapter instance
        adapter = adapter_class(
            config=adapter_config,
            principal=principal,
            dry_run=True,  # Always dry-run for inventory fetching
            tenant_id=tenant_id
        )
        
        # Fetch inventory from adapter
        inventory_data = await adapter.get_available_inventory()
        
        return AdServerInventory(
            placements=inventory_data.get("placements", []),
            ad_units=inventory_data.get("ad_units", []),
            targeting_options=inventory_data.get("targeting_options", {}),
            creative_specs=inventory_data.get("creative_specs", []),
            properties=inventory_data.get("properties", {})
        )
    
    def _get_available_formats(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Get all available creative formats (standard + custom for tenant)."""
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT format_id, name, type, description, width, height, duration_seconds
            FROM creative_formats
            WHERE tenant_id IS NULL OR tenant_id = ?
            ORDER BY is_standard DESC, type, name
        """, (tenant_id,))
        
        formats = []
        for row in cursor:
            format_dict = {
                "format_id": row[0],
                "name": row[1],
                "type": row[2],
                "description": row[3]
            }
            
            # Add dimensions for display formats
            if row[4] and row[5]:
                format_dict["dimensions"] = f"{row[4]}x{row[5]}"
                format_dict["width"] = row[4]
                format_dict["height"] = row[5]
            
            # Add duration for video/audio formats
            if row[6]:
                format_dict["duration"] = f"{row[6]}s"
                format_dict["duration_seconds"] = row[6]
                
            formats.append(format_dict)
        
        conn.close()
        return formats
    
    async def _generate_product_configuration(
        self,
        description: ProductDescription,
        inventory: AdServerInventory,
        creative_formats: List[Dict[str, Any]],
        adapter_type: str
    ) -> Dict[str, Any]:
        """Use AI to generate optimal product configuration."""
        
        # Prepare context for AI
        context = {
            "description": {
                "name": description.name,
                "external": description.external_description,
                "internal": description.internal_details
            },
            "available_inventory": {
                "placements": inventory.placements,
                "ad_units": inventory.ad_units,
                "targeting": inventory.targeting_options
            },
            "creative_formats": creative_formats,
            "adapter": adapter_type
        }
        
        prompt = f"""
        You are an expert ad operations specialist. Create an optimal product configuration
        based on the following information:
        
        Product Description:
        - Name: {description.name}
        - External (buyer-facing): {description.external_description}
        - Internal details: {description.internal_details or 'None provided'}
        
        Available Ad Server Inventory:
        {json.dumps(inventory.placements, indent=2)}
        
        Available Targeting Options:
        {json.dumps(inventory.targeting_options, indent=2)}
        
        Creative Formats Available:
        {json.dumps([f for f in creative_formats if f['type'] in ['display', 'video']], indent=2)}
        
        Generate a product configuration with:
        1. Selected placements that best match the product description
        2. Appropriate creative formats
        3. Suggested pricing (CPM) based on premium-ness
        4. Targeting template that makes sense
        5. Implementation configuration for {adapter_type}
        
        Consider:
        - Premium placements (homepage, above-fold) should have higher CPMs
        - Match creative formats to placement capabilities
        - Set appropriate geographic targeting
        - Configure any adapter-specific settings
        
        Return ONLY a valid JSON object with this structure:
        {{
            "product_id": "generated_id",
            "formats": ["format_id1", "format_id2"],
            "delivery_type": "guaranteed" or "non_guaranteed",
            "cpm": number or null,
            "price_guidance": {{"min": number, "max": number}} or null,
            "countries": ["US", "CA"] or null for all,
            "targeting_template": {{
                "geo_targets": {{"countries": [...]}},
                "device_targets": {{"device_types": [...]}},
                "placement_targets": {{"ad_unit_ids": [...]}}
            }},
            "implementation_config": {{
                "placements": [...],
                "ad_units": [...],
                "{adapter_type}_specific": {{...}}
            }}
        }}
        """
        
        response = self.model.generate_content(prompt)
        
        try:
            config = json.loads(response.text)
            
            # Validate and clean configuration
            config = self._validate_configuration(config, creative_formats)
            
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response: {e}")
            # Return a safe default configuration
            return self._get_default_configuration(description, creative_formats)
    
    def _validate_configuration(
        self, 
        config: Dict[str, Any], 
        available_formats: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Validate and clean AI-generated configuration."""
        
        # Ensure formats exist
        available_format_ids = [f["format_id"] for f in available_formats]
        config["formats"] = [f for f in config.get("formats", []) if f in available_format_ids]
        
        # Ensure valid delivery type
        if config.get("delivery_type") not in ["guaranteed", "non_guaranteed"]:
            config["delivery_type"] = "guaranteed"
        
        # Validate pricing
        if config["delivery_type"] == "guaranteed":
            if not config.get("cpm") or config["cpm"] <= 0:
                config["cpm"] = 5.0  # Default CPM
            config["price_guidance"] = None
        else:
            config["cpm"] = None
            if not config.get("price_guidance"):
                config["price_guidance"] = {"min": 2.0, "max": 10.0}
        
        # Ensure targeting template has required structure
        if not config.get("targeting_template"):
            config["targeting_template"] = {}
        
        return config
    
    def _get_default_configuration(
        self,
        description: ProductDescription,
        creative_formats: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Return a safe default configuration."""
        
        # Pick common display formats
        display_formats = [f for f in creative_formats if f["type"] == "display"][:3]
        
        return {
            "product_id": description.name.lower().replace(" ", "_"),
            "formats": [f["format_id"] for f in display_formats],
            "delivery_type": "guaranteed",
            "cpm": 5.0,
            "price_guidance": None,
            "countries": None,  # All countries
            "targeting_template": {
                "geo_targets": {"countries": ["US"]},
                "device_targets": {"device_types": ["desktop", "mobile"]}
            },
            "implementation_config": {}
        }

# API endpoints for the admin UI
async def analyze_product_description(
    tenant_id: str,
    name: str,
    external_description: str,
    internal_details: Optional[str] = None
) -> Dict[str, Any]:
    """Analyze descriptions and return suggested configuration."""
    
    service = AIProductConfigurationService()
    
    # Get tenant's adapter type
    conn = get_db_connection()
    cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
    tenant_config_row = cursor.fetchone()
    # PostgreSQL returns JSONB as dict, SQLite returns string
    tenant_config = tenant_config_row[0] if isinstance(tenant_config_row[0], dict) else json.loads(tenant_config_row[0])
    conn.close()
    
    # Find enabled adapter
    adapter_type = None
    for adapter, config in tenant_config.get("adapters", {}).items():
        if config.get("enabled"):
            adapter_type = adapter
            break
    
    if not adapter_type:
        raise ValueError("No enabled adapter found for tenant")
    
    description = ProductDescription(
        name=name,
        external_description=external_description,
        internal_details=internal_details
    )
    
    config = await service.create_product_from_description(
        tenant_id=tenant_id,
        description=description,
        adapter_type=adapter_type
    )
    
    return config