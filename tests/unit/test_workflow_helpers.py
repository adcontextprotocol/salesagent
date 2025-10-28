"""Unit tests for workflow_helpers module.

Tests for shared workflow helper functions used across all adapters.
"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch, call

from src.core.helpers.workflow_helpers import (
    create_workflow_step,
    build_activation_action_details,
    build_manual_creation_action_details,
    build_approval_action_details,
    build_background_polling_action_details,
)


class TestCreateWorkflowStep:
    """Tests for create_workflow_step helper function."""

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_create_workflow_step_basic(self, mock_get_db_session):
        """Test basic workflow step creation."""
        # Setup mock session
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        result = create_workflow_step(
            tenant_id="tenant_123",
            principal_id="principal_123",
            step_type="approval",
            tool_name="activate_gam_order",
            request_data={"action_type": "activate"},
            status="approval",
            owner="publisher",
            media_buy_id="order_123",
            action="activate",
        )

        # Should return a step_id
        assert result is not None
        assert isinstance(result, str)
        assert result.startswith("a")  # approval prefix

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_create_workflow_step_different_types(self, mock_get_db_session):
        """Test workflow step creation with different step types."""
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        step_types = {
            "creation": "c",
            "approval": "a",
            "background_task": "b",
        }

        for step_type, expected_prefix in step_types.items():
            result = create_workflow_step(
                tenant_id="tenant_123",
                principal_id="principal_123",
                step_type=step_type,
                tool_name="test_tool",
                request_data={},
                status="approval",
                owner="publisher",
                media_buy_id="order_123",
                action="test",
            )

            assert result.startswith(expected_prefix)

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_create_workflow_step_with_logging(self, mock_get_db_session):
        """Test workflow step creation with logging function."""
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session
        mock_log = MagicMock()

        result = create_workflow_step(
            tenant_id="tenant_123",
            principal_id="principal_123",
            step_type="approval",
            tool_name="test_tool",
            request_data={"action": "test"},
            status="approval",
            owner="publisher",
            media_buy_id="order_123",
            action="test",
            log_func=mock_log,
        )

        # Should have called log function
        mock_log.assert_called()
        assert "Created workflow step" in mock_log.call_args[0][0]

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_create_workflow_step_with_audit_logger(self, mock_get_db_session):
        """Test workflow step creation with audit logger."""
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session
        mock_audit_logger = MagicMock()

        result = create_workflow_step(
            tenant_id="tenant_123",
            principal_id="principal_123",
            step_type="approval",
            tool_name="test_tool",
            request_data={},
            status="approval",
            owner="publisher",
            media_buy_id="order_123",
            action="test",
            audit_logger=mock_audit_logger,
        )

        # Should have called audit logger
        mock_audit_logger.log_success.assert_called()

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_create_workflow_step_with_transaction_details(self, mock_get_db_session):
        """Test workflow step creation with transaction details."""
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        transaction_details = {
            "gam_order_id": "order_123",
            "total_budget": 5000.0,
            "campaign_name": "Test Campaign",
        }

        result = create_workflow_step(
            tenant_id="tenant_123",
            principal_id="principal_123",
            step_type="creation",
            tool_name="create_gam_order",
            request_data={},
            status="approval",
            owner="publisher",
            media_buy_id="order_123",
            action="create",
            transaction_details=transaction_details,
        )

        # Should capture transaction details in the created workflow step
        assert result is not None

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_create_workflow_step_handles_database_error(self, mock_get_db_session):
        """Test workflow step creation handles database errors gracefully."""
        mock_get_db_session.return_value.__enter__.side_effect = Exception("DB connection failed")

        result = create_workflow_step(
            tenant_id="tenant_123",
            principal_id="principal_123",
            step_type="approval",
            tool_name="test_tool",
            request_data={},
            status="approval",
            owner="publisher",
            media_buy_id="order_123",
            action="test",
        )

        # Should return None on error
        assert result is None

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_create_workflow_step_creates_mapping(self, mock_get_db_session):
        """Test that workflow step creation creates object mapping."""
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        result = create_workflow_step(
            tenant_id="tenant_123",
            principal_id="principal_123",
            step_type="approval",
            tool_name="test_tool",
            request_data={},
            status="approval",
            owner="publisher",
            media_buy_id="order_123",
            action="activate",
        )

        # Verify that add() was called for all three objects (context, step, mapping)
        assert mock_session.add.call_count >= 3
        assert mock_session.commit.called


class TestBuildActivationActionDetails:
    """Tests for build_activation_action_details helper function."""

    def test_build_activation_action_details_basic(self):
        """Test basic activation action details building."""
        media_buy_id = "order_123"
        packages = [
            MagicMock(name="Package 1", impressions=1000000, cpm=10.0),
            MagicMock(name="Package 2", impressions=500000, cpm=15.0),
        ]

        result = build_activation_action_details(media_buy_id, packages)

        assert result["action_type"] == "activate_gam_order"
        assert result["order_id"] == "order_123"
        assert result["platform"] == "Google Ad Manager"
        assert result["automation_mode"] == "confirmation_required"
        assert "instructions" in result
        assert len(result["instructions"]) > 0
        assert "gam_order_url" in result
        assert "order_123" in result["gam_order_url"]

    def test_build_activation_action_details_includes_packages(self):
        """Test activation action details includes package information."""
        media_buy_id = "order_123"
        pkg1 = MagicMock()
        pkg1.name = "Package 1"
        pkg1.impressions = 1000000
        pkg1.cpm = 10.0

        pkg2 = MagicMock()
        pkg2.name = "Package 2"
        pkg2.impressions = 500000
        pkg2.cpm = 15.0

        packages = [pkg1, pkg2]

        result = build_activation_action_details(media_buy_id, packages)

        assert "packages" in result
        assert len(result["packages"]) == 2
        assert result["packages"][0]["name"] == "Package 1"
        assert result["packages"][0]["impressions"] == 1000000
        assert result["packages"][0]["cpm"] == 10.0

    def test_build_activation_action_details_next_action(self):
        """Test activation action details specifies next action."""
        result = build_activation_action_details("order_123", [])

        assert result["next_action_after_approval"] == "automatic_activation"


class TestBuildManualCreationActionDetails:
    """Tests for build_manual_creation_action_details helper function."""

    def test_build_manual_creation_action_details_basic(self):
        """Test basic manual creation action details building."""
        request = MagicMock()
        request.get_total_budget = MagicMock(return_value=5000.0)

        packages = [MagicMock(name="Package 1", impressions=1000000, cpm=10.0)]
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 31)
        media_buy_id = "order_123"
        order_name = "Test Campaign"

        result = build_manual_creation_action_details(
            request=request,
            packages=packages,
            start_time=start_time,
            end_time=end_time,
            media_buy_id=media_buy_id,
            order_name=order_name,
        )

        assert result["action_type"] == "create_gam_order"
        assert result["order_id"] == "order_123"
        assert result["campaign_name"] == "Test Campaign"
        assert result["total_budget"] == 5000.0
        assert result["automation_mode"] == "manual_creation_required"

    def test_build_manual_creation_action_details_flight_dates(self):
        """Test manual creation action details includes flight dates."""
        request = MagicMock()
        request.get_total_budget = MagicMock(return_value=5000.0)

        packages = [MagicMock(name="Package 1", impressions=1000000, cpm=10.0)]
        start_time = datetime(2024, 1, 1)
        end_time = datetime(2024, 1, 31)

        result = build_manual_creation_action_details(
            request=request,
            packages=packages,
            start_time=start_time,
            end_time=end_time,
            media_buy_id="order_123",
            order_name="Test Campaign",
        )

        assert "flight_start" in result
        assert "flight_end" in result
        assert "2024-01-01" in result["flight_start"]
        assert "2024-01-31" in result["flight_end"]

    def test_build_manual_creation_action_details_instructions(self):
        """Test manual creation action details includes clear instructions."""
        request = MagicMock()
        request.get_total_budget = MagicMock(return_value=5000.0)

        packages = [MagicMock(name="Package 1", impressions=1000000, cpm=10.0,
                            targeting_overlay=None)]

        result = build_manual_creation_action_details(
            request=request,
            packages=packages,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 31),
            media_buy_id="order_123",
            order_name="Test Campaign",
        )

        assert "instructions" in result
        assert len(result["instructions"]) > 0
        instructions_text = " ".join(result["instructions"]).lower()
        assert "create" in instructions_text
        assert "order" in instructions_text

    def test_build_manual_creation_action_details_next_action(self):
        """Test manual creation action details specifies next action."""
        request = MagicMock()
        request.get_total_budget = MagicMock(return_value=5000.0)

        result = build_manual_creation_action_details(
            request=request,
            packages=[],
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 31),
            media_buy_id="order_123",
            order_name="Test Campaign",
        )

        assert result["next_action_after_creation"] == "order_id_update_required"


class TestBuildApprovalActionDetails:
    """Tests for build_approval_action_details helper function."""

    def test_build_approval_action_details_basic(self):
        """Test basic approval action details building."""
        media_buy_id = "order_123"

        result = build_approval_action_details(media_buy_id)

        assert result["action_type"] == "creative_approval"
        assert result["order_id"] == "order_123"
        assert result["platform"] == "Google Ad Manager"
        assert result["automation_mode"] == "approval_required"
        assert "instructions" in result

    def test_build_approval_action_details_custom_type(self):
        """Test approval action details with custom approval type."""
        media_buy_id = "order_123"
        approval_type = "budget_approval"

        result = build_approval_action_details(media_buy_id, approval_type)

        assert result["action_type"] == "budget_approval"
        assert "budget approval" in result["instructions"][0].lower()

    def test_build_approval_action_details_next_action(self):
        """Test approval action details specifies next action."""
        result = build_approval_action_details("order_123")

        assert result["next_action_after_approval"] == "automatic_processing"

    def test_build_approval_action_details_gam_url(self):
        """Test approval action details includes GAM URL."""
        result = build_approval_action_details("order_123")

        assert "gam_order_url" in result
        assert "order_123" in result["gam_order_url"]


class TestBuildBackgroundPollingActionDetails:
    """Tests for build_background_polling_action_details helper function."""

    def test_build_background_polling_action_details_basic(self):
        """Test basic background polling action details building."""
        media_buy_id = "order_123"
        packages = [MagicMock(name="Package 1", impressions=1000000, cpm=10.0)]

        result = build_background_polling_action_details(media_buy_id, packages)

        assert result["automation_mode"] == "background_polling"
        assert result["order_id"] == "order_123"
        assert result["status"] == "working"
        assert "packages" in result

    def test_build_background_polling_action_details_includes_packages(self):
        """Test background polling includes package context."""
        media_buy_id = "order_123"
        packages = [
            MagicMock(name="Package 1", impressions=1000000, cpm=10.0),
            MagicMock(name="Package 2", impressions=500000, cpm=15.0),
        ]

        result = build_background_polling_action_details(media_buy_id, packages)

        assert "packages" in result
        assert len(result["packages"]) == 2

    def test_build_background_polling_action_details_polling_config(self):
        """Test background polling specifies polling configuration."""
        result = build_background_polling_action_details("order_123", [])

        assert "polling_interval_seconds" in result
        assert result["polling_interval_seconds"] == 30
        assert "max_polling_duration_minutes" in result
        assert result["max_polling_duration_minutes"] == 15

    def test_build_background_polling_action_details_custom_operation(self):
        """Test background polling with custom operation type."""
        media_buy_id = "order_123"
        packages = []
        operation = "custom_approval_check"

        result = build_background_polling_action_details(
            media_buy_id, packages, operation
        )

        assert result["action_type"] == "custom_approval_check"

    def test_build_background_polling_action_details_next_action(self):
        """Test background polling specifies automatic approval as next action."""
        result = build_background_polling_action_details("order_123", [])

        assert result["next_action"] == "automatic_approval_when_ready"


class TestWorkflowHelpersIntegration:
    """Integration tests for multiple workflow helpers working together."""

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_full_activation_workflow_creation(self, mock_get_db_session):
        """Test complete activation workflow creation."""
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        # Build action details
        packages = [MagicMock(name="Package 1", impressions=1000000, cpm=10.0)]
        action_details = build_activation_action_details("order_123", packages)

        # Create workflow step
        step_id = create_workflow_step(
            tenant_id="tenant_123",
            principal_id="principal_123",
            step_type="approval",
            tool_name="activate_gam_order",
            request_data=action_details,
            status="approval",
            owner="publisher",
            media_buy_id="order_123",
            action="activate",
        )

        assert step_id is not None
        assert step_id.startswith("a")

    @patch("src.core.helpers.workflow_helpers.get_db_session")
    def test_full_manual_creation_workflow(self, mock_get_db_session):
        """Test complete manual creation workflow creation."""
        mock_session = MagicMock()
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        # Build action details
        request = MagicMock()
        request.get_total_budget = MagicMock(return_value=5000.0)
        packages = [MagicMock(name="Package 1", impressions=1000000, cpm=10.0,
                            targeting_overlay=None)]

        action_details = build_manual_creation_action_details(
            request=request,
            packages=packages,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 31),
            media_buy_id="order_123",
            order_name="Test Campaign",
        )

        # Create workflow step
        step_id = create_workflow_step(
            tenant_id="tenant_123",
            principal_id="principal_123",
            step_type="creation",
            tool_name="create_gam_order",
            request_data=action_details,
            status="approval",
            owner="publisher",
            media_buy_id="order_123",
            action="create",
        )

        assert step_id is not None
        assert step_id.startswith("c")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
