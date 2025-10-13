"""Integration tests for delivery simulator restart_active_simulations functionality.

Tests the critical join logic between MediaBuy and PushNotificationConfig tables.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import MediaBuy, Principal, PushNotificationConfig, Tenant
from src.services.delivery_simulator import delivery_simulator


@pytest.mark.requires_db
class TestDeliverySimulatorRestart:
    """Test delivery simulator restart with proper database joins."""

    @pytest.fixture
    def test_tenant(self, integration_db):
        """Create test tenant."""
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id="test_tenant_restart", name="Test Tenant for Restart", subdomain="test-restart", config={}
            )
            session.add(tenant)
            session.commit()
            yield tenant.tenant_id

            # Cleanup
            stmt = select(Tenant).filter_by(tenant_id="test_tenant_restart")
            tenant = session.scalars(stmt).first()
            if tenant:
                session.delete(tenant)
                session.commit()

    @pytest.fixture
    def test_principal(self, test_tenant):
        """Create test principal."""
        with get_db_session() as session:
            principal = Principal(
                tenant_id=test_tenant,
                principal_id="test_principal_restart",
                name="Test Principal",
                access_token="test_token_restart",
                platform_mappings={},
            )
            session.add(principal)
            session.commit()
            yield principal.principal_id

    @pytest.fixture
    def test_webhook_config(self, test_tenant, test_principal):
        """Create test push notification config."""
        with get_db_session() as session:
            config = PushNotificationConfig(
                tenant_id=test_tenant,
                principal_id=test_principal,
                session_id=None,  # Principal-level config
                url="https://example.com/webhook",
                authentication_type="bearer",
                authentication_token="test_auth_token",
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(config)
            session.commit()
            yield config.id

    def test_restart_finds_media_buys_with_principal_webhook(self, test_tenant, test_principal, test_webhook_config):
        """Test that restart_active_simulations correctly joins MediaBuy with PushNotificationConfig via principal_id."""
        # Create multiple media buys for same principal
        media_buy_ids = []
        now = datetime.now(UTC)

        with get_db_session() as session:
            for i in range(3):
                media_buy = MediaBuy(
                    tenant_id=test_tenant,
                    media_buy_id=f"buy_restart_test_{i}",
                    principal_id=test_principal,
                    status="active",  # Active status
                    config={},
                    start_date=now,
                    end_date=now + timedelta(days=7),
                    total_budget=1000.0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(media_buy)
                media_buy_ids.append(media_buy.media_buy_id)

            session.commit()

        try:
            # Call restart_active_simulations - should find all 3 media buys
            delivery_simulator.restart_active_simulations()

            # Verify simulations were started for all media buys
            active_count = 0
            for media_buy_id in media_buy_ids:
                if media_buy_id in delivery_simulator._active_simulations:
                    active_count += 1

            # Should have started simulations for all active media buys with webhooks
            assert active_count == 3, f"Expected 3 simulations, found {active_count}"

        finally:
            # Cleanup: Stop all simulations
            for media_buy_id in media_buy_ids:
                delivery_simulator.stop_simulation(media_buy_id)

            # Cleanup: Delete media buys
            with get_db_session() as session:
                for media_buy_id in media_buy_ids:
                    stmt = select(MediaBuy).filter_by(tenant_id=test_tenant, media_buy_id=media_buy_id)
                    media_buy = session.scalars(stmt).first()
                    if media_buy:
                        session.delete(media_buy)
                session.commit()

    def test_restart_ignores_media_buys_without_webhook(self, test_tenant, test_principal):
        """Test that media buys without webhook configs are not restarted."""
        now = datetime.now(UTC)
        media_buy_id = "buy_no_webhook"

        with get_db_session() as session:
            # Create media buy WITHOUT webhook config (no PushNotificationConfig for this principal)
            # First create a principal without webhook
            principal_no_webhook = Principal(
                tenant_id=test_tenant,
                principal_id="principal_no_webhook",
                name="Principal Without Webhook",
                access_token="token_no_webhook",
                platform_mappings={},
            )
            session.add(principal_no_webhook)

            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id="principal_no_webhook",
                status="active",
                config={},
                start_date=now,
                end_date=now + timedelta(days=7),
                total_budget=1000.0,
                created_at=now,
                updated_at=now,
            )
            session.add(media_buy)
            session.commit()

        try:
            # Call restart - should NOT start simulation for this media buy
            delivery_simulator.restart_active_simulations()

            # Verify no simulation was started
            assert media_buy_id not in delivery_simulator._active_simulations

        finally:
            # Cleanup
            with get_db_session() as session:
                stmt = select(MediaBuy).filter_by(tenant_id=test_tenant, media_buy_id=media_buy_id)
                media_buy = session.scalars(stmt).first()
                if media_buy:
                    session.delete(media_buy)

                stmt = select(Principal).filter_by(tenant_id=test_tenant, principal_id="principal_no_webhook")
                principal = session.scalars(stmt).first()
                if principal:
                    session.delete(principal)

                session.commit()

    def test_restart_join_cardinality(self, test_tenant, test_principal, test_webhook_config):
        """Test that join produces correct 1:N cardinality (one webhook config → many media buys)."""
        media_buy_ids = []
        now = datetime.now(UTC)

        with get_db_session() as session:
            # Create 5 media buys for same principal (should all use same webhook config)
            for i in range(5):
                media_buy = MediaBuy(
                    tenant_id=test_tenant,
                    media_buy_id=f"buy_cardinality_{i}",
                    principal_id=test_principal,
                    status="active",
                    config={},
                    start_date=now,
                    end_date=now + timedelta(days=7),
                    total_budget=1000.0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(media_buy)
                media_buy_ids.append(media_buy.media_buy_id)
            session.commit()

        try:
            # Verify the join query returns correct number of results
            with get_db_session() as session:
                stmt = (
                    select(MediaBuy, PushNotificationConfig)
                    .join(
                        PushNotificationConfig,
                        (MediaBuy.tenant_id == PushNotificationConfig.tenant_id)
                        & (MediaBuy.principal_id == PushNotificationConfig.principal_id),
                    )
                    .where(MediaBuy.status.in_(["pending", "active", "working"]))
                    .where(PushNotificationConfig.is_active)
                )
                results = session.execute(stmt).all()

                # Should find all 5 media buys joined with the single webhook config
                assert len(results) == 5, f"Expected 5 results from join, got {len(results)}"

                # All should reference the same webhook config
                webhook_config_ids = {result[1].id for result in results}
                assert len(webhook_config_ids) == 1, "All media buys should use same webhook config"
                assert test_webhook_config in webhook_config_ids

        finally:
            # Cleanup
            for media_buy_id in media_buy_ids:
                delivery_simulator.stop_simulation(media_buy_id)

            with get_db_session() as session:
                for media_buy_id in media_buy_ids:
                    stmt = select(MediaBuy).filter_by(tenant_id=test_tenant, media_buy_id=media_buy_id)
                    media_buy = session.scalars(stmt).first()
                    if media_buy:
                        session.delete(media_buy)
                session.commit()
