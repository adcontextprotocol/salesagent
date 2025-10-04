"""Integration tests for workflow step webhook delivery.

Tests the critical path: WorkflowStep → Context → principal_id → webhook delivery
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.database.models import (
    ObjectWorkflowMapping,
    WorkflowStep,
)
from src.core.database.models import (
    PushNotificationConfig as DBPushNotificationConfig,
)
from src.services.push_notification_service import push_notification_service


class TestWorkflowWebhookIntegration:
    """Test workflow step webhook delivery integration."""

    @pytest.mark.asyncio
    async def test_send_workflow_step_notification_finds_principal_id_via_context(self):
        """Test that send_workflow_step_notification correctly accesses step.context.principal_id.

        This is the CRITICAL test for the bug fix:
        - WorkflowStep does NOT have principal_id field
        - Must access via step.context.principal_id relationship
        """

        # Mock database session and models
        with (
            patch("src.services.push_notification_service.get_db_session") as mock_db_session,
            patch("httpx.AsyncClient") as mock_http_client,
        ):

            # Create mock context with principal_id
            mock_context = Mock()
            mock_context.tenant_id = "tenant_test"
            mock_context.principal_id = "prin_test123"  # This is what we need to access

            # Create mock workflow step with context relationship
            mock_step = Mock(spec=WorkflowStep)
            mock_step.step_id = "step_test"
            mock_step.context_id = "ctx_test"
            mock_step.context = mock_context  # CRITICAL: step.context.principal_id

            # Create mock media buy mapping
            mock_mapping = Mock(spec=ObjectWorkflowMapping)
            mock_mapping.object_id = "mb_test123"
            mock_mapping.object_type = "media_buy"

            # Create mock webhook config
            mock_webhook_config = Mock(spec=DBPushNotificationConfig)
            mock_webhook_config.id = "webhook_123"
            mock_webhook_config.url = "https://buyer.example.com/webhook"
            mock_webhook_config.authentication_type = "bearer"
            mock_webhook_config.authentication_token = "test_token"
            mock_webhook_config.validation_token = None

            # Mock database session context manager
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)

            # Mock database queries
            def query_side_effect(model):
                mock_query = Mock()
                if model == WorkflowStep:
                    # First query: get step by step_id
                    mock_query.filter_by.return_value.first.return_value = mock_step
                    # Second query: get all steps by context_id
                    mock_query.filter.return_value.all.return_value = [mock_step]
                elif model == ObjectWorkflowMapping:
                    mock_query.filter.return_value.first.return_value = mock_mapping
                elif model == DBPushNotificationConfig:
                    # CRITICAL: This query uses tenant_id and principal_id from step.context
                    mock_query.filter_by.return_value.all.return_value = [mock_webhook_config]
                return mock_query

            mock_session.query.side_effect = query_side_effect
            mock_db_session.return_value = mock_session

            # Mock HTTP client
            mock_response = Mock()
            mock_response.status_code = 200
            mock_http_instance = Mock()
            mock_http_instance.post = AsyncMock(return_value=mock_response)
            mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
            mock_http_instance.__aexit__ = AsyncMock(return_value=None)
            mock_http_client.return_value = mock_http_instance

            # Call send_workflow_step_notification
            result = await push_notification_service.send_workflow_step_notification(
                workflow_id="ctx_test",  # Actually context_id
                step_id="step_test",
                step_status="completed",
                step_type="create_media_buy",
            )

            # Verify webhook was sent
            assert result["sent"] == 1, f"Expected 1 webhook sent, got {result}"
            assert result["failed"] == 0

            # Verify HTTP POST was called with correct webhook URL
            mock_http_instance.post.assert_called_once()
            call_args = mock_http_instance.post.call_args

            # Verify webhook URL
            assert call_args[0][0] == "https://buyer.example.com/webhook"

            # Verify payload contains correct principal_id from step.context
            payload = call_args[1]["json"]
            assert payload["principal_id"] == "prin_test123", "Should use principal_id from step.context"
            assert payload["tenant_id"] == "tenant_test", "Should use tenant_id from step.context"

    @pytest.mark.asyncio
    async def test_send_workflow_step_notification_handles_missing_context(self):
        """Test that send_workflow_step_notification handles step without context gracefully."""

        with patch("src.services.push_notification_service.get_db_session") as mock_db_session:

            # Create mock workflow step WITHOUT context
            mock_step = Mock(spec=WorkflowStep)
            mock_step.step_id = "step_test"
            mock_step.context = None  # Missing context

            # Mock database session
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)

            # Mock queries
            def query_side_effect(model):
                mock_query = Mock()
                if model == WorkflowStep:
                    mock_query.filter_by.return_value.first.return_value = mock_step
                    mock_query.filter.return_value.all.return_value = [mock_step]
                elif model == ObjectWorkflowMapping:
                    # No mapping found
                    mock_query.filter.return_value.first.return_value = None
                return mock_query

            mock_session.query.side_effect = query_side_effect
            mock_db_session.return_value = mock_session

            # Call should handle missing context gracefully
            result = await push_notification_service.send_workflow_step_notification(
                workflow_id="ctx_test",
                step_id="step_test",
                step_status="completed",
                step_type="create_media_buy",
            )

            # Should return empty result, not crash
            assert result["sent"] == 0
            assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_send_workflow_step_notification_no_webhook_configs(self):
        """Test workflow notification when no webhook configs are registered."""

        with patch("src.services.push_notification_service.get_db_session") as mock_db_session:

            # Create mock context
            mock_context = Mock()
            mock_context.tenant_id = "tenant_test"
            mock_context.principal_id = "prin_test"

            # Create mock workflow step
            mock_step = Mock(spec=WorkflowStep)
            mock_step.step_id = "step_test"
            mock_step.context = mock_context

            # Create mock mapping
            mock_mapping = Mock(spec=ObjectWorkflowMapping)
            mock_mapping.object_id = "mb_test"

            # Mock database session
            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)

            # Mock queries
            def query_side_effect(model):
                mock_query = Mock()
                if model == WorkflowStep:
                    mock_query.filter_by.return_value.first.return_value = mock_step
                    mock_query.filter.return_value.all.return_value = [mock_step]
                elif model == ObjectWorkflowMapping:
                    mock_query.filter.return_value.first.return_value = mock_mapping
                elif model == DBPushNotificationConfig:
                    # NO webhook configs found
                    mock_query.filter_by.return_value.all.return_value = []
                return mock_query

            mock_session.query.side_effect = query_side_effect
            mock_db_session.return_value = mock_session

            # Call send_workflow_step_notification
            result = await push_notification_service.send_workflow_step_notification(
                workflow_id="ctx_test",
                step_id="step_test",
                step_status="completed",
                step_type="create_media_buy",
            )

            # Should return no webhooks sent
            assert result["sent"] == 0
            assert result["failed"] == 0
            assert len(result["configs"]) == 0

    @pytest.mark.asyncio
    async def test_send_workflow_step_notification_http_failure_retries(self):
        """Test that webhook delivery retries on HTTP failure."""

        with (
            patch("src.services.push_notification_service.get_db_session") as mock_db_session,
            patch("httpx.AsyncClient") as mock_http_client,
        ):

            # Setup mocks (same as first test)
            mock_context = Mock()
            mock_context.tenant_id = "tenant_test"
            mock_context.principal_id = "prin_test"

            mock_step = Mock(spec=WorkflowStep)
            mock_step.step_id = "step_test"
            mock_step.context = mock_context

            mock_mapping = Mock(spec=ObjectWorkflowMapping)
            mock_mapping.object_id = "mb_test"

            mock_webhook_config = Mock(spec=DBPushNotificationConfig)
            mock_webhook_config.id = "webhook_123"
            mock_webhook_config.url = "https://buyer.example.com/webhook"
            mock_webhook_config.authentication_type = "bearer"
            mock_webhook_config.authentication_token = "test_token"
            mock_webhook_config.validation_token = None

            mock_session = Mock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)

            def query_side_effect(model):
                mock_query = Mock()
                if model == WorkflowStep:
                    mock_query.filter_by.return_value.first.return_value = mock_step
                    mock_query.filter.return_value.all.return_value = [mock_step]
                elif model == ObjectWorkflowMapping:
                    mock_query.filter.return_value.first.return_value = mock_mapping
                elif model == DBPushNotificationConfig:
                    mock_query.filter_by.return_value.all.return_value = [mock_webhook_config]
                return mock_query

            mock_session.query.side_effect = query_side_effect
            mock_db_session.return_value = mock_session

            # Mock HTTP client to fail first 2 times, then succeed
            mock_responses = [
                Mock(status_code=500),  # First attempt
                Mock(status_code=500),  # Second attempt
                Mock(status_code=200),  # Third attempt succeeds
            ]

            mock_http_instance = Mock()
            mock_http_instance.post = AsyncMock(side_effect=mock_responses)
            mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
            mock_http_instance.__aexit__ = AsyncMock(return_value=None)
            mock_http_client.return_value = mock_http_instance

            # Call send_workflow_step_notification
            result = await push_notification_service.send_workflow_step_notification(
                workflow_id="ctx_test",
                step_id="step_test",
                step_status="completed",
                step_type="create_media_buy",
            )

            # Should succeed after retries
            assert result["sent"] == 1
            assert result["failed"] == 0

            # Should have made 3 HTTP attempts
            assert mock_http_instance.post.call_count == 3
