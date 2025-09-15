"""
GAM Creatives Manager

Handles creative validation, creation, upload, and association with line items
for Google Ad Manager campaigns.
"""

import base64
import logging
import random
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from src.core.schemas import AssetStatus

from ..utils.validation import GAMValidator

logger = logging.getLogger(__name__)


class GAMCreativesManager:
    """Manages creative operations for Google Ad Manager."""

    def __init__(self, client_manager, advertiser_id: str, dry_run: bool = False):
        """Initialize creatives manager.

        Args:
            client_manager: GAMClientManager instance
            advertiser_id: GAM advertiser ID
            dry_run: Whether to run in dry-run mode
        """
        self.client_manager = client_manager
        self.advertiser_id = advertiser_id
        self.dry_run = dry_run
        self.validator = GAMValidator()

    def add_creative_assets(
        self, media_buy_id: str, assets: list[dict[str, Any]], today: datetime
    ) -> list[AssetStatus]:
        """Creates new Creatives in GAM and associates them with LineItems.

        Args:
            media_buy_id: GAM order ID
            assets: List of creative asset dictionaries
            today: Current datetime

        Returns:
            List of AssetStatus objects indicating success/failure for each creative
        """
        logger.info(f"Adding {len(assets)} creative assets for order '{media_buy_id}'")

        if not self.dry_run:
            creative_service = self.client_manager.get_service("CreativeService")
            lica_service = self.client_manager.get_service("LineItemCreativeAssociationService")
            line_item_service = self.client_manager.get_service("LineItemService")

        created_asset_statuses = []

        # Get line item mapping and creative placeholders
        line_item_map, creative_placeholders = self._get_line_item_info(
            media_buy_id, line_item_service if not self.dry_run else None
        )

        for asset in assets:
            # Validate creative asset against GAM requirements
            validation_issues = self._validate_creative_for_gam(asset)

            # Add creative size validation against placeholders
            size_validation_issues = self._validate_creative_size_against_placeholders(asset, creative_placeholders)
            validation_issues.extend(size_validation_issues)

            if validation_issues:
                logger.error(f"Creative {asset['creative_id']} failed GAM validation:")
                for issue in validation_issues:
                    logger.error(f"  - {issue}")
                created_asset_statuses.append(AssetStatus(creative_id=asset["creative_id"], status="failed"))
                continue

            # Determine creative type using AdCP v1.3+ logic
            creative_type = self._get_creative_type(asset)

            if creative_type == "vast":
                # VAST is handled at line item level, not creative level
                logger.info(f"VAST creative {asset['creative_id']} - configuring at line item level")
                self._configure_vast_for_line_items(media_buy_id, asset, line_item_map)
                created_asset_statuses.append(AssetStatus(creative_id=asset["creative_id"], status="approved"))
                continue

            # Get placeholders for this asset's package assignments
            asset_placeholders = []
            for pkg_id in asset.get("package_assignments", []):
                if pkg_id in creative_placeholders:
                    asset_placeholders.extend(creative_placeholders[pkg_id])

            # Create GAM creative object
            try:
                creative = self._create_gam_creative(asset, creative_type, asset_placeholders)
                if not creative:
                    logger.warning(f"Skipping unsupported creative {asset['creative_id']} with type: {creative_type}")
                    created_asset_statuses.append(AssetStatus(creative_id=asset["creative_id"], status="failed"))
                    continue

                # Create the creative in GAM
                if self.dry_run:
                    logger.info(f"Would call: creative_service.createCreatives([{creative.get('name', 'unnamed')}])")
                    gam_creative_id = f"mock_creative_{random.randint(100000, 999999)}"
                else:
                    created_creatives = creative_service.createCreatives([creative])
                    if not created_creatives:
                        logger.error(f"Failed to create creative {asset['creative_id']} - no creatives returned")
                        created_asset_statuses.append(AssetStatus(creative_id=asset["creative_id"], status="failed"))
                        continue

                    gam_creative_id = created_creatives[0]["id"]
                    logger.info(f"✓ Created GAM Creative ID: {gam_creative_id}")

                # Associate creative with line items
                self._associate_creative_with_line_items(
                    gam_creative_id, asset, line_item_map, lica_service if not self.dry_run else None
                )

                created_asset_statuses.append(AssetStatus(creative_id=asset["creative_id"], status="approved"))

            except Exception as e:
                logger.error(f"Error creating creative {asset['creative_id']}: {str(e)}")
                created_asset_statuses.append(AssetStatus(creative_id=asset["creative_id"], status="failed"))

        return created_asset_statuses

    def _get_line_item_info(self, media_buy_id: str, line_item_service) -> tuple[dict[str, str], dict[str, list]]:
        """Get line item mapping and creative placeholders for an order.

        Args:
            media_buy_id: GAM order ID
            line_item_service: GAM LineItemService (None for dry run)

        Returns:
            Tuple of (line_item_map, creative_placeholders)
        """
        if not self.dry_run and line_item_service:
            statement = (
                self.client_manager.get_statement_builder()
                .where("orderId = :orderId")
                .with_bind_variable("orderId", int(media_buy_id))
            )
            response = line_item_service.getLineItemsByStatement(statement.ToStatement())
            line_items = response.get("results", [])
            line_item_map = {item["name"]: item["id"] for item in line_items}

            # Collect all creative placeholders from line items for size validation
            creative_placeholders = {}
            for line_item in line_items:
                package_name = line_item["name"]
                placeholders = line_item.get("creativePlaceholders", [])
                creative_placeholders[package_name] = placeholders
        else:
            # In dry-run mode, create a mock line item map and placeholders
            line_item_map = {"mock_package": "mock_line_item_123"}
            creative_placeholders = {
                "mock_package": [
                    {"size": {"width": 300, "height": 250}, "creativeSizeType": "PIXEL"},
                    {"size": {"width": 728, "height": 90}, "creativeSizeType": "PIXEL"},
                ]
            }

        return line_item_map, creative_placeholders

    def _get_creative_type(self, asset: dict[str, Any]) -> str:
        """Determine the creative type based on AdCP v1.3+ fields.

        Args:
            asset: Creative asset dictionary

        Returns:
            Creative type string
        """
        # Check AdCP v1.3+ fields first
        if asset.get("snippet") and asset.get("snippet_type"):
            if asset["snippet_type"] in ["vast_xml", "vast_url"]:
                return "vast"
            else:
                return "third_party_tag"
        elif asset.get("template_variables"):
            return "native"
        elif asset.get("media_url") or asset.get("media_data"):
            # Check if HTML5 based on file extension or format
            media_url = asset.get("media_url", "")
            format_str = asset.get("format", "")
            if (
                media_url.lower().endswith((".html", ".htm", ".html5", ".zip"))
                or "html5" in format_str.lower()
                or "rich_media" in format_str.lower()
            ):
                return "html5"
            else:
                return "hosted_asset"
        else:
            # Auto-detect from legacy patterns for backward compatibility
            url = asset.get("url", "")
            format_str = asset.get("format", "")

            if self._is_html_snippet(url):
                return "third_party_tag"
            elif "native" in format_str:
                return "native"
            elif url and (".xml" in url.lower() or "vast" in url.lower()):
                return "vast"
            elif (
                url.lower().endswith((".html", ".htm", ".html5", ".zip"))
                or "html5" in format_str.lower()
                or "rich_media" in format_str.lower()
            ):
                return "html5"
            else:
                return "hosted_asset"  # Default

    def _validate_creative_for_gam(self, asset: dict[str, Any]) -> list[str]:
        """Validate creative asset against GAM requirements before API submission.

        Args:
            asset: Creative asset dictionary

        Returns:
            List of validation error messages (empty if valid)
        """
        return self.validator.validate_creative_asset(asset)

    def _validate_creative_size_against_placeholders(
        self, asset: dict[str, Any], creative_placeholders: dict[str, list]
    ) -> list[str]:
        """Validate that creative format and asset requirements match available LineItem placeholders.

        Args:
            asset: Creative asset dictionary
            creative_placeholders: Dictionary mapping package names to placeholder lists

        Returns:
            List of validation error messages
        """
        validation_errors = []

        # Get asset dimensions
        try:
            asset_width, asset_height = self._get_creative_dimensions(asset, None)
        except Exception as e:
            validation_errors.append(f"Could not determine creative dimensions: {str(e)}")
            return validation_errors

        # Check if asset dimensions match any placeholder in its assigned packages
        package_assignments = asset.get("package_assignments", [])
        if not package_assignments:
            logger.warning(f"Creative {asset.get('creative_id', 'unknown')} has no package assignments")
            return validation_errors

        matching_placeholders_found = False
        for package_id in package_assignments:
            placeholders = creative_placeholders.get(package_id, [])
            for placeholder in placeholders:
                placeholder_size = placeholder.get("size", {})
                placeholder_width = placeholder_size.get("width", 0)
                placeholder_height = placeholder_size.get("height", 0)

                if asset_width == placeholder_width and asset_height == placeholder_height:
                    matching_placeholders_found = True
                    break

            if matching_placeholders_found:
                break

        if not matching_placeholders_found:
            available_sizes = []
            for package_id in package_assignments:
                placeholders = creative_placeholders.get(package_id, [])
                for placeholder in placeholders:
                    size = placeholder.get("size", {})
                    if size:
                        available_sizes.append(f"{size.get('width', 0)}x{size.get('height', 0)}")

            validation_errors.append(
                f"Creative size {asset_width}x{asset_height} does not match any LineItem placeholders. "
                f"Available sizes in assigned packages: {', '.join(set(available_sizes))}"
            )

        return validation_errors

    def _create_gam_creative(
        self, asset: dict[str, Any], creative_type: str, placeholders: list[dict] = None
    ) -> dict[str, Any] | None:
        """Create a GAM creative object based on the asset type.

        Args:
            asset: Creative asset dictionary
            creative_type: Type of creative to create
            placeholders: List of creative placeholders for validation

        Returns:
            GAM creative dictionary or None if unsupported
        """
        if creative_type == "third_party_tag":
            return self._create_third_party_creative(asset)
        elif creative_type == "native":
            return self._create_native_creative(asset)
        elif creative_type == "html5":
            return self._create_html5_creative(asset)
        elif creative_type == "hosted_asset":
            return self._create_hosted_asset_creative(asset)
        else:
            logger.warning(f"Unsupported creative type: {creative_type}")
            return None

    def _create_third_party_creative(self, asset: dict[str, Any]) -> dict[str, Any]:
        """Create a third-party creative for GAM."""
        width, height = self._get_creative_dimensions(asset)

        # Use snippet if available (AdCP v1.3+), otherwise fall back to URL
        snippet = asset.get("snippet")
        if not snippet:
            snippet = asset.get("url", "")

        creative = {
            "xsi_type": "ThirdPartyCreative",
            "name": asset.get("name", f"AdCP Creative {asset.get('creative_id', 'unknown')}"),
            "advertiserId": self.advertiser_id,
            "size": {"width": width, "height": height},
            "snippet": snippet,
        }

        self._add_tracking_urls_to_creative(creative, asset)
        return creative

    def _create_native_creative(self, asset: dict[str, Any]) -> dict[str, Any]:
        """Create a native creative for GAM."""
        template_id = self._get_native_template_id(asset)
        template_variables = self._build_native_template_variables(asset)

        creative = {
            "xsi_type": "TemplateCreative",
            "name": asset.get("name", f"AdCP Native Creative {asset.get('creative_id', 'unknown')}"),
            "advertiserId": self.advertiser_id,
            "creativeTemplateId": template_id,
            "creativeTemplateVariableValues": template_variables,
        }

        return creative

    def _create_html5_creative(self, asset: dict[str, Any]) -> dict[str, Any]:
        """Create an HTML5 creative for GAM."""
        width, height = self._get_creative_dimensions(asset)
        html_source = self._get_html5_source(asset)

        creative = {
            "xsi_type": "CustomCreative",
            "name": asset.get("name", f"AdCP HTML5 Creative {asset.get('creative_id', 'unknown')}"),
            "advertiserId": self.advertiser_id,
            "size": {"width": width, "height": height},
            "htmlSnippet": html_source,
        }

        self._add_tracking_urls_to_creative(creative, asset)
        return creative

    def _create_hosted_asset_creative(self, asset: dict[str, Any]) -> dict[str, Any]:
        """Create a hosted asset (image/video) creative for GAM."""
        width, height = self._get_creative_dimensions(asset)

        # Upload the binary asset to GAM
        uploaded_asset = self._upload_binary_asset(asset)
        if not uploaded_asset:
            raise Exception("Failed to upload binary asset")

        # Determine asset type
        asset_type = self._determine_asset_type(asset)

        if asset_type == "image":
            creative = {
                "xsi_type": "ImageCreative",
                "name": asset.get("name", f"AdCP Image Creative {asset.get('creative_id', 'unknown')}"),
                "advertiserId": self.advertiser_id,
                "size": {"width": width, "height": height},
                "primaryImageAsset": uploaded_asset,
            }
        elif asset_type == "video":
            creative = {
                "xsi_type": "VideoCreative",
                "name": asset.get("name", f"AdCP Video Creative {asset.get('creative_id', 'unknown')}"),
                "advertiserId": self.advertiser_id,
                "size": {"width": width, "height": height},
                "videoAsset": uploaded_asset,
            }
        else:
            raise Exception(f"Unsupported asset type: {asset_type}")

        self._add_tracking_urls_to_creative(creative, asset)
        return creative

    def _get_creative_dimensions(self, asset: dict[str, Any], placeholders: list[dict] = None) -> tuple[int, int]:
        """Get creative dimensions from asset or format.

        Args:
            asset: Creative asset dictionary
            placeholders: Optional list of placeholders for validation

        Returns:
            Tuple of (width, height)
        """
        # Try explicit width/height first
        if asset.get("width") and asset.get("height"):
            return int(asset["width"]), int(asset["height"])

        # Try to parse from format string
        format_str = asset.get("format", "")
        if format_str:
            # Extract dimensions from format like "display_300x250"
            parts = format_str.lower().split("_")
            for part in parts:
                if "x" in part:
                    try:
                        width_str, height_str = part.split("x")
                        return int(width_str), int(height_str)
                    except (ValueError, IndexError):
                        continue

        # Default fallback
        logger.warning(
            f"Could not determine dimensions for creative {asset.get('creative_id', 'unknown')}, using 300x250 default"
        )
        return 300, 250

    def _is_html_snippet(self, content: str) -> bool:
        """Check if content appears to be an HTML snippet."""
        if not content:
            return False
        content_lower = content.lower().strip()
        return any(
            [
                content_lower.startswith("<script"),
                content_lower.startswith("<div"),
                content_lower.startswith("<iframe"),
                content_lower.startswith("<!doctype"),
                content_lower.startswith("<html"),
            ]
        )

    def _get_html5_source(self, asset: dict[str, Any]) -> str:
        """Get HTML5 source content for the creative."""
        # Try media_data first (direct HTML content)
        if asset.get("media_data"):
            try:
                # Decode base64 if needed
                content = asset["media_data"]
                if content.startswith("data:"):
                    # Extract base64 part after comma
                    content = content.split(",", 1)[1]
                    content = base64.b64decode(content).decode("utf-8")
                return content
            except Exception as e:
                logger.warning(f"Failed to decode media_data: {e}")

        # Fall back to media_url
        if asset.get("media_url"):
            return f'<iframe src="{asset["media_url"]}" width="100%" height="100%" frameborder="0"></iframe>'

        # Last resort: use URL field
        url = asset.get("url", "")
        if url:
            return f'<iframe src="{url}" width="100%" height="100%" frameborder="0"></iframe>'

        raise Exception("No HTML5 source content found in asset")

    def _upload_binary_asset(self, asset: dict[str, Any]) -> dict[str, Any] | None:
        """Upload binary asset to GAM and return asset info."""
        if self.dry_run:
            logger.info("Would upload binary asset to GAM")
            return {
                "assetId": f"mock_asset_{random.randint(100000, 999999)}",
                "fileName": asset.get("name", "mock_asset.jpg"),
                "fileSize": 12345,
                "mimeType": self._get_content_type(asset),
            }

        # Implementation would handle actual upload to GAM
        # This is a simplified version
        logger.warning("Binary asset upload not fully implemented")
        return None

    def _get_content_type(self, asset: dict[str, Any]) -> str:
        """Determine content type from asset."""
        # Check explicit mime type
        if asset.get("mime_type"):
            return asset["mime_type"]

        # Guess from URL extension
        url = asset.get("media_url") or asset.get("url", "")
        if url:
            parsed = urlparse(url)
            path = parsed.path.lower()
            if path.endswith((".jpg", ".jpeg")):
                return "image/jpeg"
            elif path.endswith(".png"):
                return "image/png"
            elif path.endswith(".gif"):
                return "image/gif"
            elif path.endswith((".mp4", ".mov")):
                return "video/mp4"

        # Default
        return "image/jpeg"

    def _determine_asset_type(self, asset: dict[str, Any]) -> str:
        """Determine if asset is image or video."""
        content_type = self._get_content_type(asset)
        if content_type.startswith("video/"):
            return "video"
        else:
            return "image"

    def _get_native_template_id(self, asset: dict[str, Any]) -> str:
        """Get the GAM native template ID for the asset."""
        # This would need to be configured per network
        return "123456"  # Placeholder

    def _build_native_template_variables(self, asset: dict[str, Any]) -> list[dict[str, Any]]:
        """Build native template variables from asset."""
        variables = []
        template_vars = asset.get("template_variables", {})

        for key, value in template_vars.items():
            variables.append(
                {
                    "uniqueName": key,
                    "value": {
                        "xsi_type": "StringCreativeTemplateVariableValue",
                        "value": str(value),
                    },
                }
            )

        return variables

    def _add_tracking_urls_to_creative(self, creative: dict[str, Any], asset: dict[str, Any]) -> None:
        """Add tracking URLs to the creative if available."""
        tracking_events = asset.get("tracking_events", {})

        # Add impression tracking
        if tracking_events.get("impression"):
            creative["trackingUrls"] = [{"url": url} for url in tracking_events["impression"]]

        # Add click tracking (for supported creative types)
        if tracking_events.get("click") and creative.get("xsi_type") in ["ImageCreative", "ThirdPartyCreative"]:
            creative["destinationUrl"] = tracking_events["click"][0]  # Use first click URL

    def _configure_vast_for_line_items(
        self, media_buy_id: str, asset: dict[str, Any], line_item_map: dict[str, str]
    ) -> None:
        """Configure VAST creative at line item level."""
        if self.dry_run:
            logger.info(f"Would configure VAST for line items in order {media_buy_id}")
            return

        # VAST configuration would be implemented here
        logger.info(f"Configuring VAST creative {asset['creative_id']} for line items")

    def _associate_creative_with_line_items(
        self, gam_creative_id: str, asset: dict[str, Any], line_item_map: dict[str, str], lica_service
    ) -> None:
        """Associate creative with its assigned line items."""
        package_assignments = asset.get("package_assignments", [])

        for package_id in package_assignments:
            line_item_id = line_item_map.get(package_id)
            if not line_item_id:
                logger.warning(f"Line item not found for package {package_id}")
                continue

            if self.dry_run:
                logger.info(f"Would associate creative {gam_creative_id} with line item {line_item_id}")
            else:
                # Create Line Item Creative Association
                association = {
                    "creativeId": gam_creative_id,
                    "lineItemId": line_item_id,
                }

                try:
                    lica_service.createLineItemCreativeAssociations([association])
                    logger.info(f"✓ Associated creative {gam_creative_id} with line item {line_item_id}")
                except Exception as e:
                    logger.error(f"Failed to associate creative {gam_creative_id} with line item {line_item_id}: {e}")
                    raise
