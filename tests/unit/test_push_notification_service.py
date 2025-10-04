"""Unit tests for push notification service."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.push_notification_service import PushNotificationService


class TestPushNotificationService:
    """Test suite for PushNotificationService."""

    @pytest.fixture
    def service(self):
        """Create push notification service instance."""
        return PushNotificationService(timeout_seconds=5, max_retries=2)

    @pytest.fixture
    def mock_config(self):
        """Create mock push notification config."""
        config = Mock()
        config.id = "pnc_test123"
        config.url = "https://buyer.example.com/webhooks/adcp"
        config.authentication_type = "bearer"
        config.authentication_token = "test_token_12345"
        config.validation_token = "validation_xyz"
        return config

    @pytest.mark.asyncio
    async def test_send_task_status_notification_no_configs(self, service):
        """Test sending notification when no configs exist."""
        with patch("src.services.push_notification_service.get_db_session") as mock_db:
            # Mock database session to return no configs
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_session.query().filter_by().all.return_value = []
            mock_db.return_value = mock_session

            result = await service.send_task_status_notification(
                tenant_id="tenant_test", principal_id="prin_test", task_id="task_123", task_status="completed"
            )

            assert result["sent"] == 0
            assert result["failed"] == 0
            assert len(result["configs"]) == 0

    @pytest.mark.asyncio
    async def test_send_task_status_notification_success(self, service, mock_config):
        """Test successful notification delivery."""
        with (
            patch("src.services.push_notification_service.get_db_session") as mock_db,
            patch("httpx.AsyncClient") as mock_client,
        ):

            # Mock database session
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_session.query().filter_by().all.return_value = [mock_config]
            mock_db.return_value = mock_session

            # Mock HTTP client
            mock_response = Mock()
            mock_response.status_code = 200
            mock_http_instance = Mock()
            mock_http_instance.post = AsyncMock(return_value=mock_response)
            mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
            mock_http_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http_instance

            result = await service.send_task_status_notification(
                tenant_id="tenant_test",
                principal_id="prin_test",
                task_id="task_123",
                task_status="completed",
                task_data={"media_buy_id": "mb_123"},
            )

            assert result["sent"] == 1
            assert result["failed"] == 0
            assert "pnc_test123" in result["configs"]
            assert len(result["errors"]) == 0

            # Verify HTTP client was called correctly
            mock_http_instance.post.assert_called_once()
            call_args = mock_http_instance.post.call_args
            assert call_args[0][0] == "https://buyer.example.com/webhooks/adcp"
            assert "Authorization" in call_args[1]["headers"]
            assert call_args[1]["headers"]["Authorization"] == "Bearer test_token_12345"

    @pytest.mark.asyncio
    async def test_send_task_status_notification_failure(self, service, mock_config):
        """Test notification delivery failure."""
        with (
            patch("src.services.push_notification_service.get_db_session") as mock_db,
            patch("httpx.AsyncClient") as mock_client,
        ):

            # Mock database session
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_session.query().filter_by().all.return_value = [mock_config]
            mock_db.return_value = mock_session

            # Mock HTTP client to return failure
            mock_response = Mock()
            mock_response.status_code = 500
            mock_http_instance = Mock()
            mock_http_instance.post = AsyncMock(return_value=mock_response)
            mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
            mock_http_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http_instance

            result = await service.send_task_status_notification(
                tenant_id="tenant_test", principal_id="prin_test", task_id="task_123", task_status="failed"
            )

            assert result["sent"] == 0
            assert result["failed"] == 1
            assert "pnc_test123" in result["errors"]

            # Should have retried (2 attempts total)
            assert mock_http_instance.post.call_count == 2

    @pytest.mark.asyncio
    async def test_deliver_webhook_with_authentication_types(self, service, mock_config):
        """Test webhook delivery with different authentication types."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock successful HTTP response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_http_instance = Mock()
            mock_http_instance.post = AsyncMock(return_value=mock_response)
            mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
            mock_http_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http_instance

            # Test bearer token
            mock_config.authentication_type = "bearer"
            result = await service._deliver_webhook(mock_config, {"test": "data"})
            assert result is True
            call_headers = mock_http_instance.post.call_args[1]["headers"]
            assert call_headers["Authorization"] == "Bearer test_token_12345"

            # Test basic auth
            mock_config.authentication_type = "basic"
            result = await service._deliver_webhook(mock_config, {"test": "data"})
            assert result is True
            call_headers = mock_http_instance.post.call_args[1]["headers"]
            assert call_headers["Authorization"] == "Basic test_token_12345"

            # Test no auth
            mock_config.authentication_type = None
            result = await service._deliver_webhook(mock_config, {"test": "data"})
            assert result is True
            call_headers = mock_http_instance.post.call_args[1]["headers"]
            assert "Authorization" not in call_headers

    @pytest.mark.asyncio
    async def test_send_media_buy_status_notification(self, service):
        """Test media buy status notification."""
        with (
            patch("src.services.push_notification_service.get_db_session") as mock_db,
            patch.object(service, "send_task_status_notification", new_callable=AsyncMock) as mock_send,
        ):

            # Mock database session with media buy
            mock_media_buy = Mock()
            mock_media_buy.media_buy_id = "mb_123"
            mock_media_buy.buyer_ref = "buyer_ref_123"
            mock_media_buy.tenant_id = "tenant_test"
            mock_media_buy.principal_id = "prin_test"

            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_session.query().filter_by().first.return_value = mock_media_buy
            mock_db.return_value = mock_session

            # Mock send_task_status_notification
            mock_send.return_value = {"sent": 1, "failed": 0, "configs": ["pnc_test"], "errors": {}}

            result = await service.send_media_buy_status_notification(
                media_buy_id="mb_123", status="completed", message="Campaign completed successfully"
            )

            assert result["sent"] == 1
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args[1]
            assert call_kwargs["tenant_id"] == "tenant_test"
            assert call_kwargs["principal_id"] == "prin_test"
            assert call_kwargs["task_id"] == "mb_123"
            assert call_kwargs["task_status"] == "completed"
            assert "message" in call_kwargs["task_data"]
