"""
Unit tests for GAMSyncManager class.

Tests sync orchestration, status tracking, error handling, scheduling,
and database integration for GAM synchronization operations.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from src.adapters.gam.managers.sync import GAMSyncManager
from src.core.database.models import SyncJob


class TestGAMSyncManager:
    """Test suite for GAMSyncManager sync orchestration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock()
        self.mock_inventory_manager = Mock()
        self.mock_orders_manager = Mock()
        self.tenant_id = "test_tenant_123"

        self.sync_manager = GAMSyncManager(
            self.mock_client_manager,
            self.mock_inventory_manager,
            self.mock_orders_manager,
            self.tenant_id,
            dry_run=False,
        )

    def test_init_with_valid_parameters(self):
        """Test initialization with valid parameters."""
        sync_manager = GAMSyncManager(
            self.mock_client_manager,
            self.mock_inventory_manager,
            self.mock_orders_manager,
            self.tenant_id,
            dry_run=True,
        )

        assert sync_manager.client_manager == self.mock_client_manager
        assert sync_manager.inventory_manager == self.mock_inventory_manager
        assert sync_manager.orders_manager == self.mock_orders_manager
        assert sync_manager.tenant_id == self.tenant_id
        assert sync_manager.dry_run is True
        assert sync_manager.sync_timeout == timedelta(minutes=30)
        assert sync_manager.retry_attempts == 3
        assert sync_manager.retry_delay == timedelta(minutes=5)

    def test_sync_inventory_success(self):
        """Test successful inventory synchronization."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "sync_123"

        # Mock inventory sync result
        mock_sync_result = {
            "tenant_id": self.tenant_id,
            "sync_time": datetime.now().isoformat(),
            "duration_seconds": 120,
            "ad_units": {"total": 15, "active": 12},
            "placements": {"total": 8, "active": 6},
            "labels": {"total": 5, "active": 5},
            "custom_targeting": {"total_keys": 10, "total_values": 150},
            "audience_segments": {"total": 25},
        }
        self.mock_inventory_manager.sync_all_inventory.return_value = mock_sync_result

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
            patch("src.adapters.gam.managers.sync.GAMInventoryService") as mock_inventory_service_class,
        ):

            mock_get_recent.return_value = None  # No recent sync
            mock_create_job.return_value = mock_sync_job

            # Mock inventory service
            mock_inventory_service = Mock()
            mock_inventory_service_class.return_value = mock_inventory_service

            # Mock discovery instance
            mock_discovery = Mock()
            self.mock_inventory_manager._get_discovery.return_value = mock_discovery

            result = self.sync_manager.sync_inventory(mock_session, force=False)

            assert result["sync_id"] == "sync_123"
            assert result["status"] == "completed"
            assert result["summary"] == mock_sync_result

            # Verify sync job status updates
            assert mock_sync_job.status == "completed"
            assert mock_sync_job.completed_at is not None

            # Verify inventory service called
            mock_inventory_service._save_inventory_to_db.assert_called_once_with(self.tenant_id, mock_discovery)

    def test_sync_inventory_with_recent_sync_not_forced(self):
        """Test inventory sync when recent sync exists and not forced."""
        mock_session = Mock(spec=Session)

        recent_sync_data = {
            "sync_id": "recent_sync_456",
            "status": "completed",
            "summary": {"message": "Recent sync found"},
        }

        with patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent:
            mock_get_recent.return_value = recent_sync_data

            result = self.sync_manager.sync_inventory(mock_session, force=False)

            assert result == recent_sync_data
            # Should not create new sync job
            self.mock_inventory_manager.sync_all_inventory.assert_not_called()

    def test_sync_inventory_forced_ignores_recent_sync(self):
        """Test inventory sync with force=True ignores recent sync."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "forced_sync_789"

        recent_sync_data = {"sync_id": "recent_sync", "status": "completed"}
        mock_sync_result = {
            "tenant_id": self.tenant_id,
            "sync_time": datetime.now().isoformat(),
            "ad_units": {"total": 20},
        }

        self.mock_inventory_manager.sync_all_inventory.return_value = mock_sync_result

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
            patch("src.adapters.gam.managers.sync.GAMInventoryService"),
        ):

            mock_get_recent.return_value = recent_sync_data
            mock_create_job.return_value = mock_sync_job

            result = self.sync_manager.sync_inventory(mock_session, force=True)

            assert result["sync_id"] == "forced_sync_789"
            # Should not check for recent sync
            mock_get_recent.assert_not_called()

    def test_sync_inventory_dry_run_mode(self):
        """Test inventory sync in dry-run mode."""
        self.sync_manager.dry_run = True
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "dry_run_sync"

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
        ):

            mock_get_recent.return_value = None
            mock_create_job.return_value = mock_sync_job

            result = self.sync_manager.sync_inventory(mock_session)

            assert result["sync_id"] == "dry_run_sync"
            assert result["status"] == "completed"
            assert result["summary"]["dry_run"] is True

            # Should not call real inventory sync
            self.mock_inventory_manager.sync_all_inventory.assert_not_called()

    def test_sync_inventory_failure(self):
        """Test inventory sync failure handling."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)

        self.mock_inventory_manager.sync_all_inventory.side_effect = Exception("Sync failed")

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
        ):

            mock_get_recent.return_value = None
            mock_create_job.return_value = mock_sync_job

            with pytest.raises(Exception, match="Sync failed"):
                self.sync_manager.sync_inventory(mock_session)

            # Verify sync job marked as failed
            assert mock_sync_job.status == "failed"
            assert mock_sync_job.error_message == "Sync failed"
            assert mock_sync_job.completed_at is not None

    def test_sync_orders_success(self):
        """Test successful orders synchronization."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "orders_sync_123"

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
        ):

            mock_get_recent.return_value = None
            mock_create_job.return_value = mock_sync_job

            result = self.sync_manager.sync_orders(mock_session, force=False)

            assert result["sync_id"] == "orders_sync_123"
            assert result["status"] == "completed"
            assert "orders" in result["summary"]
            assert "line_items" in result["summary"]

    def test_sync_orders_dry_run_mode(self):
        """Test orders sync in dry-run mode."""
        self.sync_manager.dry_run = True
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
        ):

            mock_get_recent.return_value = None
            mock_create_job.return_value = mock_sync_job

            result = self.sync_manager.sync_orders(mock_session)

            assert result["summary"]["dry_run"] is True

    def test_sync_orders_failure(self):
        """Test orders sync failure handling."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
        ):

            mock_get_recent.return_value = None
            mock_create_job.return_value = mock_sync_job
            mock_create_job.side_effect = Exception("Database error")

            with pytest.raises(Exception, match="Database error"):
                self.sync_manager.sync_orders(mock_session)

    def test_sync_full_success(self):
        """Test successful full synchronization."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "full_sync_123"

        inventory_result = {"sync_id": "inv_sync", "summary": {"ad_units": {"total": 15}}}
        orders_result = {"sync_id": "ord_sync", "summary": {"orders": {"total": 5}}}

        with (
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
            patch.object(self.sync_manager, "sync_inventory") as mock_sync_inventory,
            patch.object(self.sync_manager, "sync_orders") as mock_sync_orders,
        ):

            mock_create_job.return_value = mock_sync_job
            mock_sync_inventory.return_value = inventory_result
            mock_sync_orders.return_value = orders_result

            result = self.sync_manager.sync_full(mock_session, force=False)

            assert result["sync_id"] == "full_sync_123"
            assert result["status"] == "completed"
            assert "inventory" in result["summary"]
            assert "orders" in result["summary"]
            assert "duration_seconds" in result["summary"]

            # Verify both syncs called with force=True
            mock_sync_inventory.assert_called_once_with(mock_session, force=True)
            mock_sync_orders.assert_called_once_with(mock_session, force=True)

    def test_sync_full_failure(self):
        """Test full sync failure handling."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)

        with (
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
            patch.object(self.sync_manager, "sync_inventory") as mock_sync_inventory,
        ):

            mock_create_job.return_value = mock_sync_job
            mock_sync_inventory.side_effect = Exception("Inventory sync failed")

            with pytest.raises(Exception, match="Inventory sync failed"):
                self.sync_manager.sync_full(mock_session)

            assert mock_sync_job.status == "failed"
            assert mock_sync_job.error_message == "Inventory sync failed"

    def test_get_sync_status_found(self):
        """Test getting sync status for existing sync job."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "sync_123"
        mock_sync_job.tenant_id = self.tenant_id
        mock_sync_job.sync_type = "inventory"
        mock_sync_job.status = "completed"
        mock_sync_job.started_at = datetime(2025, 1, 15, 10, 0, 0)
        mock_sync_job.completed_at = datetime(2025, 1, 15, 10, 5, 0)
        mock_sync_job.triggered_by = "api"
        mock_sync_job.summary = json.dumps({"ad_units": {"total": 15}})
        mock_sync_job.error_message = None

        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_sync_job

        result = self.sync_manager.get_sync_status(mock_session, "sync_123")

        assert result["sync_id"] == "sync_123"
        assert result["tenant_id"] == self.tenant_id
        assert result["sync_type"] == "inventory"
        assert result["status"] == "completed"
        assert result["started_at"] == "2025-01-15T10:00:00"
        assert result["completed_at"] == "2025-01-15T10:05:00"
        assert result["duration_seconds"] == 300.0
        assert result["triggered_by"] == "api"
        assert result["summary"] == {"ad_units": {"total": 15}}
        assert "error" not in result

    def test_get_sync_status_with_error(self):
        """Test getting sync status for failed sync job."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "failed_sync"
        mock_sync_job.tenant_id = self.tenant_id
        mock_sync_job.sync_type = "inventory"
        mock_sync_job.status = "failed"
        mock_sync_job.started_at = datetime(2025, 1, 15, 10, 0, 0)
        mock_sync_job.completed_at = datetime(2025, 1, 15, 10, 2, 0)
        mock_sync_job.triggered_by = "api"
        mock_sync_job.summary = None
        mock_sync_job.error_message = "Connection timeout"

        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_sync_job

        result = self.sync_manager.get_sync_status(mock_session, "failed_sync")

        assert result["status"] == "failed"
        assert result["error"] == "Connection timeout"
        assert "summary" not in result

    def test_get_sync_status_not_found(self):
        """Test getting sync status for non-existent sync job."""
        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        result = self.sync_manager.get_sync_status(mock_session, "nonexistent")

        assert result is None

    def test_get_sync_history_success(self):
        """Test successful sync history retrieval."""
        mock_session = Mock(spec=Session)

        # Mock sync jobs
        mock_job_1 = Mock(spec=SyncJob)
        mock_job_1.sync_id = "sync_1"
        mock_job_1.sync_type = "inventory"
        mock_job_1.status = "completed"
        mock_job_1.started_at = datetime(2025, 1, 15, 10, 0, 0)
        mock_job_1.completed_at = datetime(2025, 1, 15, 10, 5, 0)
        mock_job_1.triggered_by = "api"
        mock_job_1.summary = json.dumps({"ad_units": {"total": 15}})
        mock_job_1.error_message = None

        mock_job_2 = Mock(spec=SyncJob)
        mock_job_2.sync_id = "sync_2"
        mock_job_2.sync_type = "orders"
        mock_job_2.status = "failed"
        mock_job_2.started_at = datetime(2025, 1, 15, 9, 0, 0)
        mock_job_2.completed_at = datetime(2025, 1, 15, 9, 1, 0)
        mock_job_2.triggered_by = "scheduler"
        mock_job_2.summary = None
        mock_job_2.error_message = "API error"

        # Mock query chain
        mock_query = Mock()
        mock_query.filter_by.return_value = mock_query
        mock_query.count.return_value = 2
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [mock_job_1, mock_job_2]

        mock_session.query.return_value = mock_query

        result = self.sync_manager.get_sync_history(mock_session, limit=10, offset=0)

        assert result["total"] == 2
        assert result["limit"] == 10
        assert result["offset"] == 0
        assert len(result["results"]) == 2

        # Check first result
        job_1_result = result["results"][0]
        assert job_1_result["sync_id"] == "sync_1"
        assert job_1_result["status"] == "completed"
        assert job_1_result["summary"] == {"ad_units": {"total": 15}}
        assert "error" not in job_1_result

        # Check second result
        job_2_result = result["results"][1]
        assert job_2_result["sync_id"] == "sync_2"
        assert job_2_result["status"] == "failed"
        assert job_2_result["error"] == "API error"

    def test_get_sync_history_with_status_filter(self):
        """Test sync history retrieval with status filter."""
        mock_session = Mock(spec=Session)

        mock_query = Mock()
        mock_query.filter_by.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = []

        mock_session.query.return_value = mock_query

        self.sync_manager.get_sync_history(mock_session, status_filter="failed")

        # Verify status filter was applied
        filter_calls = mock_query.filter_by.call_args_list
        assert any("status" in str(call) for call in filter_calls)

    def test_needs_sync_true(self):
        """Test needs_sync returns True when sync is needed."""
        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = self.sync_manager.needs_sync(mock_session, "inventory", max_age_hours=24)

        assert result is True

    def test_needs_sync_false(self):
        """Test needs_sync returns False when recent sync exists."""
        mock_session = Mock(spec=Session)
        mock_recent_job = Mock(spec=SyncJob)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_recent_job

        result = self.sync_manager.needs_sync(mock_session, "inventory", max_age_hours=24)

        assert result is False

    def test_get_recent_sync_found_running(self):
        """Test _get_recent_sync with running sync job."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "running_sync"
        mock_sync_job.status = "running"

        mock_session.query.return_value.filter.return_value.first.return_value = mock_sync_job

        result = self.sync_manager._get_recent_sync(mock_session, "inventory")

        assert result["sync_id"] == "running_sync"
        assert result["status"] == "running"
        assert result["message"] == "Sync already in progress"

    def test_get_recent_sync_found_completed(self):
        """Test _get_recent_sync with completed sync job."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "completed_sync"
        mock_sync_job.status = "completed"
        mock_sync_job.completed_at = datetime(2025, 1, 15, 10, 0, 0)
        mock_sync_job.summary = json.dumps({"ad_units": {"total": 15}})

        mock_session.query.return_value.filter.return_value.first.return_value = mock_sync_job

        result = self.sync_manager._get_recent_sync(mock_session, "inventory")

        assert result["sync_id"] == "completed_sync"
        assert result["status"] == "completed"
        assert result["completed_at"] == "2025-01-15T10:00:00"
        assert result["summary"] == {"ad_units": {"total": 15}}
        assert result["message"] == "Recent sync exists"

    def test_get_recent_sync_not_found(self):
        """Test _get_recent_sync when no recent sync exists."""
        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = self.sync_manager._get_recent_sync(mock_session, "inventory")

        assert result is None

    def test_create_sync_job_success(self):
        """Test successful sync job creation."""
        mock_session = Mock(spec=Session)

        with patch("src.adapters.gam.managers.sync.datetime") as mock_datetime:
            mock_now = datetime(2025, 1, 15, 10, 0, 0)
            mock_datetime.now.return_value = mock_now

            sync_job = self.sync_manager._create_sync_job(mock_session, "inventory", "api")

            assert sync_job.sync_id.startswith("sync_test_tenant_123_inventory_")
            assert sync_job.tenant_id == self.tenant_id
            assert sync_job.adapter_type == "google_ad_manager"
            assert sync_job.sync_type == "inventory"
            assert sync_job.status == "pending"
            assert sync_job.triggered_by == "api"
            assert sync_job.triggered_by_id == "api_sync"

            mock_session.add.assert_called_once_with(sync_job)
            mock_session.commit.assert_called_once()

    def test_get_sync_stats_success(self):
        """Test successful sync statistics retrieval."""
        mock_session = Mock(spec=Session)

        # Mock status counts
        def mock_count_side_effect(*args, **kwargs):
            # This is a simplified mock - in reality you'd check the filter conditions
            return {"pending": 1, "running": 0, "completed": 5, "failed": 2}.get("pending", 0)

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.count.side_effect = [1, 0, 5, 2]  # pending, running, completed, failed
        mock_session.query.return_value = mock_query

        # Mock recent failures
        mock_failed_job = Mock(spec=SyncJob)
        mock_failed_job.sync_id = "failed_sync"
        mock_failed_job.sync_type = "inventory"
        mock_failed_job.started_at = datetime(2025, 1, 15, 10, 0, 0)
        mock_failed_job.error_message = "Connection timeout"

        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_failed_job]

        result = self.sync_manager.get_sync_stats(mock_session, hours=24)

        assert result["tenant_id"] == self.tenant_id
        assert result["status_counts"]["pending"] == 1
        assert result["status_counts"]["running"] == 0
        assert result["status_counts"]["completed"] == 5
        assert result["status_counts"]["failed"] == 2
        assert len(result["recent_failures"]) == 1
        assert result["recent_failures"][0]["sync_id"] == "failed_sync"


class TestGAMSyncManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock()
        self.mock_inventory_manager = Mock()
        self.mock_orders_manager = Mock()
        self.tenant_id = "test_tenant_123"
        self.sync_manager = GAMSyncManager(
            self.mock_client_manager,
            self.mock_inventory_manager,
            self.mock_orders_manager,
            self.tenant_id,
            dry_run=False,
        )

    def test_sync_inventory_with_malformed_summary(self):
        """Test inventory sync when summary cannot be JSON serialized."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)

        # Create a summary with non-serializable content
        class NonSerializable:
            pass

        malformed_summary = {"object": NonSerializable()}
        self.mock_inventory_manager.sync_all_inventory.return_value = malformed_summary

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
            patch("src.adapters.gam.managers.sync.GAMInventoryService"),
            patch("src.adapters.gam.managers.sync.json.dumps") as mock_json_dumps,
        ):

            mock_get_recent.return_value = None
            mock_create_job.return_value = mock_sync_job
            mock_json_dumps.side_effect = TypeError("Object not serializable")

            with pytest.raises(TypeError):
                self.sync_manager.sync_inventory(mock_session)

    def test_sync_job_creation_with_very_long_tenant_id(self):
        """Test sync job creation with very long tenant ID."""
        long_tenant_id = "x" * 500
        sync_manager = GAMSyncManager(
            self.mock_client_manager,
            self.mock_inventory_manager,
            self.mock_orders_manager,
            long_tenant_id,
            dry_run=False,
        )

        mock_session = Mock(spec=Session)

        sync_job = sync_manager._create_sync_job(mock_session, "inventory", "api")

        # Sync ID should be created despite long tenant ID
        assert long_tenant_id in sync_job.sync_id
        assert sync_job.tenant_id == long_tenant_id

    def test_get_sync_history_with_zero_limit(self):
        """Test sync history retrieval with zero limit."""
        mock_session = Mock(spec=Session)

        mock_query = Mock()
        mock_query.filter_by.return_value = mock_query
        mock_query.count.return_value = 10
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = []

        mock_session.query.return_value = mock_query

        result = self.sync_manager.get_sync_history(mock_session, limit=0)

        assert result["total"] == 10
        assert result["limit"] == 0
        assert result["results"] == []

    def test_get_sync_history_with_large_offset(self):
        """Test sync history retrieval with offset larger than total results."""
        mock_session = Mock(spec=Session)

        mock_query = Mock()
        mock_query.filter_by.return_value = mock_query
        mock_query.count.return_value = 5
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = []

        mock_session.query.return_value = mock_query

        result = self.sync_manager.get_sync_history(mock_session, limit=10, offset=100)

        assert result["total"] == 5
        assert result["offset"] == 100
        assert result["results"] == []

    def test_needs_sync_with_zero_max_age(self):
        """Test needs_sync with zero max_age_hours."""
        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = self.sync_manager.needs_sync(mock_session, "inventory", max_age_hours=0)

        assert result is True

    def test_get_sync_status_with_incomplete_sync_job(self):
        """Test getting sync status for sync job missing optional fields."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)
        mock_sync_job.sync_id = "incomplete_sync"
        mock_sync_job.tenant_id = self.tenant_id
        mock_sync_job.sync_type = "inventory"
        mock_sync_job.status = "running"
        mock_sync_job.started_at = datetime(2025, 1, 15, 10, 0, 0)
        mock_sync_job.completed_at = None  # Still running
        mock_sync_job.triggered_by = "api"
        mock_sync_job.summary = None  # No summary yet
        mock_sync_job.error_message = None  # No error

        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_sync_job

        result = self.sync_manager.get_sync_status(mock_session, "incomplete_sync")

        assert result["sync_id"] == "incomplete_sync"
        assert result["status"] == "running"
        assert "completed_at" not in result
        assert "duration_seconds" not in result
        assert "summary" not in result
        assert "error" not in result

    def test_sync_full_partial_failure_still_updates_job(self):
        """Test that full sync failure still updates sync job status."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)

        with (
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
            patch.object(self.sync_manager, "sync_inventory") as mock_sync_inventory,
        ):

            mock_create_job.return_value = mock_sync_job
            mock_sync_inventory.side_effect = Exception("Inventory sync error")

            with pytest.raises(Exception, match="Inventory sync error"):
                self.sync_manager.sync_full(mock_session)

            # Verify job was marked as failed
            assert mock_sync_job.status == "failed"
            assert mock_sync_job.error_message == "Inventory sync error"
            assert mock_sync_job.completed_at is not None

    def test_get_sync_stats_with_no_failures(self):
        """Test sync statistics when there are no recent failures."""
        mock_session = Mock(spec=Session)

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.count.side_effect = [0, 0, 1, 0]  # No pending, running, or failed
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []  # No recent failures
        mock_session.query.return_value = mock_query

        result = self.sync_manager.get_sync_stats(mock_session)

        assert result["status_counts"]["failed"] == 0
        assert result["recent_failures"] == []

    def test_empty_tenant_id_handling(self):
        """Test sync manager behavior with empty tenant ID."""
        sync_manager = GAMSyncManager(
            self.mock_client_manager,
            self.mock_inventory_manager,
            self.mock_orders_manager,
            "",  # Empty tenant ID
            dry_run=False,
        )

        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        result = sync_manager.get_sync_status(mock_session, "sync_123")

        assert result is None  # Should still work, just won't find anything

    def test_unicode_characters_in_error_messages(self):
        """Test handling of Unicode characters in error messages."""
        mock_session = Mock(spec=Session)
        mock_sync_job = Mock(spec=SyncJob)

        unicode_error = "Sync failed: 测试错误 🚨"
        self.mock_inventory_manager.sync_all_inventory.side_effect = Exception(unicode_error)

        with (
            patch.object(self.sync_manager, "_get_recent_sync") as mock_get_recent,
            patch.object(self.sync_manager, "_create_sync_job") as mock_create_job,
        ):

            mock_get_recent.return_value = None
            mock_create_job.return_value = mock_sync_job

            with pytest.raises(Exception, match="测试错误"):
                self.sync_manager.sync_inventory(mock_session)

            # Unicode error message should be preserved
            assert mock_sync_job.error_message == unicode_error
