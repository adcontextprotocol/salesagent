"""Integration tests for creative lifecycle A2A server endpoints.

Tests the A2A skill handlers for sync_creatives and list_creatives endpoints.
These tests verify the A2A-specific parameter mapping, response formatting,
and error handling without mocking the core business logic.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from a2a.types import InternalError
from a2a.utils.errors import ServerError

from src.core.database.database_session import get_db_session
from src.core.database.models import MediaBuy, Principal, Tenant
from tests.utils.database_helpers import create_tenant_with_timestamps


class A2ATestMockHelper:
    """Centralized mock setup to reduce duplicate mocking patterns."""

    @staticmethod
    def create_mock_context(tenant_id, principal_id):
        """Create a mock tool context with tenant and principal info."""
        mock_context = MagicMock()
        mock_context.tenant_id = tenant_id
        mock_context.principal_id = principal_id
        return mock_context

    @staticmethod
    def setup_comprehensive_mocks(handler, tenant_id, principal_id):
        """Set up all necessary mocks for A2A testing in one place."""
        mock_context = A2ATestMockHelper.create_mock_context(tenant_id, principal_id)

        # Single patch for context creation
        context_patch = patch.object(handler, "_create_tool_context_from_a2a", return_value=mock_context)

        # Single patch for core sync function
        sync_patch = patch("src.a2a_server.adcp_a2a_server.core_sync_creatives_tool")

        # Single patch for core list function
        list_patch = patch("src.a2a_server.adcp_a2a_server.core_list_creatives_tool")

        return context_patch, sync_patch, list_patch, mock_context


class TestCreativeLifecycleA2A:
    """Integration tests for creative lifecycle A2A skill handlers."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, integration_db):
        """Create test tenant, principal, and media buy for A2A tests."""
        with get_db_session() as session:
            # Create test tenant
            tenant = create_tenant_with_timestamps(
                tenant_id="a2a_creative_test",
                name="A2A Creative Test Tenant",
                subdomain="a2a-creative-test",
                is_active=True,
                ad_server="mock",
                max_daily_budget=10000,
                enable_axe_signals=True,
                authorized_emails=[],
                authorized_domains=[],
                auto_approve_formats=["display_300x250", "video_pre_roll"],
                human_review_required=False,
            )
            session.add(tenant)

            # Create test principal
            principal = Principal(
                tenant_id="a2a_creative_test",
                principal_id="a2a_test_advertiser",
                name="A2A Test Advertiser",
                access_token="a2a-test-token-456",
                platform_mappings={"mock": {"id": "a2a_test_advertiser"}},
            )
            session.add(principal)

            # Create test media buy
            media_buy = MediaBuy(
                tenant_id="a2a_creative_test",
                media_buy_id="a2a_test_media_buy",
                principal_id="a2a_test_advertiser",
                order_name="A2A Test Order",
                advertiser_name="A2A Test Advertiser",
                status="active",
                budget=8000.0,
                start_date=datetime.now(UTC).date(),
                end_date=(datetime.now(UTC) + timedelta(days=21)).date(),
                buyer_ref="a2a_buyer_ref_456",
                raw_request={"test": True},
            )
            session.add(media_buy)

            session.commit()

        # Store test identifiers
        self.test_tenant_id = "a2a_creative_test"
        self.test_principal_id = "a2a_test_advertiser"
        self.test_media_buy_id = "a2a_test_media_buy"
        self.test_buyer_ref = "a2a_buyer_ref_456"
        self.test_auth_token = "a2a-test-token-456"

    @pytest.fixture
    def a2a_handler(self):
        """Create A2A request handler for testing."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        return AdCPRequestHandler()

    async def test_sync_creatives_comprehensive(self, a2a_handler):
        """Comprehensive test for sync_creatives skill handler covering success, parameters, and errors."""
        # Test data for various scenarios
        success_parameters = {
            "creatives": [
                {
                    "creative_id": "test_creative_1",
                    "name": "Test Display Ad",
                    "format": "display_300x250",
                    "url": "https://example.com/display.jpg",
                    "click_url": "https://example.com/landing",
                    "width": 300,
                    "height": 250,
                },
                {
                    "creative_id": "test_creative_2",
                    "name": "Test Video Ad",
                    "format": "video_pre_roll",
                    "url": "https://example.com/video.mp4",
                    "duration": 15.0,
                },
            ],
            "media_buy_id": self.test_media_buy_id,
            "assign_to_packages": ["package_1", "package_2"],
            "upsert": True,
        }

        # Set up comprehensive mocks
        context_patch, sync_patch, list_patch, mock_context = A2ATestMockHelper.setup_comprehensive_mocks(
            a2a_handler, self.test_tenant_id, self.test_principal_id
        )

        with context_patch, sync_patch as mock_sync, list_patch:
            from src.core.schemas import Creative, CreativeAssignment, SyncCreativesResponse

            # Test 1: Successful sync with assignments
            from tests.utils.database_helpers import get_utc_now
            now = get_utc_now()
            synced_creatives = [
                Creative(
                    creative_id="test_creative_1",
                    name="Test Display Ad",
                    format_id="display_300x250",
                    content_uri="https://example.com/display.jpg",
                    principal_id=self.test_principal_id,
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
                Creative(
                    creative_id="test_creative_2",
                    name="Test Video Ad",
                    format_id="video_pre_roll",
                    content_uri="https://example.com/video.mp4",
                    principal_id=self.test_principal_id,
                    status="pending",
                    created_at=now,
                    updated_at=now,
                ),
            ]

            assignments = [
                CreativeAssignment(
                    assignment_id="assign_1",
                    media_buy_id=self.test_media_buy_id,
                    package_id="package_1",
                    creative_id="test_creative_1",
                    weight=100,
                )
            ]

            mock_sync.return_value = SyncCreativesResponse(
                synced_creatives=synced_creatives,
                failed_creatives=[],
                assignments=assignments,
                message="Synced 2 creatives, 1 assignment created",
            )

            result = await a2a_handler._handle_sync_creatives_skill(
                parameters=success_parameters, auth_token=self.test_auth_token
            )

            # Verify successful result
            assert result["success"] is True
            assert len(result["synced_creatives"]) == 2
            assert len(result["assignments"]) == 1
            assert result["message"] == "Synced 2 creatives, 1 assignment created"

            # Verify creative data structure
            creative_1 = result["synced_creatives"][0]
            assert creative_1["creative_id"] == "test_creative_1"
            assert creative_1["format"] == "display_300x250"
            assert creative_1["status"] == "approved"

            # Test 2: Parameter validation - missing required parameter
            invalid_params = {"media_buy_id": "some_id"}  # Missing 'creatives'

            validation_result = await a2a_handler._handle_sync_creatives_skill(
                parameters=invalid_params, auth_token=self.test_auth_token
            )

            assert validation_result["success"] is False
            assert "Missing required parameter: 'creatives'" in validation_result["message"]
            assert "creatives" in validation_result["required_parameters"]

            # Test 3: Buyer ref instead of media_buy_id
            buyer_ref_params = {
                "creatives": [{"creative_id": "buyer_creative", "name": "Test", "format": "display_300x250"}],
                "buyer_ref": self.test_buyer_ref,
            }

            mock_sync.return_value = SyncCreativesResponse(
                synced_creatives=[], failed_creatives=[], assignments=[], message="Success"
            )

            await a2a_handler._handle_sync_creatives_skill(parameters=buyer_ref_params, auth_token=self.test_auth_token)

            # Verify buyer_ref was used instead of media_buy_id
            last_call_args = mock_sync.call_args[1]
            assert last_call_args["buyer_ref"] == self.test_buyer_ref
            assert last_call_args["media_buy_id"] is None

            # Test 4: Partial failure handling
            mock_sync.return_value = SyncCreativesResponse(
                synced_creatives=[synced_creatives[0]],  # Only first creative succeeds
                failed_creatives=[
                    {"creative_id": "test_creative_2", "name": "Test Video Ad", "error": "Invalid format"}
                ],
                assignments=[],
                message="Synced 1 creative, 1 failed",
            )

            partial_result = await a2a_handler._handle_sync_creatives_skill(
                parameters=success_parameters, auth_token=self.test_auth_token
            )

            assert partial_result["success"] is True
            assert len(partial_result["synced_creatives"]) == 1
            assert len(partial_result["failed_creatives"]) == 1
            assert "Invalid format" in partial_result["failed_creatives"][0]["error"]

            # Test 5: Core function exception handling
            mock_sync.side_effect = Exception("Database error")

            with pytest.raises(ServerError) as exc_info:
                await a2a_handler._handle_sync_creatives_skill(
                    parameters=success_parameters, auth_token=self.test_auth_token
                )

            assert isinstance(exc_info.value.error, InternalError)
            assert "Failed to sync creatives: Database error" in str(exc_info.value.error.message)

    async def test_list_creatives_comprehensive(self, a2a_handler):
        """Comprehensive test for list_creatives skill handler covering all parameters and error cases."""
        # Test parameters covering all possible options
        comprehensive_params = {
            "media_buy_id": self.test_media_buy_id,
            "status": "approved",
            "format": "display_300x250",
            "search": "holiday",
            "tags": ["sale", "promo"],
            "created_after": "2024-01-01T00:00:00Z",
            "created_before": "2024-12-31T23:59:59Z",
            "page": 2,
            "limit": 25,
            "sort_by": "name",
            "sort_order": "asc",
        }

        # Set up comprehensive mocks
        context_patch, sync_patch, list_patch, mock_context = A2ATestMockHelper.setup_comprehensive_mocks(
            a2a_handler, self.test_tenant_id, self.test_principal_id
        )

        with context_patch, sync_patch, list_patch as mock_list:
            from src.core.schemas import Creative, ListCreativesResponse

            # Test 1: Successful list with all parameters
            from tests.utils.database_helpers import get_utc_now
            now = get_utc_now()
            sample_creatives = [
                Creative(
                    creative_id="list_creative_1",
                    name="Holiday Sale Banner",
                    format_id="display_300x250",
                    content_uri="https://example.com/holiday1.jpg",
                    principal_id=self.test_principal_id,
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
                Creative(
                    creative_id="list_creative_2",
                    name="Holiday Video Promo",
                    format_id="video_pre_roll",
                    content_uri="https://example.com/holiday2.mp4",
                    principal_id=self.test_principal_id,
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
            ]

            mock_list.return_value = ListCreativesResponse(
                creatives=sample_creatives,
                total_count=47,
                page=2,
                limit=25,
                has_more=True,
                message="Found 2 of 47 creatives",
            )

            result = await a2a_handler._handle_list_creatives_skill(
                parameters=comprehensive_params, auth_token=self.test_auth_token
            )

            # Verify successful result
            assert result["success"] is True
            assert len(result["creatives"]) == 2
            assert result["total_count"] == 47
            assert result["has_more"] is True
            assert result["message"] == "Found 2 of 47 creatives"

            # Verify all parameters were passed to core function
            call_args = mock_list.call_args[1]
            assert call_args["media_buy_id"] == self.test_media_buy_id
            assert call_args["status"] == "approved"
            assert call_args["format"] == "display_300x250"
            assert call_args["search"] == "holiday"
            assert call_args["tags"] == ["sale", "promo"]
            assert call_args["created_after"] == "2024-01-01T00:00:00Z"
            assert call_args["created_before"] == "2024-12-31T23:59:59Z"
            assert call_args["page"] == 2
            assert call_args["limit"] == 25
            assert call_args["sort_by"] == "name"
            assert call_args["sort_order"] == "asc"

            # Test 2: Minimal parameters (defaults)
            minimal_result = await a2a_handler._handle_list_creatives_skill(
                parameters={}, auth_token=self.test_auth_token
            )
            assert minimal_result["success"] is True

            # Verify default parameters were used
            call_args = mock_list.call_args[1]
            assert call_args["page"] == 1
            assert call_args["limit"] == 50
            assert call_args["sort_by"] == "created_date"
            assert call_args["sort_order"] == "desc"
            assert call_args["tags"] == []

            # Test 3: Buyer ref parameter
            buyer_ref_params = {"buyer_ref": self.test_buyer_ref, "status": "pending"}

            await a2a_handler._handle_list_creatives_skill(parameters=buyer_ref_params, auth_token=self.test_auth_token)

            call_args = mock_list.call_args[1]
            assert call_args["buyer_ref"] == self.test_buyer_ref
            assert call_args["media_buy_id"] is None

            # Test 4: Empty results
            mock_list.return_value = ListCreativesResponse(
                creatives=[], total_count=0, page=1, limit=50, has_more=False, message="No creatives found"
            )

            empty_result = await a2a_handler._handle_list_creatives_skill(
                parameters={"status": "archived"}, auth_token=self.test_auth_token
            )

            assert empty_result["success"] is True
            assert empty_result["creatives"] == []
            assert empty_result["total_count"] == 0
            assert empty_result["has_more"] is False

            # Test 5: Core function exception handling
            mock_list.side_effect = Exception("Database connection failed")

            with pytest.raises(ServerError) as exc_info:
                await a2a_handler._handle_list_creatives_skill(
                    parameters={"status": "approved"}, auth_token=self.test_auth_token
                )

            assert isinstance(exc_info.value.error, InternalError)
            assert "Failed to list creatives: Database connection failed" in str(exc_info.value.error.message)

    async def test_context_creation_integration(self, a2a_handler):
        """Test real context creation without mocking to verify integration."""
        # This test uses real context creation to ensure proper integration
        parameters = {
            "creatives": [
                {
                    "creative_id": "integration_test",
                    "name": "Integration Test Creative",
                    "format": "display_300x250",
                    "url": "https://example.com/integration.jpg",
                }
            ]
        }

        # Only mock the core function, not the context creation
        with patch("src.a2a_server.adcp_a2a_server.core_sync_creatives_tool") as mock_core:
            from src.core.schemas import SyncCreativesResponse

            mock_core.return_value = SyncCreativesResponse(
                synced_creatives=[], failed_creatives=[], assignments=[], message="Success"
            )

            # Call with real context creation
            result = await a2a_handler._handle_sync_creatives_skill(
                parameters=parameters, auth_token=self.test_auth_token
            )

            # Verify the real context was created and used properly
            assert result["success"] is True

            # Verify context argument structure
            call_args = mock_core.call_args[1]
            context_arg = call_args["context"]
            assert hasattr(context_arg, "tenant_id")
            assert hasattr(context_arg, "principal_id")
            assert context_arg.tenant_id == self.test_tenant_id
            assert context_arg.principal_id == self.test_principal_id
