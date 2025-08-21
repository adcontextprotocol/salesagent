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
        sess["user"] = {"email": "admin@example.com", "role": "super_admin"}
        sess["role"] = "super_admin"
        sess["authenticated"] = True
        sess["email"] = "admin@example.com"

    # Mock database response and super admin check
    with (
        patch("src.admin.blueprints.core.get_db_session") as mock_db,
        patch("src.admin.utils.is_super_admin", return_value=True),
    ):
        mock_session = MagicMock()
        from datetime import datetime

        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "test_tenant"
        mock_tenant.name = "Test Tenant"
        mock_tenant.subdomain = "test"
        mock_tenant.is_active = True
        mock_tenant.created_at = datetime(2024, 1, 1, 0, 0, 0)

        mock_session.query().order_by().all.return_value = [mock_tenant]
        mock_db().__enter__.return_value = mock_session

        response = client.get("/")
        assert response.status_code == 200
        assert b"Test Tenant" in response.data

    # Test with tenant admin (should redirect to tenant dashboard)
    with client.session_transaction() as sess:
        sess["user"] = {"email": "user@example.com", "role": "tenant_admin"}
        sess["role"] = "tenant_admin"
        sess["tenant_id"] = "test_tenant"
        sess["authenticated"] = True
        sess["email"] = "user@example.com"

    response = client.get("/")
    assert response.status_code == 302
    assert "/tenant/test_tenant" in response.location

    print("✅ Index route works in refactored app!")


if __name__ == "__main__":
    print("Testing index route in refactored app...")
    test_index_route_in_refactored_app()
    print("\n🎉 Index route test passed!")
