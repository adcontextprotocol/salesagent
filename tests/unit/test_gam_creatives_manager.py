"""
Unit tests for GAMCreativesManager class.

Tests creative validation, creation, upload, association with line items,
and various creative types (third-party, native, HTML5, hosted assets, VAST).
"""

import base64
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.adapters.gam.managers.creatives import GAMCreativesManager


class TestGAMCreativesManager:
    """Test suite for GAMCreativesManager creative lifecycle management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock()
        self.advertiser_id = "123456789"
        self.mock_validator = Mock()

        # Create manager instance
        self.creatives_manager = GAMCreativesManager(self.mock_client_manager, self.advertiser_id, dry_run=False)

        # Replace validator with mock
        self.creatives_manager.validator = self.mock_validator

    def test_init_with_valid_parameters(self):
        """Test initialization with valid parameters."""
        creatives_manager = GAMCreativesManager(self.mock_client_manager, self.advertiser_id, dry_run=True)

        assert creatives_manager.client_manager == self.mock_client_manager
        assert creatives_manager.advertiser_id == self.advertiser_id
        assert creatives_manager.dry_run is True

    def test_get_creative_type_third_party_tag(self):
        """Test creative type detection for third-party tags."""
        # AdCP v1.3+ format
        asset = {"snippet": "<script>console.log('test');</script>", "snippet_type": "javascript"}

        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "third_party_tag"

        # VAST format
        asset = {"snippet": "<VAST>...</VAST>", "snippet_type": "vast_xml"}

        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "vast"

    def test_get_creative_type_native(self):
        """Test creative type detection for native creatives."""
        asset = {"template_variables": {"headline": "Test Ad", "image_url": "https://example.com/img.jpg"}}

        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "native"

    def test_get_creative_type_hosted_asset(self):
        """Test creative type detection for hosted assets."""
        # Media URL
        asset = {"media_url": "https://example.com/banner.jpg"}
        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "hosted_asset"

        # Media data
        asset = {"media_data": base64.b64encode(b"image data").decode()}
        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "hosted_asset"

    def test_get_creative_type_html5(self):
        """Test creative type detection for HTML5 creatives."""
        # By URL extension
        asset = {"media_url": "https://example.com/creative.html"}
        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "html5"

        # By format
        asset = {"url": "https://example.com/creative", "format": "html5_interactive"}
        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "html5"

    def test_get_creative_type_legacy_detection(self):
        """Test legacy creative type detection patterns."""
        # HTML snippet detection
        asset = {"url": "<script>alert('test');</script>"}
        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "third_party_tag"

        # VAST by URL
        asset = {"url": "https://example.com/vast.xml"}
        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "vast"

        # Default to hosted asset
        asset = {"url": "https://example.com/banner.jpg"}
        creative_type = self.creatives_manager._get_creative_type(asset)
        assert creative_type == "hosted_asset"

    def test_is_html_snippet_detection(self):
        """Test HTML snippet detection helper method."""
        html_snippets = [
            "<script>test</script>",
            "<div>content</div>",
            "<iframe src='test'></iframe>",
            "<!DOCTYPE html>",
            "<html><body></body></html>",
        ]

        for snippet in html_snippets:
            assert self.creatives_manager._is_html_snippet(snippet) is True

        non_html = ["https://example.com/image.jpg", "plain text content", "", None]

        for content in non_html:
            assert self.creatives_manager._is_html_snippet(content) is False

    def test_get_creative_dimensions_explicit_values(self):
        """Test creative dimension extraction from explicit width/height."""
        asset = {"width": 728, "height": 90, "format": "display_300x250"}  # Should be overridden by explicit values

        width, height = self.creatives_manager._get_creative_dimensions(asset)
        assert width == 728
        assert height == 90

    def test_get_creative_dimensions_from_format(self):
        """Test creative dimension extraction from format string."""
        asset = {"format": "display_300x250"}

        width, height = self.creatives_manager._get_creative_dimensions(asset)
        assert width == 300
        assert height == 250

    def test_get_creative_dimensions_format_parsing(self):
        """Test format string parsing for dimensions."""
        test_cases = [
            ("display_728x90", (728, 90)),
            ("native_320x50", (320, 50)),
            ("video_1920x1080", (1920, 1080)),
            ("custom_format_970x250", (970, 250)),
        ]

        for format_str, expected_dims in test_cases:
            asset = {"format": format_str}
            width, height = self.creatives_manager._get_creative_dimensions(asset)
            assert (width, height) == expected_dims

    def test_get_creative_dimensions_fallback(self):
        """Test creative dimension fallback to default values."""
        asset = {"creative_id": "test"}  # No width, height, or parseable format

        width, height = self.creatives_manager._get_creative_dimensions(asset)
        assert width == 300
        assert height == 250

    def test_create_third_party_creative(self):
        """Test third-party creative creation."""
        asset = {
            "creative_id": "test_creative",
            "name": "Test Third Party Creative",
            "snippet": "<script>console.log('test');</script>",
            "width": 728,
            "height": 90,
            "tracking_events": {"impression": ["https://track1.com", "https://track2.com"]},
        }

        creative = self.creatives_manager._create_third_party_creative(asset)

        assert creative["xsi_type"] == "ThirdPartyCreative"
        assert creative["name"] == "Test Third Party Creative"
        assert creative["advertiserId"] == self.advertiser_id
        assert creative["size"] == {"width": 728, "height": 90}
        assert creative["snippet"] == "<script>console.log('test');</script>"
        assert "trackingUrls" in creative

    def test_create_third_party_creative_fallback_to_url(self):
        """Test third-party creative creation falling back to URL when snippet missing."""
        asset = {"creative_id": "test_creative", "url": "https://example.com/tag.js", "width": 300, "height": 250}

        creative = self.creatives_manager._create_third_party_creative(asset)

        assert creative["snippet"] == "https://example.com/tag.js"

    def test_create_native_creative(self):
        """Test native creative creation."""
        asset = {
            "creative_id": "test_native",
            "name": "Test Native Creative",
            "template_variables": {
                "headline": "Great Product",
                "image_url": "https://example.com/img.jpg",
                "description": "Amazing product description",
            },
        }

        with (
            patch.object(self.creatives_manager, "_get_native_template_id") as mock_template_id,
            patch.object(self.creatives_manager, "_build_native_template_variables") as mock_build_vars,
        ):

            mock_template_id.return_value = "template_123"
            mock_build_vars.return_value = [
                {
                    "uniqueName": "headline",
                    "value": {"xsi_type": "StringCreativeTemplateVariableValue", "value": "Great Product"},
                }
            ]

            creative = self.creatives_manager._create_native_creative(asset)

            assert creative["xsi_type"] == "TemplateCreative"
            assert creative["name"] == "Test Native Creative"
            assert creative["advertiserId"] == self.advertiser_id
            assert creative["creativeTemplateId"] == "template_123"
            assert creative["creativeTemplateVariableValues"] == mock_build_vars.return_value

    def test_create_html5_creative(self):
        """Test HTML5 creative creation."""
        asset = {
            "creative_id": "test_html5",
            "name": "Test HTML5 Creative",
            "media_data": "data:text/html;base64,"
            + base64.b64encode(b"<html><body>Rich content</body></html>").decode(),
            "width": 970,
            "height": 250,
            "tracking_events": {"impression": ["https://track.com"]},
        }

        with patch.object(self.creatives_manager, "_get_html5_source") as mock_get_source:
            mock_get_source.return_value = "<html><body>Rich content</body></html>"

            creative = self.creatives_manager._create_html5_creative(asset)

            assert creative["xsi_type"] == "CustomCreative"
            assert creative["name"] == "Test HTML5 Creative"
            assert creative["advertiserId"] == self.advertiser_id
            assert creative["size"] == {"width": 970, "height": 250}
            assert creative["htmlSnippet"] == "<html><body>Rich content</body></html>"

    def test_create_hosted_asset_creative_image(self):
        """Test hosted asset creative creation for image."""
        asset = {
            "creative_id": "test_image",
            "name": "Test Image Creative",
            "media_url": "https://example.com/banner.jpg",
            "width": 300,
            "height": 250,
        }

        mock_uploaded_asset = {
            "assetId": "asset_123",
            "fileName": "banner.jpg",
            "fileSize": 50000,
            "mimeType": "image/jpeg",
        }

        with (
            patch.object(self.creatives_manager, "_upload_binary_asset") as mock_upload,
            patch.object(self.creatives_manager, "_determine_asset_type") as mock_asset_type,
        ):

            mock_upload.return_value = mock_uploaded_asset
            mock_asset_type.return_value = "image"

            creative = self.creatives_manager._create_hosted_asset_creative(asset)

            assert creative["xsi_type"] == "ImageCreative"
            assert creative["name"] == "Test Image Creative"
            assert creative["advertiserId"] == self.advertiser_id
            assert creative["size"] == {"width": 300, "height": 250}
            assert creative["primaryImageAsset"] == mock_uploaded_asset

    def test_create_hosted_asset_creative_video(self):
        """Test hosted asset creative creation for video."""
        asset = {
            "creative_id": "test_video",
            "name": "Test Video Creative",
            "media_url": "https://example.com/video.mp4",
            "width": 1280,
            "height": 720,
        }

        mock_uploaded_asset = {
            "assetId": "asset_456",
            "fileName": "video.mp4",
            "fileSize": 1000000,
            "mimeType": "video/mp4",
        }

        with (
            patch.object(self.creatives_manager, "_upload_binary_asset") as mock_upload,
            patch.object(self.creatives_manager, "_determine_asset_type") as mock_asset_type,
        ):

            mock_upload.return_value = mock_uploaded_asset
            mock_asset_type.return_value = "video"

            creative = self.creatives_manager._create_hosted_asset_creative(asset)

            assert creative["xsi_type"] == "VideoCreative"
            assert creative["name"] == "Test Video Creative"
            assert creative["advertiserId"] == self.advertiser_id
            assert creative["size"] == {"width": 1280, "height": 720}
            assert creative["videoAsset"] == mock_uploaded_asset

    def test_create_hosted_asset_creative_upload_failure(self):
        """Test hosted asset creative creation when upload fails."""
        asset = {
            "creative_id": "test_failed",
            "media_url": "https://example.com/banner.jpg",
            "width": 300,
            "height": 250,
        }

        with patch.object(self.creatives_manager, "_upload_binary_asset") as mock_upload:
            mock_upload.return_value = None  # Upload failed

            with pytest.raises(Exception, match="Failed to upload binary asset"):
                self.creatives_manager._create_hosted_asset_creative(asset)

    def test_upload_binary_asset_dry_run(self):
        """Test binary asset upload in dry-run mode."""
        self.creatives_manager.dry_run = True

        asset = {"name": "test.jpg", "media_url": "https://example.com/banner.jpg"}

        with patch.object(self.creatives_manager, "_get_content_type") as mock_content_type:
            mock_content_type.return_value = "image/jpeg"

            result = self.creatives_manager._upload_binary_asset(asset)

            assert result is not None
            assert result["fileName"] == "test.jpg"
            assert result["mimeType"] == "image/jpeg"
            assert "assetId" in result

    def test_get_content_type_detection(self):
        """Test content type detection from various asset properties."""
        test_cases = [
            ({"mime_type": "image/png"}, "image/png"),
            ({"media_url": "https://example.com/image.jpg"}, "image/jpeg"),
            ({"media_url": "https://example.com/image.jpeg"}, "image/jpeg"),
            ({"media_url": "https://example.com/image.png"}, "image/png"),
            ({"media_url": "https://example.com/image.gif"}, "image/gif"),
            ({"media_url": "https://example.com/video.mp4"}, "video/mp4"),
            ({"url": "https://example.com/video.mov"}, "video/mp4"),
            ({"url": "https://example.com/unknown.ext"}, "image/jpeg"),  # Default
        ]

        for asset, expected_type in test_cases:
            content_type = self.creatives_manager._get_content_type(asset)
            assert content_type == expected_type

    def test_determine_asset_type(self):
        """Test asset type determination (image vs video)."""
        # Video asset
        asset = {"media_url": "https://example.com/video.mp4"}
        with patch.object(self.creatives_manager, "_get_content_type") as mock_content_type:
            mock_content_type.return_value = "video/mp4"
            asset_type = self.creatives_manager._determine_asset_type(asset)
            assert asset_type == "video"

        # Image asset
        asset = {"media_url": "https://example.com/banner.jpg"}
        with patch.object(self.creatives_manager, "_get_content_type") as mock_content_type:
            mock_content_type.return_value = "image/jpeg"
            asset_type = self.creatives_manager._determine_asset_type(asset)
            assert asset_type == "image"

    def test_get_html5_source_from_media_data(self):
        """Test HTML5 source extraction from media_data."""
        html_content = "<html><body>Test content</body></html>"
        base64_content = base64.b64encode(html_content.encode()).decode()

        asset = {"media_data": f"data:text/html;base64,{base64_content}"}

        source = self.creatives_manager._get_html5_source(asset)
        assert source == html_content

    def test_get_html5_source_from_media_url(self):
        """Test HTML5 source extraction from media_url."""
        asset = {"media_url": "https://example.com/creative.html"}

        source = self.creatives_manager._get_html5_source(asset)
        expected = (
            '<iframe src="https://example.com/creative.html" width="100%" height="100%" frameborder="0"></iframe>'
        )
        assert source == expected

    def test_get_html5_source_fallback_to_url(self):
        """Test HTML5 source fallback to URL field."""
        asset = {"url": "https://example.com/creative.html"}

        source = self.creatives_manager._get_html5_source(asset)
        expected = (
            '<iframe src="https://example.com/creative.html" width="100%" height="100%" frameborder="0"></iframe>'
        )
        assert source == expected

    def test_get_html5_source_no_content_raises_error(self):
        """Test HTML5 source extraction with no content raises error."""
        asset = {"creative_id": "test"}  # No content

        with pytest.raises(Exception, match="No HTML5 source content found in asset"):
            self.creatives_manager._get_html5_source(asset)

    def test_build_native_template_variables(self):
        """Test native template variable building."""
        asset = {
            "template_variables": {
                "headline": "Great Product",
                "image_url": "https://example.com/img.jpg",
                "price": 19.99,
            }
        }

        variables = self.creatives_manager._build_native_template_variables(asset)

        assert len(variables) == 3

        # Check variable structure
        headline_var = next(v for v in variables if v["uniqueName"] == "headline")
        assert headline_var["value"]["xsi_type"] == "StringCreativeTemplateVariableValue"
        assert headline_var["value"]["value"] == "Great Product"

        price_var = next(v for v in variables if v["uniqueName"] == "price")
        assert price_var["value"]["value"] == "19.99"  # Converted to string

    def test_add_tracking_urls_to_creative_impression_tracking(self):
        """Test adding impression tracking URLs to creative."""
        creative = {"xsi_type": "ImageCreative"}
        asset = {"tracking_events": {"impression": ["https://track1.com", "https://track2.com"]}}

        self.creatives_manager._add_tracking_urls_to_creative(creative, asset)

        assert "trackingUrls" in creative
        expected_urls = [{"url": "https://track1.com"}, {"url": "https://track2.com"}]
        assert creative["trackingUrls"] == expected_urls

    def test_add_tracking_urls_to_creative_click_tracking(self):
        """Test adding click tracking URLs to supported creative types."""
        test_cases = ["ImageCreative", "ThirdPartyCreative"]

        for creative_type in test_cases:
            creative = {"xsi_type": creative_type}
            asset = {"tracking_events": {"click": ["https://click-track.com"]}}

            self.creatives_manager._add_tracking_urls_to_creative(creative, asset)

            assert creative["destinationUrl"] == "https://click-track.com"

    def test_add_tracking_urls_no_tracking_events(self):
        """Test adding tracking URLs when no tracking events exist."""
        creative = {"xsi_type": "ImageCreative"}
        asset = {}

        self.creatives_manager._add_tracking_urls_to_creative(creative, asset)

        # Should not add any tracking fields
        assert "trackingUrls" not in creative
        assert "destinationUrl" not in creative

    def test_validate_creative_size_against_placeholders_valid_match(self):
        """Test creative size validation against placeholders with valid match."""
        asset = {"creative_id": "test_creative", "format": "display_300x250", "package_assignments": ["package_1"]}

        creative_placeholders = {
            "package_1": [
                {"size": {"width": 300, "height": 250}, "creativeSizeType": "PIXEL"},
                {"size": {"width": 728, "height": 90}, "creativeSizeType": "PIXEL"},
            ]
        }

        errors = self.creatives_manager._validate_creative_size_against_placeholders(asset, creative_placeholders)

        assert len(errors) == 0

    def test_validate_creative_size_against_placeholders_no_match(self):
        """Test creative size validation with no matching placeholders."""
        asset = {"creative_id": "test_creative", "format": "display_970x250", "package_assignments": ["package_1"]}

        creative_placeholders = {
            "package_1": [
                {"size": {"width": 300, "height": 250}, "creativeSizeType": "PIXEL"},
                {"size": {"width": 728, "height": 90}, "creativeSizeType": "PIXEL"},
            ]
        }

        errors = self.creatives_manager._validate_creative_size_against_placeholders(asset, creative_placeholders)

        assert len(errors) == 1
        assert "970x250 does not match any LineItem placeholders" in errors[0]
        assert "300x250" in errors[0] or "728x90" in errors[0]

    def test_validate_creative_size_against_placeholders_no_assignments(self):
        """Test creative size validation with no package assignments."""
        asset = {"creative_id": "test_creative", "format": "display_300x250", "package_assignments": []}

        creative_placeholders = {}

        errors = self.creatives_manager._validate_creative_size_against_placeholders(asset, creative_placeholders)

        assert len(errors) == 0  # Should pass with no assignments

    def test_validate_creative_size_against_placeholders_dimension_error(self):
        """Test creative size validation when dimensions cannot be determined."""
        asset = {
            "creative_id": "test_creative",
            "package_assignments": ["package_1"],
            # No format, width, or height
        }

        creative_placeholders = {"package_1": [{"size": {"width": 728, "height": 90}, "creativeSizeType": "PIXEL"}]}

        # Mock dimension extraction to raise exception
        with patch.object(self.creatives_manager, "_get_creative_dimensions") as mock_dims:
            mock_dims.side_effect = Exception("Cannot determine dimensions")

            errors = self.creatives_manager._validate_creative_size_against_placeholders(asset, creative_placeholders)

            assert len(errors) == 1
            assert "Could not determine creative dimensions" in errors[0]

    def test_configure_vast_for_line_items_dry_run(self):
        """Test VAST configuration for line items in dry-run mode."""
        self.creatives_manager.dry_run = True

        asset = {"creative_id": "vast_creative", "snippet": "<VAST>...</VAST>"}

        line_item_map = {"package_1": "line_item_123"}

        # Should not raise exception
        self.creatives_manager._configure_vast_for_line_items("order_123", asset, line_item_map)

    def test_associate_creative_with_line_items_success(self):
        """Test successful creative association with line items."""
        mock_lica_service = Mock()

        asset = {"creative_id": "test_creative", "package_assignments": ["package_1", "package_2"]}

        line_item_map = {"package_1": "line_item_111", "package_2": "line_item_222"}

        self.creatives_manager._associate_creative_with_line_items(
            "gam_creative_123", asset, line_item_map, mock_lica_service
        )

        # Should create associations for both packages
        assert mock_lica_service.createLineItemCreativeAssociations.call_count == 2

        # Verify association structure
        calls = mock_lica_service.createLineItemCreativeAssociations.call_args_list

        first_association = calls[0][0][0][0]
        assert first_association["creativeId"] == "gam_creative_123"
        assert first_association["lineItemId"] == "line_item_111"

        second_association = calls[1][0][0][0]
        assert second_association["creativeId"] == "gam_creative_123"
        assert second_association["lineItemId"] == "line_item_222"

    def test_associate_creative_with_line_items_dry_run(self):
        """Test creative association in dry-run mode."""
        self.creatives_manager.dry_run = True

        asset = {"creative_id": "test_creative", "package_assignments": ["package_1"]}

        line_item_map = {"package_1": "line_item_111"}

        # Should not call service
        self.creatives_manager._associate_creative_with_line_items("gam_creative_123", asset, line_item_map, None)

    def test_associate_creative_with_line_items_missing_line_item(self):
        """Test creative association when line item not found for package."""
        mock_lica_service = Mock()

        asset = {"creative_id": "test_creative", "package_assignments": ["package_1", "missing_package"]}

        line_item_map = {"package_1": "line_item_111"}  # missing_package not in map

        self.creatives_manager._associate_creative_with_line_items(
            "gam_creative_123", asset, line_item_map, mock_lica_service
        )

        # Should only create one association (for existing package)
        assert mock_lica_service.createLineItemCreativeAssociations.call_count == 1

    def test_associate_creative_with_line_items_api_error(self):
        """Test creative association when API call fails."""
        mock_lica_service = Mock()
        mock_lica_service.createLineItemCreativeAssociations.side_effect = Exception("API Error")

        asset = {"creative_id": "test_creative", "package_assignments": ["package_1"]}

        line_item_map = {"package_1": "line_item_111"}

        with pytest.raises(Exception, match="API Error"):
            self.creatives_manager._associate_creative_with_line_items(
                "gam_creative_123", asset, line_item_map, mock_lica_service
            )


class TestGAMCreativesManagerAssetWorkflow:
    """Test suite for add_creative_assets workflow."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock()
        self.advertiser_id = "123456789"
        self.creatives_manager = GAMCreativesManager(self.mock_client_manager, self.advertiser_id, dry_run=False)

        # Mock validator
        self.mock_validator = Mock()
        self.creatives_manager.validator = self.mock_validator

    def test_add_creative_assets_success_flow(self):
        """Test successful creative assets addition workflow."""
        # Setup test data
        assets = [
            {
                "creative_id": "test_creative_1",
                "name": "Test Creative",
                "snippet": "<script>test</script>",
                "snippet_type": "javascript",
                "package_assignments": ["package_1"],
                "width": 300,
                "height": 250,
            }
        ]

        today = datetime.now()

        # Setup mocks
        mock_creative_service = Mock()
        mock_lica_service = Mock()
        mock_line_item_service = Mock()

        self.mock_client_manager.get_service.side_effect = lambda service: {
            "CreativeService": mock_creative_service,
            "LineItemCreativeAssociationService": mock_lica_service,
            "LineItemService": mock_line_item_service,
        }[service]

        # Mock line item info
        line_item_map = {"package_1": "line_item_123"}
        creative_placeholders = {"package_1": [{"size": {"width": 300, "height": 250}, "creativeSizeType": "PIXEL"}]}

        with (
            patch.object(self.creatives_manager, "_get_line_item_info") as mock_get_info,
            patch.object(self.creatives_manager, "_validate_creative_for_gam") as mock_validate,
            patch.object(self.creatives_manager, "_validate_creative_size_against_placeholders") as mock_validate_size,
        ):

            mock_get_info.return_value = (line_item_map, creative_placeholders)
            mock_validate.return_value = []  # No validation errors
            mock_validate_size.return_value = []  # No size validation errors

            # Mock creative creation
            created_creative = {"id": "gam_creative_123", "name": "Test Creative"}
            mock_creative_service.createCreatives.return_value = [created_creative]

            result = self.creatives_manager.add_creative_assets("order_123", assets, today)

            assert len(result) == 1
            assert result[0].creative_id == "test_creative_1"
            assert result[0].status == "approved"

    def test_add_creative_assets_validation_failure(self):
        """Test creative assets addition with validation failure."""
        assets = [
            {
                "creative_id": "invalid_creative",
                "snippet": "<script>eval('bad');</script>",
                "snippet_type": "javascript",
            }
        ]

        today = datetime.now()

        # Setup validation to return errors
        with (
            patch.object(self.creatives_manager, "_get_line_item_info") as mock_get_info,
            patch.object(self.creatives_manager, "_validate_creative_for_gam") as mock_validate,
        ):

            mock_get_info.return_value = ({}, {})
            mock_validate.return_value = ["eval() is not allowed", "Unsafe script content"]

            result = self.creatives_manager.add_creative_assets("order_123", assets, today)

            assert len(result) == 1
            assert result[0].creative_id == "invalid_creative"
            assert result[0].status == "failed"

    def test_add_creative_assets_vast_creative(self):
        """Test VAST creative handling (configured at line item level)."""
        assets = [
            {
                "creative_id": "vast_creative",
                "snippet": "<VAST>...</VAST>",
                "snippet_type": "vast_xml",
                "package_assignments": ["package_1"],
            }
        ]

        today = datetime.now()

        with (
            patch.object(self.creatives_manager, "_get_line_item_info") as mock_get_info,
            patch.object(self.creatives_manager, "_validate_creative_for_gam") as mock_validate,
            patch.object(self.creatives_manager, "_validate_creative_size_against_placeholders") as mock_size_validate,
            patch.object(self.creatives_manager, "_configure_vast_for_line_items") as mock_configure_vast,
        ):

            mock_get_info.return_value = (
                {"package_1": "line_item_123"},
                {"line_item_123": [{"width": 300, "height": 250}]},
            )
            mock_validate.return_value = []
            mock_size_validate.return_value = []

            result = self.creatives_manager.add_creative_assets("order_123", assets, today)

            assert len(result) == 1
            assert result[0].creative_id == "vast_creative"
            assert result[0].status == "approved"

            # Should configure VAST at line item level
            mock_configure_vast.assert_called_once()

    def test_add_creative_assets_dry_run_mode(self):
        """Test creative assets addition in dry-run mode."""
        self.creatives_manager.dry_run = True

        assets = [
            {
                "creative_id": "dry_run_creative",
                "snippet": "<script>test</script>",
                "snippet_type": "javascript",
                "package_assignments": ["package_1"],
            }
        ]

        today = datetime.now()

        with (
            patch.object(self.creatives_manager, "_get_line_item_info") as mock_get_info,
            patch.object(self.creatives_manager, "_validate_creative_for_gam") as mock_validate,
        ):

            mock_get_info.return_value = (
                {"package_1": "line_item_123"},
                {"package_1": [{"size": {"width": 300, "height": 250}}]},
            )
            mock_validate.return_value = []

            result = self.creatives_manager.add_creative_assets("order_123", assets, today)

            assert len(result) == 1
            assert result[0].creative_id == "dry_run_creative"
            assert result[0].status == "approved"

            # Should not call GAM services in dry-run mode
            self.mock_client_manager.get_service.assert_not_called()

    def test_add_creative_assets_unsupported_creative_type(self):
        """Test handling of unsupported creative types."""
        assets = [{"creative_id": "unsupported_creative", "unsupported_field": "value"}]

        today = datetime.now()

        with (
            patch.object(self.creatives_manager, "_get_line_item_info") as mock_get_info,
            patch.object(self.creatives_manager, "_validate_creative_for_gam") as mock_validate,
            patch.object(self.creatives_manager, "_create_gam_creative") as mock_create,
        ):

            mock_get_info.return_value = ({}, {})
            mock_validate.return_value = []
            mock_create.return_value = None  # Unsupported type

            result = self.creatives_manager.add_creative_assets("order_123", assets, today)

            assert len(result) == 1
            assert result[0].creative_id == "unsupported_creative"
            assert result[0].status == "failed"

    def test_add_creative_assets_creative_creation_failure(self):
        """Test handling of creative creation failures."""
        assets = [{"creative_id": "failed_creative", "snippet": "<script>test</script>", "snippet_type": "javascript"}]

        today = datetime.now()

        # Setup mocks
        mock_creative_service = Mock()
        mock_creative_service.createCreatives.side_effect = Exception("GAM API Error")
        self.mock_client_manager.get_service.return_value = mock_creative_service

        with (
            patch.object(self.creatives_manager, "_get_line_item_info") as mock_get_info,
            patch.object(self.creatives_manager, "_validate_creative_for_gam") as mock_validate,
        ):

            mock_get_info.return_value = ({}, {})
            mock_validate.return_value = []

            result = self.creatives_manager.add_creative_assets("order_123", assets, today)

            assert len(result) == 1
            assert result[0].creative_id == "failed_creative"
            assert result[0].status == "failed"

    def test_get_line_item_info_success(self):
        """Test successful line item info retrieval."""
        mock_line_item_service = Mock()
        mock_statement_builder = Mock()
        mock_statement = Mock()

        # Setup statement builder
        self.mock_client_manager.get_statement_builder.return_value = mock_statement_builder
        mock_statement_builder.where.return_value = mock_statement_builder
        mock_statement_builder.with_bind_variable.return_value = mock_statement_builder
        mock_statement_builder.ToStatement.return_value = mock_statement

        # Mock line items response
        line_items = [
            {
                "id": "line_item_123",
                "name": "package_1",
                "creativePlaceholders": [{"size": {"width": 300, "height": 250}, "creativeSizeType": "PIXEL"}],
            }
        ]
        mock_line_item_service.getLineItemsByStatement.return_value = {"results": line_items}

        line_item_map, creative_placeholders = self.creatives_manager._get_line_item_info("123", mock_line_item_service)

        assert line_item_map == {"package_1": "line_item_123"}
        assert "package_1" in creative_placeholders
        assert len(creative_placeholders["package_1"]) == 1

    def test_get_line_item_info_dry_run(self):
        """Test line item info retrieval in dry-run mode."""
        line_item_map, creative_placeholders = self.creatives_manager._get_line_item_info("123", None)

        # Should return mock data
        assert line_item_map == {"mock_package": "mock_line_item_123"}
        assert "mock_package" in creative_placeholders
