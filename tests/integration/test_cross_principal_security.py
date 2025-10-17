"""Integration tests for cross-principal data isolation security.

CRITICAL SECURITY TESTS: These tests verify that principals (advertisers) cannot
access or modify each other's data within the same tenant.

Tests cover:
1. sync_creatives - Cannot modify another principal's creatives
2. list_creatives - Cannot see another principal's creatives
3. update_media_buy - Cannot modify another principal's media buys
4. get_media_buy_delivery - Cannot see another principal's media buy delivery data
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from src.core.database.database_session import get_db_session
from src.core.database.models import Creative as DBCreative
from src.core.database.models import MediaBuy, Principal
from src.core.schema_adapters import ListCreativesResponse
from tests.utils.database_helpers import create_tenant_with_timestamps

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


class MockContext:
    """Mock FastMCP Context for testing."""

    def __init__(self, auth_token=None):
        if auth_token is None:
            self.meta = {"headers": {}}
        else:
            self.meta = {"headers": {"x-adcp-auth": auth_token}}


class TestCrossPrincipalSecurity:
    """Integration tests for cross-principal data isolation."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, integration_db):
        """Create test tenant with multiple principals and their data."""
        with get_db_session() as session:
            # Create test tenant
            tenant = create_tenant_with_timestamps(
                tenant_id="security_test_tenant",
                name="Security Test Tenant",
                subdomain="security-test",
                is_active=True,
                ad_server="mock",
                enable_axe_signals=True,
                authorized_emails=[],
                authorized_domains=[],
                auto_approve_formats=["display_300x250"],
                human_review_required=False,
            )
            session.add(tenant)

            # Create two different principals (advertisers)
            principal_a = Principal(
                tenant_id="security_test_tenant",
                principal_id="advertiser_a",
                name="Advertiser A",
                access_token="token-advertiser-a",
                platform_mappings={"mock": {"id": "advertiser_a"}},
            )
            principal_b = Principal(
                tenant_id="security_test_tenant",
                principal_id="advertiser_b",
                name="Advertiser B",
                access_token="token-advertiser-b",
                platform_mappings={"mock": {"id": "advertiser_b"}},
            )
            session.add_all([principal_a, principal_b])

            # Commit principals before creating dependent data (FK constraint)
            session.commit()

            # Create creative owned by Advertiser A
            creative_a = DBCreative(
                tenant_id="security_test_tenant",
                creative_id="creative_owned_by_a",
                principal_id="advertiser_a",
                name="Advertiser A Creative",
                format="display_300x250",
                agent_url="https://creative.adcontextprotocol.org/",
                status="approved",
                data={
                    "url": "https://example.com/creative_a.jpg",
                    "width": 300,
                    "height": 250,
                },
            )
            session.add(creative_a)

            # Create media buy owned by Advertiser A
            media_buy_a = MediaBuy(
                tenant_id="security_test_tenant",
                media_buy_id="media_buy_a",
                principal_id="advertiser_a",
                buyer_ref="buyer_ref_a",
                flight_start_date=date.today(),
                flight_end_date=date.today() + timedelta(days=30),
                total_budget=1000.0,
                currency="USD",
                raw_request={
                    "buyer_ref": "buyer_ref_a",
                    "packages": [],
                    "budget": {"total": 1000.0, "currency": "USD"},
                },
                platform_order_id="order_a",
            )
            session.add(media_buy_a)

            session.commit()

    def test_sync_creatives_cannot_modify_other_principals_creative(self):
        """Test that sync_creatives cannot modify another principal's creative.

        SECURITY: Principal B should NOT be able to modify Principal A's creative
        by calling sync_creatives with the same creative_id.
        """
        from src.core.main import _sync_creatives_impl

        # Principal B tries to modify Principal A's creative
        mock_context_b = MockContext(auth_token="token-advertiser-b")

        creatives_data = [
            {
                "creative_id": "creative_owned_by_a",  # Owned by Principal A!
                "name": "HACKED BY PRINCIPAL B",  # Trying to change name
                "format": "display_728x90",  # Trying to change format
                "url": "https://evil.com/malicious.jpg",
            }
        ]

        with patch("src.core.main.get_current_tenant", return_value={"tenant_id": "security_test_tenant"}):
            response = _sync_creatives_impl(creatives=creatives_data, patch=False, context=mock_context_b)

            # Verify Principal B's attempt did NOT modify Principal A's creative
            with get_db_session() as session:
                from sqlalchemy import select

                stmt = select(DBCreative).filter_by(tenant_id="security_test_tenant", creative_id="creative_owned_by_a")
                original_creative = session.scalars(stmt).first()

                # Original creative should be UNCHANGED
                assert original_creative.principal_id == "advertiser_a", "Creative ownership changed!"
                assert original_creative.name == "Advertiser A Creative", "Creative name was modified!"
                assert original_creative.format == "display_300x250", "Creative format was modified!"
                assert (
                    original_creative.data["url"] == "https://example.com/creative_a.jpg"
                ), "Creative URL was modified!"

            # Response should show success (it created a NEW creative for Principal B, not modified A's)
            assert response.synced == 1, "Should have created 1 creative"
            assert len(response.failed) == 0, "Should have no failures"

            # Verify a NEW creative was created for Principal B (upsert behavior)
            with get_db_session() as session:
                stmt = select(DBCreative).filter_by(
                    tenant_id="security_test_tenant",
                    principal_id="advertiser_b",
                    creative_id="creative_owned_by_a",
                )
                new_creative = session.scalars(stmt).first()

                assert new_creative is not None, "Should have created NEW creative for Principal B"
                assert new_creative.name == "HACKED BY PRINCIPAL B"
                assert new_creative.principal_id == "advertiser_b"

    def test_list_creatives_cannot_see_other_principals_creatives(self):
        """Test that list_creatives only returns the authenticated principal's creatives.

        SECURITY: Principal B should NOT see Principal A's creatives.
        """
        from src.core.main import list_creatives as core_list_creatives_tool

        mock_context_b = MockContext(auth_token="token-advertiser-b")

        with patch("src.core.main.get_current_tenant", return_value={"tenant_id": "security_test_tenant"}):
            response = core_list_creatives_tool(context=mock_context_b)

            assert isinstance(response, ListCreativesResponse)

            # Principal B should see ZERO creatives (they don't own any)
            assert len(response.creatives) == 0, "Principal B should not see Principal A's creative!"
            assert response.query_summary.total_matching == 0

    def test_update_media_buy_cannot_modify_other_principals_media_buy(self):
        """Test that update_media_buy rejects attempts to modify another principal's media buy.

        SECURITY: Principal B should NOT be able to update Principal A's media buy.
        """

        from src.core.main import _update_media_buy_impl

        mock_context_b = MockContext(auth_token="token-advertiser-b")

        # Principal B tries to update Principal A's media buy
        with patch("src.core.main.get_current_tenant", return_value={"tenant_id": "security_test_tenant"}):
            # _verify_principal should raise PermissionError
            with pytest.raises(PermissionError, match="does not own media buy"):
                _update_media_buy_impl(
                    media_buy_id="media_buy_a",  # Owned by Principal A!
                    buyer_ref="hacked_by_b",
                    context=mock_context_b,
                )

            # Verify media buy was NOT modified
            with get_db_session() as session:
                from sqlalchemy import select

                stmt = select(MediaBuy).filter_by(tenant_id="security_test_tenant", media_buy_id="media_buy_a")
                media_buy = session.scalars(stmt).first()

                assert media_buy.principal_id == "advertiser_a", "Media buy ownership changed!"
                assert media_buy.buyer_ref == "buyer_ref_a", "Media buy buyer_ref was modified!"

    def test_get_media_buy_delivery_cannot_see_other_principals_data(self):
        """Test that get_media_buy_delivery only returns data for owned media buys.

        SECURITY: Principal B should NOT see Principal A's media buy delivery data.
        """
        from src.core.main import _get_media_buy_delivery_impl
        from src.core.schemas import GetMediaBuyDeliveryRequest

        mock_context_b = MockContext(auth_token="token-advertiser-b")

        request = GetMediaBuyDeliveryRequest(
            media_buy_ids=["media_buy_a"],  # Owned by Principal A!
        )

        with patch("src.core.main.get_current_tenant", return_value={"tenant_id": "security_test_tenant"}):
            response = _get_media_buy_delivery_impl(req=request, context=mock_context_b)

            # Principal B should NOT see Principal A's media buy
            assert len(response.media_buy_deliveries) == 0, "Principal B should not see Principal A's delivery data!"

    def test_cross_tenant_isolation_also_enforced(self):
        """Test that principals from different tenants are isolated.

        SECURITY: Even if a principal somehow gets another tenant's data ID,
        they should not be able to access it.
        """
        # Create a second tenant with its own principal and creative
        with get_db_session() as session:
            tenant2 = create_tenant_with_timestamps(
                tenant_id="second_tenant",
                name="Second Tenant",
                subdomain="second-tenant",
                is_active=True,
                ad_server="mock",
            )
            session.add(tenant2)

            principal_c = Principal(
                tenant_id="second_tenant",
                principal_id="advertiser_c",
                name="Advertiser C",
                access_token="token-advertiser-c",
                platform_mappings={"mock": {"id": "advertiser_c"}},
            )
            session.add(principal_c)
            session.commit()

            creative_c = DBCreative(
                tenant_id="second_tenant",
                creative_id="creative_owned_by_c",
                principal_id="advertiser_c",
                name="Advertiser C Creative",
                format="display_300x250",
                agent_url="https://creative.adcontextprotocol.org/",
                status="approved",
                data={"url": "https://example.com/creative_c.jpg", "width": 300, "height": 250},
            )
            session.add(creative_c)
            session.commit()

        # Principal A (from first tenant) tries to access creative from second tenant
        from src.core.main import list_creatives as core_list_creatives_tool

        mock_context_a = MockContext(auth_token="token-advertiser-a")

        with patch("src.core.main.get_current_tenant", return_value={"tenant_id": "security_test_tenant"}):
            response = core_list_creatives_tool(context=mock_context_a)

            # Should only see their own creative, not creative_c from other tenant
            creative_ids = [c.creative_id for c in response.creatives]
            assert "creative_owned_by_a" in creative_ids or len(creative_ids) == 0
            assert "creative_owned_by_c" not in creative_ids, "Cross-tenant data leakage!"

    def test_sync_creatives_with_duplicate_creative_id_creates_separate_creatives(self):
        """Test that two principals can use the same creative_id without conflict.

        SECURITY: Creative IDs are scoped by (tenant_id, principal_id, creative_id).
        Multiple principals can have creatives with the same ID without interfering.
        """
        from src.core.main import _sync_creatives_impl

        # Both principals create creatives with the same creative_id
        creative_id = "shared_creative_id"

        # Principal A creates creative
        mock_context_a = MockContext(auth_token="token-advertiser-a")
        creatives_a = [
            {
                "creative_id": creative_id,
                "name": "Principal A's Creative",
                "format": "display_300x250",
                "url": "https://example.com/a.jpg",
            }
        ]

        with patch("src.core.main.get_current_tenant", return_value={"tenant_id": "security_test_tenant"}):
            response_a = _sync_creatives_impl(creatives=creatives_a, patch=False, context=mock_context_a)
            assert response_a.synced == 1

        # Principal B creates creative with SAME creative_id
        mock_context_b = MockContext(auth_token="token-advertiser-b")
        creatives_b = [
            {
                "creative_id": creative_id,
                "name": "Principal B's Creative",
                "format": "display_728x90",
                "url": "https://example.com/b.jpg",
            }
        ]

        with patch("src.core.main.get_current_tenant", return_value={"tenant_id": "security_test_tenant"}):
            response_b = _sync_creatives_impl(creatives=creatives_b, patch=False, context=mock_context_b)
            assert response_b.synced == 1

        # Verify both creatives exist independently
        with get_db_session() as session:
            from sqlalchemy import select

            stmt = select(DBCreative).filter_by(tenant_id="security_test_tenant", creative_id=creative_id)
            all_creatives = session.scalars(stmt).all()

            assert len(all_creatives) == 2, "Should have 2 separate creatives with same ID"

            creative_a = next(c for c in all_creatives if c.principal_id == "advertiser_a")
            creative_b = next(c for c in all_creatives if c.principal_id == "advertiser_b")

            assert creative_a.name == "Principal A's Creative"
            assert creative_b.name == "Principal B's Creative"
            assert creative_a.format == "display_300x250"
            assert creative_b.format == "display_728x90"
