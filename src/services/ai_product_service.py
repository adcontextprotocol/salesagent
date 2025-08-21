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
import os
from dataclasses import dataclass
from typing import Any

import google.generativeai as genai

from src.core.database.database_session import get_db_session
from src.core.database.models import Principal as PrincipalModel
from src.core.database.models import Tenant

logger = logging.getLogger(__name__)


@dataclass
class ProductDescription:
    """External and internal product descriptions."""

    name: str
    external_description: str  # What buyers see
    internal_details: str | None = None  # Publisher's implementation notes


@dataclass
class AdServerInventory:
    """Available inventory from ad server."""

    placements: list[dict[str, Any]]
    ad_units: list[dict[str, Any]]
    targeting_options: dict[str, list[Any]]
    creative_specs: list[dict[str, Any]]
    properties: dict[str, Any] | None = None


class AIProductConfigurationService:
    """Service that uses AI to automatically configure products."""

    def __init__(self):
        # Initialize Gemini
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        genai.configure(api_key=api_key)
        # Using Gemini 2.5 Flash for improved performance and capabilities
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    async def create_product_from_description(
        self, tenant_id: str, description: ProductDescription, adapter_type: str
    ) -> dict[str, Any]:
        """Create a complete product configuration from descriptions."""

        # 1. Fetch ad server inventory
        inventory = await self._fetch_ad_server_inventory(tenant_id, adapter_type)

        # 2. Get existing formats from database (standard + custom for this tenant)
        creative_formats = self._get_available_formats(tenant_id)

        # 3. Use AI to generate configuration
        config = await self._generate_product_configuration(
            description=description, inventory=inventory, creative_formats=creative_formats, adapter_type=adapter_type
        )

        return config

    async def _fetch_ad_server_inventory(self, tenant_id: str, adapter_type: str) -> AdServerInventory:
        """Fetch available inventory from ad server."""

        # Validate tenant_id to prevent injection
        import re

        if not tenant_id or not re.match(r"^[a-zA-Z0-9_-]+$", tenant_id) or len(tenant_id) > 100:
            logger.error(f"Invalid tenant_id format: {tenant_id}")
            return AdServerInventory(ad_units=[], targeting_keys=[], formats=[])

        # Get adapter configuration and principal
        with get_db_session() as db_session:
            # Get tenant ad server
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                logger.error(f"Tenant {tenant_id} not found")
                return AdServerInventory(ad_units=[], targeting_keys=[], formats=[])

            # Get a principal for this tenant (use first available)
            principal_model = db_session.query(PrincipalModel).filter_by(tenant_id=tenant_id).first()

            if not principal_model:
                # Create a temporary principal for inventory fetching
                from schemas import Principal

                principal = Principal(
                    principal_id="ai_config_temp",
                    name="AI Configuration Service",
                    access_token="ai_config_token",
                    platform_mappings={"mock": {"id": "system"}},  # Default mock mapping
                )
            else:
                from schemas import Principal

                mappings = principal_model.platform_mappings
                if isinstance(mappings, str):
                    try:
                        mappings = json.loads(mappings)
                        if not isinstance(mappings, dict):
                            logger.warning(
                                f"Invalid platform mappings for principal {principal_model.principal_id}: not a dict"
                            )
                            mappings = {}
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(
                            f"Failed to parse platform mappings for principal {principal_model.principal_id}: {e}"
                        )
                        mappings = {}
                principal = Principal(
                    principal_id=principal_model.principal_id,
                    name=principal_model.name,
                    access_token=principal_model.access_token,
                    platform_mappings=mappings,
                )

        # Get adapter instance
        from adapters import get_adapter_class
        from src.core.database.models import AdapterConfig

        adapter_class = get_adapter_class(adapter_type)

        # Get adapter config from adapter_config table
        with get_db_session() as db_session:
            adapter_config_row = db_session.query(AdapterConfig).filter_by(tenant_id=tenant_id).first()
            adapter_config = {}
            if adapter_config_row:
                # Build config from individual fields based on adapter type
                adapter_config = {"adapter_type": adapter_config_row.adapter_type, "enabled": True}

                if adapter_config_row.adapter_type == "mock":
                    adapter_config["dry_run"] = adapter_config_row.mock_dry_run or False

                elif adapter_config_row.adapter_type == "google_ad_manager":
                    adapter_config.update(
                        {
                            "network_code": adapter_config_row.gam_network_code,
                            "refresh_token": adapter_config_row.gam_refresh_token,
                            "company_id": adapter_config_row.gam_company_id,
                            "trafficker_id": adapter_config_row.gam_trafficker_id,
                            "manual_approval_required": adapter_config_row.gam_manual_approval_required or False,
                        }
                    )

                elif adapter_config_row.adapter_type == "kevel":
                    adapter_config.update(
                        {
                            "network_id": adapter_config_row.kevel_network_id,
                            "api_key": adapter_config_row.kevel_api_key,
                            "manual_approval_required": adapter_config_row.kevel_manual_approval_required or False,
                        }
                    )

                elif adapter_config_row.adapter_type == "triton":
                    adapter_config.update(
                        {
                            "station_id": adapter_config_row.triton_station_id,
                            "api_key": adapter_config_row.triton_api_key,
                        }
                    )

        # Create adapter instance
        adapter = adapter_class(
            config=adapter_config,
            principal=principal,
            dry_run=True,  # Always dry-run for inventory fetching
            tenant_id=tenant_id,
        )

        # Fetch inventory from adapter
        try:
            inventory_data = await adapter.get_available_inventory()
        except Exception as e:
            logger.error(f"Failed to fetch inventory from {adapter_type}: {e}")
            return AdServerInventory(ad_units=[], targeting_keys=[], formats=[])

        return AdServerInventory(
            placements=inventory_data.get("placements", []),
            ad_units=inventory_data.get("ad_units", []),
            targeting_options=inventory_data.get("targeting_options", {}),
            creative_specs=inventory_data.get("creative_specs", []),
            properties=inventory_data.get("properties", {}),
        )

    def _get_available_formats(self, tenant_id: str) -> list[dict[str, Any]]:
        """Get all available creative formats (standard + custom for tenant)."""
        from src.core.database.models import CreativeFormat

        with get_db_session() as db_session:
            from sqlalchemy import or_

            formats_query = (
                db_session.query(CreativeFormat)
                .filter(or_(CreativeFormat.tenant_id.is_(None), CreativeFormat.tenant_id == tenant_id))
                .order_by(CreativeFormat.is_standard.desc(), CreativeFormat.type, CreativeFormat.name)
            )

            formats = []
            for format_obj in formats_query:
                format_dict = {
                    "format_id": format_obj.format_id,
                    "name": format_obj.name,
                    "type": format_obj.type,
                    "description": format_obj.description,
                }

                # Add dimensions for display formats
                if format_obj.width and format_obj.height:
                    format_dict["dimensions"] = f"{format_obj.width}x{format_obj.height}"
                    format_dict["width"] = format_obj.width
                    format_dict["height"] = format_obj.height

                # Add duration for video/audio formats
                if format_obj.duration_seconds:
                    format_dict["duration"] = f"{format_obj.duration_seconds}s"
                    format_dict["duration_seconds"] = format_obj.duration_seconds

                formats.append(format_dict)

            return formats

    def _analyze_inventory_for_product(
        self, description: ProductDescription, inventory: AdServerInventory
    ) -> dict[str, Any]:
        """Analyze inventory to find best matches for product description."""
        analysis = {
            "matched_placements": [],
            "suggested_cpm_range": {"min": 0, "max": 0},
            "premium_level": "standard",
            "recommended_formats": [],
        }

        # Keywords that indicate premium inventory
        premium_keywords = ["premium", "homepage", "takeover", "above-fold", "hero", "spotlight"]
        standard_keywords = ["run-of-site", "ros", "standard", "general", "remnant"]

        description_text = (description.external_description + " " + (description.internal_details or "")).lower()

        # Determine premium level
        if any(keyword in description_text for keyword in premium_keywords):
            analysis["premium_level"] = "premium"
        elif any(keyword in description_text for keyword in standard_keywords):
            analysis["premium_level"] = "standard"

        # Match placements based on description
        cpm_values = []
        for placement in inventory.placements:
            placement_name = placement.get("name", "").lower()
            placement_path = placement.get("path", "").lower()

            # Score placement relevance
            score = 0
            if "homepage" in description_text and ("/" == placement_path or "homepage" in placement_name):
                score += 3
            if "article" in description_text and "article" in placement_path:
                score += 3
            if "mobile" in description_text and placement.get("device") == "mobile":
                score += 2
            if "video" in description_text and placement.get("format") == "video":
                score += 3
            if placement.get("position") == "above_fold" and analysis["premium_level"] == "premium":
                score += 2

            if score > 0:
                analysis["matched_placements"].append(
                    {"id": placement["id"], "score": score, "cpm": placement.get("typical_cpm", 5.0)}
                )
                if placement.get("typical_cpm"):
                    cpm_values.append(placement["typical_cpm"])

        # Sort by score and limit
        analysis["matched_placements"].sort(key=lambda x: x["score"], reverse=True)
        analysis["matched_placements"] = analysis["matched_placements"][:5]

        # Calculate CPM range
        if cpm_values:
            analysis["suggested_cpm_range"]["min"] = min(cpm_values) * 0.8
            analysis["suggested_cpm_range"]["max"] = max(cpm_values) * 1.2
        else:
            # Default ranges by premium level
            if analysis["premium_level"] == "premium":
                analysis["suggested_cpm_range"] = {"min": 15.0, "max": 50.0}
            else:
                analysis["suggested_cpm_range"] = {"min": 2.0, "max": 10.0}

        # Recommend formats based on matched placements
        format_sizes = set()
        for placement in analysis["matched_placements"]:
            placement_data = next((p for p in inventory.placements if p["id"] == placement["id"]), {})
            if "sizes" in placement_data:
                format_sizes.update(placement_data["sizes"])

        analysis["recommended_formats"] = list(format_sizes)

        return analysis

    async def _generate_product_configuration(
        self,
        description: ProductDescription,
        inventory: AdServerInventory,
        creative_formats: list[dict[str, Any]],
        adapter_type: str,
    ) -> dict[str, Any]:
        """Use AI to generate optimal product configuration."""

        # Analyze inventory first
        inventory_analysis = self._analyze_inventory_for_product(description, inventory)

        # Prepare context for AI (used in prompt generation below)

        prompt = f"""
        You are an expert ad operations specialist. Create an optimal product configuration
        based on the following information:

        Product Description:
        - Name: {description.name}
        - External (buyer-facing): {description.external_description}
        - Internal details: {description.internal_details or 'None provided'}

        Inventory Analysis Results:
        - Premium Level: {inventory_analysis['premium_level']}
        - Best Matching Placements: {json.dumps(inventory_analysis['matched_placements'][:3], indent=2)}
        - Suggested CPM Range: ${inventory_analysis['suggested_cpm_range']['min']:.2f} - ${inventory_analysis['suggested_cpm_range']['max']:.2f}
        - Recommended Ad Sizes: {inventory_analysis['recommended_formats']}

        Available Ad Server Inventory:
        {json.dumps(inventory.placements[:10], indent=2)}

        Available Targeting Options:
        {json.dumps(inventory.targeting_options, indent=2)}

        Creative Formats Available:
        {json.dumps([f for f in creative_formats if f['type'] in ['display', 'video', 'native']][:20], indent=2)}

        Generate a product configuration following these guidelines:
        1. Use the matched placements from the analysis as placement_targets
        2. Select creative formats that match the recommended sizes
        3. Set CPM within the suggested range (use single CPM for guaranteed, range for non-guaranteed)
        4. Choose targeting that aligns with the product description
        5. Include implementation details specific to {adapter_type}

        Rules:
        - For "premium" products: Use guaranteed delivery with higher CPM
        - For "standard" products: Use non_guaranteed with price guidance
        - Match format IDs exactly from the available creative formats list
        - Use placement IDs from the matched placements in targeting

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
        self, config: dict[str, Any], available_formats: list[dict[str, Any]]
    ) -> dict[str, Any]:
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
        self, description: ProductDescription, creative_formats: list[dict[str, Any]]
    ) -> dict[str, Any]:
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
                "device_targets": {"device_types": ["desktop", "mobile"]},
            },
            "implementation_config": {},
        }


# API endpoints for the admin UI
async def analyze_product_description(
    tenant_id: str, name: str, external_description: str, internal_details: str | None = None
) -> dict[str, Any]:
    """Analyze descriptions and return suggested configuration."""

    service = AIProductConfigurationService()

    # Get tenant's adapter type
    with get_db_session() as db_session:
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        adapter_type = tenant.ad_server

        if not adapter_type:
            raise ValueError("No enabled adapter found for tenant")

    description = ProductDescription(
        name=name, external_description=external_description, internal_details=internal_details
    )

    config = await service.create_product_from_description(
        tenant_id=tenant_id, description=description, adapter_type=adapter_type
    )

    return config
