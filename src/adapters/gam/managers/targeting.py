"""
GAM Targeting Manager

Handles targeting validation, translation from AdCP targeting to GAM targeting,
and geo mapping operations for Google Ad Manager campaigns.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class GAMTargetingManager:
    """Manages targeting operations for Google Ad Manager."""

    # Supported device types and their GAM numeric device category IDs
    # These are GAM's standard device category IDs that work across networks
    DEVICE_TYPE_MAP = {
        "mobile": 30000,  # Mobile devices
        "desktop": 30001,  # Desktop computers
        "tablet": 30002,  # Tablet devices
        "ctv": 30003,  # Connected TV / Streaming devices
        "dooh": 30004,  # Digital out-of-home / Set-top box
    }

    # Supported media types
    SUPPORTED_MEDIA_TYPES = {"video", "display", "native"}

    def __init__(self):
        """Initialize targeting manager."""
        self.geo_country_map = {}
        self.geo_region_map = {}
        self.geo_metro_map = {}
        self._load_geo_mappings()

    def _load_geo_mappings(self):
        """Load geo mappings from JSON file."""
        try:
            # Look for the geo mappings file relative to the adapters directory
            mapping_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gam_geo_mappings.json")
            with open(mapping_file) as f:
                geo_data = json.load(f)

            self.geo_country_map = geo_data.get("countries", {})
            self.geo_region_map = geo_data.get("regions", {})
            self.geo_metro_map = geo_data.get("metros", {}).get("US", {})  # Currently only US metros

            logger.info(
                f"Loaded GAM geo mappings: {len(self.geo_country_map)} countries, "
                f"{sum(len(v) for v in self.geo_region_map.values())} regions, "
                f"{len(self.geo_metro_map)} metros"
            )
        except Exception as e:
            logger.warning(f"Could not load geo mappings file: {e}")
            logger.warning("Using empty geo mappings - geo targeting will not work properly")
            self.geo_country_map = {}
            self.geo_region_map = {}
            self.geo_metro_map = {}

    def _lookup_region_id(self, region_code: str) -> str | None:
        """Look up region ID across all countries.

        Args:
            region_code: The region code to look up

        Returns:
            GAM region ID if found, None otherwise
        """
        # First check if we have country context (not implemented yet)
        # For now, search across all countries
        for _country, regions in self.geo_region_map.items():
            if region_code in regions:
                return regions[region_code]
        return None

    def validate_targeting(self, targeting_overlay) -> list[str]:
        """Validate targeting and return unsupported features.

        Args:
            targeting_overlay: AdCP targeting overlay object

        Returns:
            List of unsupported feature descriptions
        """
        unsupported = []

        if not targeting_overlay:
            return unsupported

        # Check device types
        if targeting_overlay.device_type_any_of:
            for device in targeting_overlay.device_type_any_of:
                if device not in self.DEVICE_TYPE_MAP:
                    unsupported.append(f"Device type '{device}' not supported")

        # Check media types
        if targeting_overlay.media_type_any_of:
            for media in targeting_overlay.media_type_any_of:
                if media not in self.SUPPORTED_MEDIA_TYPES:
                    unsupported.append(f"Media type '{media}' not supported")

        # Audio-specific targeting not supported
        if targeting_overlay.media_type_any_of and "audio" in targeting_overlay.media_type_any_of:
            unsupported.append("Audio media type not supported by Google Ad Manager")

        # City and postal targeting require GAM API lookups (not implemented)
        if targeting_overlay.geo_city_any_of or targeting_overlay.geo_city_none_of:
            unsupported.append("City targeting requires GAM geo service integration (not implemented)")
        if targeting_overlay.geo_zip_any_of or targeting_overlay.geo_zip_none_of:
            unsupported.append("Postal code targeting requires GAM geo service integration (not implemented)")

        # GAM supports all other standard targeting dimensions

        return unsupported

    def build_targeting(self, targeting_overlay) -> dict[str, Any]:
        """Build GAM targeting criteria from AdCP targeting.

        Args:
            targeting_overlay: AdCP targeting overlay object

        Returns:
            Dictionary containing GAM targeting configuration

        Raises:
            ValueError: If unsupported targeting is requested (no quiet failures)
        """
        if not targeting_overlay:
            return {}

        gam_targeting = {}

        # Geographic targeting
        geo_targeting = {}

        # Build targeted locations - only for supported geo features
        if any(
            [
                targeting_overlay.geo_country_any_of,
                targeting_overlay.geo_region_any_of,
                targeting_overlay.geo_metro_any_of,
            ]
        ):
            geo_targeting["targetedLocations"] = []

            # Map countries
            if targeting_overlay.geo_country_any_of:
                for country in targeting_overlay.geo_country_any_of:
                    if country in self.geo_country_map:
                        geo_targeting["targetedLocations"].append({"id": self.geo_country_map[country]})
                    else:
                        logger.warning(f"Country code '{country}' not in GAM mapping")

            # Map regions
            if targeting_overlay.geo_region_any_of:
                for region in targeting_overlay.geo_region_any_of:
                    region_id = self._lookup_region_id(region)
                    if region_id:
                        geo_targeting["targetedLocations"].append({"id": region_id})
                    else:
                        logger.warning(f"Region code '{region}' not in GAM mapping")

            # Map metros (DMAs)
            if targeting_overlay.geo_metro_any_of:
                for metro in targeting_overlay.geo_metro_any_of:
                    if metro in self.geo_metro_map:
                        geo_targeting["targetedLocations"].append({"id": self.geo_metro_map[metro]})
                    else:
                        logger.warning(f"Metro code '{metro}' not in GAM mapping")

        # City and postal code targeting not supported - fail loudly
        if targeting_overlay.geo_city_any_of:
            raise ValueError(
                f"City targeting requested but not supported. "
                f"Cannot fulfill buyer contract for cities: {targeting_overlay.geo_city_any_of}. "
                f"Use geo_metro_any_of for metropolitan area targeting instead."
            )
        if targeting_overlay.geo_zip_any_of:
            raise ValueError(
                f"Postal code targeting requested but not supported. "
                f"Cannot fulfill buyer contract for postal codes: {targeting_overlay.geo_zip_any_of}. "
                f"Use geo_metro_any_of for metropolitan area targeting instead."
            )

        # Build excluded locations - only for supported geo features
        if any(
            [
                targeting_overlay.geo_country_none_of,
                targeting_overlay.geo_region_none_of,
                targeting_overlay.geo_metro_none_of,
            ]
        ):
            geo_targeting["excludedLocations"] = []

            # Map excluded countries
            if targeting_overlay.geo_country_none_of:
                for country in targeting_overlay.geo_country_none_of:
                    if country in self.geo_country_map:
                        geo_targeting["excludedLocations"].append({"id": self.geo_country_map[country]})

            # Map excluded regions
            if targeting_overlay.geo_region_none_of:
                for region in targeting_overlay.geo_region_none_of:
                    region_id = self._lookup_region_id(region)
                    if region_id:
                        geo_targeting["excludedLocations"].append({"id": region_id})

            # Map excluded metros
            if targeting_overlay.geo_metro_none_of:
                for metro in targeting_overlay.geo_metro_none_of:
                    if metro in self.geo_metro_map:
                        geo_targeting["excludedLocations"].append({"id": self.geo_metro_map[metro]})

        # City and postal code exclusions not supported - fail loudly
        if targeting_overlay.geo_city_none_of:
            raise ValueError(
                f"City exclusion requested but not supported. "
                f"Cannot fulfill buyer contract for excluded cities: {targeting_overlay.geo_city_none_of}."
            )
        if targeting_overlay.geo_zip_none_of:
            raise ValueError(
                f"Postal code exclusion requested but not supported. "
                f"Cannot fulfill buyer contract for excluded postal codes: {targeting_overlay.geo_zip_none_of}."
            )

        if geo_targeting:
            gam_targeting["geoTargeting"] = geo_targeting

        # Technology/Device targeting - NOT SUPPORTED, MUST FAIL LOUDLY
        if targeting_overlay.device_type_any_of:
            raise ValueError(
                f"Device targeting requested but not supported. "
                f"Cannot fulfill buyer contract for device types: {targeting_overlay.device_type_any_of}."
            )

        if targeting_overlay.os_any_of:
            raise ValueError(
                f"OS targeting requested but not supported. "
                f"Cannot fulfill buyer contract for OS types: {targeting_overlay.os_any_of}."
            )

        if targeting_overlay.browser_any_of:
            raise ValueError(
                f"Browser targeting requested but not supported. "
                f"Cannot fulfill buyer contract for browsers: {targeting_overlay.browser_any_of}."
            )

        # Content targeting - NOT SUPPORTED, MUST FAIL LOUDLY
        if targeting_overlay.content_cat_any_of:
            raise ValueError(
                f"Content category targeting requested but not supported. "
                f"Cannot fulfill buyer contract for categories: {targeting_overlay.content_cat_any_of}."
            )

        if targeting_overlay.keywords_any_of:
            raise ValueError(
                f"Keyword targeting requested but not supported. "
                f"Cannot fulfill buyer contract for keywords: {targeting_overlay.keywords_any_of}."
            )

        # Custom key-value targeting
        custom_targeting = {}

        # Platform-specific custom targeting
        if targeting_overlay.custom and "gam" in targeting_overlay.custom:
            custom_targeting.update(targeting_overlay.custom["gam"].get("key_values", {}))

        # AEE signal integration via key-value pairs (managed-only)
        if targeting_overlay.key_value_pairs:
            logger.info("Adding AEE signals to GAM key-value targeting")
            for key, value in targeting_overlay.key_value_pairs.items():
                custom_targeting[key] = value
                logger.info(f"  {key}: {value}")

        if custom_targeting:
            gam_targeting["customTargeting"] = custom_targeting

        # Audience segment targeting
        # Map AdCP audiences_any_of and signals to GAM audience segment IDs
        if targeting_overlay.audiences_any_of or targeting_overlay.signals:
            # Note: This requires GAM audience segment ID mapping configured per tenant
            # For now, we fail loudly to indicate it's not fully implemented
            audience_list = []
            if targeting_overlay.audiences_any_of:
                audience_list.extend(targeting_overlay.audiences_any_of)
            if targeting_overlay.signals:
                audience_list.extend(targeting_overlay.signals)

            raise ValueError(
                f"Audience/signal targeting requested but GAM audience segment mapping not configured. "
                f"Cannot fulfill buyer contract for: {', '.join(audience_list)}. "
                f"Configure audience segment ID mappings in tenant adapter config to support this targeting."
            )

        # Media type targeting - map to GAM environmentType
        # This should be set on line items, not in targeting dict
        # We'll store it for the line item creation logic to use
        if targeting_overlay.media_type_any_of:
            # Validate only one media type (GAM line items have single environmentType)
            if len(targeting_overlay.media_type_any_of) > 1:
                raise ValueError(
                    f"Multiple media types requested but GAM supports only one environmentType per line item. "
                    f"Requested: {targeting_overlay.media_type_any_of}. "
                    f"Create separate packages for each media type."
                )

            media_type = targeting_overlay.media_type_any_of[0]
            # Map AdCP media types to GAM environmentType
            media_type_map = {
                "video": "VIDEO_PLAYER",
                "display": "BROWSER",
                "native": "BROWSER",
                # audio and dooh not directly supported by GAM
            }

            if media_type in media_type_map:
                # Store for line item creation - will be picked up by orders manager
                gam_targeting["_media_type_environment"] = media_type_map[media_type]
                logger.info(f"Media type '{media_type}' mapped to GAM environmentType: {media_type_map[media_type]}")
            else:
                raise ValueError(
                    f"Media type '{media_type}' is not supported in GAM. "
                    f"Supported types: {', '.join(media_type_map.keys())}"
                )

        logger.info(f"Applying GAM targeting: {list(gam_targeting.keys())}")
        return gam_targeting

    def add_inventory_targeting(
        self,
        targeting: dict[str, Any],
        targeted_ad_unit_ids: list[str] | None = None,
        targeted_placement_ids: list[str] | None = None,
        include_descendants: bool = True,
    ) -> dict[str, Any]:
        """Add inventory targeting to GAM targeting configuration.

        Args:
            targeting: Existing GAM targeting configuration
            targeted_ad_unit_ids: Optional list of ad unit IDs to target
            targeted_placement_ids: Optional list of placement IDs to target
            include_descendants: Whether to include descendant ad units

        Returns:
            Updated targeting configuration with inventory targeting
        """
        inventory_targeting = {}

        if targeted_ad_unit_ids:
            inventory_targeting["targetedAdUnits"] = [
                {"adUnitId": ad_unit_id, "includeDescendants": include_descendants}
                for ad_unit_id in targeted_ad_unit_ids
            ]

        if targeted_placement_ids:
            inventory_targeting["targetedPlacements"] = [
                {"placementId": placement_id} for placement_id in targeted_placement_ids
            ]

        if inventory_targeting:
            targeting["inventoryTargeting"] = inventory_targeting

        return targeting

    def add_custom_targeting(self, targeting: dict[str, Any], custom_keys: dict[str, Any]) -> dict[str, Any]:
        """Add custom targeting keys to GAM targeting configuration.

        Args:
            targeting: Existing GAM targeting configuration
            custom_keys: Dictionary of custom targeting key-value pairs

        Returns:
            Updated targeting configuration with custom targeting
        """
        if custom_keys:
            if "customTargeting" not in targeting:
                targeting["customTargeting"] = {}
            targeting["customTargeting"].update(custom_keys)

        return targeting
