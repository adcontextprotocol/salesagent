"""Unit tests for GAM AXE segment integration with inventory sync.

Tests that the inventory sync automatically ensures the AXE custom targeting key exists
and that the key name is read from adapter configuration.
"""

from unittest.mock import MagicMock, patch

from src.adapters.gam.managers.inventory import GAMInventoryManager


def test_sync_inventory_does_not_auto_create_axe_key():
    """Test that sync_all_inventory does NOT automatically create AXE keys.

    This ensures the two-step workflow: sync first, then select key.
    """
    mock_client_manager = MagicMock()
    mock_client = MagicMock()
    mock_client_manager.get_client.return_value = mock_client

    manager = GAMInventoryManager(mock_client_manager, "tenant_123", dry_run=False)

    with patch.object(manager, "ensure_axe_custom_targeting_key") as mock_ensure:
        with patch.object(manager, "_get_discovery") as mock_discovery:
            mock_discovery_instance = MagicMock()
            mock_discovery_instance.sync_all.return_value = {
                "tenant_id": "tenant_123",
                "ad_units": {"total": 10},
                "custom_targeting": {"total_keys": 5, "total_values": 100},
            }
            mock_discovery.return_value = mock_discovery_instance

            # Run sync
            result = manager.sync_all_inventory(fetch_values=True)

            # Verify ensure_axe_custom_targeting_key was NOT called
            mock_ensure.assert_not_called()

            # Verify sync_all was called
            mock_discovery_instance.sync_all.assert_called_once()


def test_get_axe_key_name_reads_from_config():
    """Test that _get_axe_key_name reads from adapter configuration."""
    mock_client_manager = MagicMock()
    manager = GAMInventoryManager(mock_client_manager, "tenant_123", dry_run=False)

    # Mock database session and adapter config
    mock_adapter_config = MagicMock()
    mock_adapter_config.gam_axe_custom_targeting_key = "custom_axe_key"

    with patch("src.core.database.database_session.get_db_session") as mock_get_session:
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_session
        mock_session.scalars.return_value.first.return_value = mock_adapter_config
        mock_get_session.return_value = mock_session

        # Get key name
        key_name = manager._get_axe_key_name()

        # Verify it returns the configured key name
        assert key_name == "custom_axe_key"


def test_get_axe_key_name_defaults_to_axe_segment():
    """Test that _get_axe_key_name defaults to 'axe_segment' if not configured."""
    mock_client_manager = MagicMock()
    manager = GAMInventoryManager(mock_client_manager, "tenant_123", dry_run=False)

    # Mock database session with no adapter config
    with patch("src.core.database.database_session.get_db_session") as mock_get_session:
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_session
        mock_session.scalars.return_value.first.return_value = None
        mock_get_session.return_value = mock_session

        # Get key name
        key_name = manager._get_axe_key_name()

        # Verify it returns the default
        assert key_name == "axe_segment"


def test_get_axe_key_name_handles_database_error():
    """Test that _get_axe_key_name handles database errors gracefully."""
    mock_client_manager = MagicMock()
    manager = GAMInventoryManager(mock_client_manager, "tenant_123", dry_run=False)

    # Mock database session to raise exception
    with patch("src.core.database.database_session.get_db_session") as mock_get_session:
        mock_get_session.side_effect = Exception("Database connection error")

        # Get key name - should return default and not raise
        key_name = manager._get_axe_key_name()

        # Verify it returns the default
        assert key_name == "axe_segment"


def test_ensure_axe_custom_targeting_key_can_be_called_manually():
    """Test that publishers can manually ensure AXE key exists if needed.

    This is for cases where publishers want to create a new custom targeting key
    for AXE segments rather than using an existing one.
    """
    mock_client_manager = MagicMock()
    mock_client = MagicMock()
    mock_client_manager.get_client.return_value = mock_client

    # Mock GAM service
    mock_service = MagicMock()
    mock_client.GetService.return_value = mock_service

    # Mock response - key already exists
    mock_service.getCustomTargetingKeysByStatement.return_value = {
        "results": [{"id": 12345, "name": "axe_segment", "type": "FREEFORM"}]
    }

    manager = GAMInventoryManager(mock_client_manager, "tenant_123", dry_run=False)

    # Manually call ensure method
    result = manager.ensure_axe_custom_targeting_key("axe_segment")

    # Verify it returns the existing key
    assert result["key_id"] == "12345"
    assert result["name"] == "axe_segment"
    assert result["created"] is False  # Not created, already existed
