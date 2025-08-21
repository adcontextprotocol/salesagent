"""Unit test to verify AdapterConfig schema doesn't have config column."""


def test_adapter_config_has_no_config_column():
    """Verify AdapterConfig model doesn't have a config column.

    This test documents the schema change that caused the bug where
    ai_product_service.py was trying to access adapter_config_row.config
    which no longer exists.
    """
    from src.core.database.models import AdapterConfig

    # This test documents the schema change that caused the bug
    assert not hasattr(AdapterConfig, "config"), "AdapterConfig should not have a 'config' column"

    # Verify expected columns exist
    assert hasattr(AdapterConfig, "adapter_type")
    assert hasattr(AdapterConfig, "mock_dry_run")
    assert hasattr(AdapterConfig, "gam_network_code")
    assert hasattr(AdapterConfig, "gam_refresh_token")
    assert hasattr(AdapterConfig, "gam_company_id")
    assert hasattr(AdapterConfig, "gam_trafficker_id")
    assert hasattr(AdapterConfig, "gam_manual_approval_required")
    assert hasattr(AdapterConfig, "kevel_network_id")
    assert hasattr(AdapterConfig, "kevel_api_key")
    assert hasattr(AdapterConfig, "kevel_manual_approval_required")
    assert hasattr(AdapterConfig, "triton_station_id")
    assert hasattr(AdapterConfig, "triton_api_key")
