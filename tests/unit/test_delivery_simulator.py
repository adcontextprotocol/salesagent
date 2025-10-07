"""Unit tests for delivery simulator service."""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.services.delivery_simulator import DeliverySimulator


class TestDeliverySimulator:
    """Test cases for DeliverySimulator."""

    @pytest.fixture
    def simulator(self):
        """Create a fresh simulator instance."""
        return DeliverySimulator()

    @pytest.fixture
    def mock_push_service(self):
        """Mock push notification service."""
        with patch("src.services.delivery_simulator.push_notification_service") as mock:
            mock.send_task_status_notification = AsyncMock(return_value={"sent": 1, "failed": 0})
            yield mock

    def test_simulator_initialization(self, simulator):
        """Test simulator initializes correctly."""
        assert simulator._active_simulations == {}
        assert simulator._stop_signals == {}

    def test_start_simulation_creates_thread(self, simulator, mock_push_service):
        """Test that starting simulation creates a background thread."""
        media_buy_id = "buy_test_123"
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(hours=1)

        simulator.start_simulation(
            media_buy_id=media_buy_id,
            tenant_id="tenant_1",
            principal_id="principal_1",
            start_time=start_time,
            end_time=end_time,
            total_budget=1000.0,
            time_acceleration=3600,
            update_interval_seconds=0.1,  # Fast for testing
        )

        # Check thread was created
        assert media_buy_id in simulator._active_simulations
        assert media_buy_id in simulator._stop_signals
        assert simulator._active_simulations[media_buy_id].is_alive()

        # Cleanup
        simulator.stop_simulation(media_buy_id)
        time.sleep(0.2)  # Give thread time to stop

    def test_stop_simulation(self, simulator, mock_push_service):
        """Test that stopping simulation sets stop signal."""
        media_buy_id = "buy_test_456"
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(hours=1)

        simulator.start_simulation(
            media_buy_id=media_buy_id,
            tenant_id="tenant_1",
            principal_id="principal_1",
            start_time=start_time,
            end_time=end_time,
            total_budget=1000.0,
            time_acceleration=3600,
            update_interval_seconds=0.1,
        )

        # Stop simulation
        simulator.stop_simulation(media_buy_id)

        # Check stop signal was set
        assert simulator._stop_signals[media_buy_id].is_set()

        # Give thread time to cleanup
        time.sleep(0.2)

        # Thread should have cleaned up
        assert media_buy_id not in simulator._active_simulations

    def test_duplicate_simulation_prevented(self, simulator, mock_push_service):
        """Test that duplicate simulations for same media buy are prevented."""
        media_buy_id = "buy_test_789"
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(hours=1)

        # Start first simulation
        simulator.start_simulation(
            media_buy_id=media_buy_id,
            tenant_id="tenant_1",
            principal_id="principal_1",
            start_time=start_time,
            end_time=end_time,
            total_budget=1000.0,
            time_acceleration=3600,
            update_interval_seconds=0.1,
        )

        # Try to start duplicate
        simulator.start_simulation(
            media_buy_id=media_buy_id,
            tenant_id="tenant_1",
            principal_id="principal_1",
            start_time=start_time,
            end_time=end_time,
            total_budget=1000.0,
            time_acceleration=3600,
            update_interval_seconds=0.1,
        )

        # Should only have one thread
        assert media_buy_id in simulator._active_simulations
        active_count = sum(1 for t in simulator._active_simulations.values() if t.is_alive())
        assert active_count == 1

        # Cleanup
        simulator.stop_simulation(media_buy_id)
        time.sleep(0.2)

    def test_webhook_payload_structure(self, simulator, mock_push_service):
        """Test that webhook payloads have correct structure."""
        media_buy_id = "buy_test_webhook"
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(hours=2)

        simulator.start_simulation(
            media_buy_id=media_buy_id,
            tenant_id="tenant_1",
            principal_id="principal_1",
            start_time=start_time,
            end_time=end_time,
            total_budget=1000.0,
            time_acceleration=7200,  # 1 sec = 2 hours (complete in 1 second)
            update_interval_seconds=0.5,  # Should fire 2-3 webhooks
        )

        # Wait for simulation to complete
        time.sleep(2.0)

        # Check webhooks were sent
        assert mock_push_service.send_task_status_notification.called

        # Get first webhook call
        first_call = mock_push_service.send_task_status_notification.call_args_list[0]
        kwargs = first_call[1]

        # Verify structure
        assert kwargs["tenant_id"] == "tenant_1"
        assert kwargs["principal_id"] == "principal_1"
        assert kwargs["task_id"] == media_buy_id

        task_data = kwargs["task_data"]

        # Verify AdCP V2.3 compliant format
        assert "adcp_version" in task_data
        assert task_data["adcp_version"] == "2.3.0"

        assert "notification_type" in task_data
        assert task_data["notification_type"] in ["scheduled", "final"]

        assert "sequence_number" in task_data
        assert task_data["sequence_number"] >= 1

        assert "reporting_period" in task_data
        assert "start" in task_data["reporting_period"]
        assert "end" in task_data["reporting_period"]

        assert "currency" in task_data
        assert task_data["currency"] == "USD"

        assert "media_buy_deliveries" in task_data
        assert len(task_data["media_buy_deliveries"]) == 1

        # Check media buy delivery structure
        delivery = task_data["media_buy_deliveries"][0]
        assert "media_buy_id" in delivery
        assert delivery["media_buy_id"] == media_buy_id
        assert "status" in delivery
        assert delivery["status"] in ["pending", "active", "completed"]
        assert "totals" in delivery
        assert "impressions" in delivery["totals"]
        assert "spend" in delivery["totals"]
        assert "by_package" in delivery

    def test_time_acceleration_calculation(self, simulator, mock_push_service):
        """Test that time acceleration works correctly."""
        media_buy_id = "buy_test_acceleration"
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(hours=24)  # 24-hour campaign

        # With acceleration of 86400 (1 sec = 1 day), should complete in 1 second
        simulator.start_simulation(
            media_buy_id=media_buy_id,
            tenant_id="tenant_1",
            principal_id="principal_1",
            start_time=start_time,
            end_time=end_time,
            total_budget=1000.0,
            time_acceleration=86400,  # 1 sec = 1 day
            update_interval_seconds=0.5,
        )

        # Wait for simulation to complete
        time.sleep(2.0)

        # Should have completed
        assert media_buy_id not in simulator._active_simulations

        # Check final webhook had completed notification_type
        last_call = mock_push_service.send_task_status_notification.call_args_list[-1]
        task_data = last_call[1]["task_data"]
        assert task_data["notification_type"] == "final"

    def test_delivery_metrics_progression(self, simulator, mock_push_service):
        """Test that delivery metrics progress realistically."""
        media_buy_id = "buy_test_metrics"
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(hours=10)
        total_budget = 5000.0

        simulator.start_simulation(
            media_buy_id=media_buy_id,
            tenant_id="tenant_1",
            principal_id="principal_1",
            start_time=start_time,
            end_time=end_time,
            total_budget=total_budget,
            time_acceleration=36000,  # 1 sec = 10 hours (complete in 1 second)
            update_interval_seconds=0.25,  # 4 updates
        )

        # Wait for simulation to complete
        time.sleep(2.0)

        # Analyze webhook progression
        calls = mock_push_service.send_task_status_notification.call_args_list

        # Should have multiple calls
        assert len(calls) >= 2

        # Check first and last
        first_data = calls[0][1]["task_data"]
        last_data = calls[-1][1]["task_data"]

        # First should have 0 spend/impressions (AdCP format)
        first_delivery = first_data["media_buy_deliveries"][0]
        assert first_delivery["totals"]["spend"] == 0
        assert first_delivery["totals"]["impressions"] == 0
        assert first_data["notification_type"] == "scheduled"

        # Last should have full spend/impressions
        last_delivery = last_data["media_buy_deliveries"][0]
        assert last_delivery["totals"]["spend"] > 0
        assert last_delivery["totals"]["impressions"] > 0
        assert last_data["notification_type"] == "final"

        # Spend should not exceed budget significantly
        assert last_delivery["totals"]["spend"] <= total_budget * 1.1  # Allow 10% variance

    def test_cleanup_after_completion(self, simulator, mock_push_service):
        """Test that simulator cleans up after completion."""
        media_buy_id = "buy_test_cleanup"
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(hours=1)

        simulator.start_simulation(
            media_buy_id=media_buy_id,
            tenant_id="tenant_1",
            principal_id="principal_1",
            start_time=start_time,
            end_time=end_time,
            total_budget=1000.0,
            time_acceleration=3600,  # 1 sec = 1 hour
            update_interval_seconds=0.5,
        )

        # Wait for completion
        time.sleep(2.0)

        # Should have cleaned up
        assert media_buy_id not in simulator._active_simulations
        assert media_buy_id not in simulator._stop_signals
