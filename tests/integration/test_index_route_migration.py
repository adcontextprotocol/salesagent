"""Test that index route works in the refactored structure."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_index_route_in_refactored_app():
    """Test that index route works in the refactored app."""
    from unittest.mock import MagicMock, patch

    from src.admin.app import create_app

    app, socketio = create_app()
    client = app.test_client()

    # Test without auth (should redirect)
    response = client.get("/")
    assert response.status_code == 302  # Redirect to login

    # Test with super admin auth
    with client.session_transaction() as sess:
        sess["user"] = "admin@example.com"
        sess["role"] = "super_admin"

    # Mock database response
    with patch("src.admin.app.get_db_session") as mock_db:
        mock_session = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "test_tenant"
        mock_tenant.name = "Test Tenant"
        mock_tenant.subdomain = "test"
        mock_tenant.is_active = True
        mock_tenant.created_at = "2024-01-01T00:00:00"

        mock_session.query().order_by().all.return_value = [mock_tenant]
        mock_db().__enter__.return_value = mock_session

        response = client.get("/")
        assert response.status_code == 200
        assert b"Test Tenant" in response.data

    # Test with tenant admin (should redirect to tenant dashboard)
    with client.session_transaction() as sess:
        sess["user"] = "user@example.com"
        sess["role"] = "tenant_admin"
        sess["tenant_id"] = "test_tenant"

    response = client.get("/")
    assert response.status_code == 302
    assert "/tenant/test_tenant" in response.location

    print("✅ Index route works in refactored app!")


if __name__ == "__main__":
    print("Testing index route in refactored app...")
    test_index_route_in_refactored_app()
    print("\n🎉 Index route test passed!")
