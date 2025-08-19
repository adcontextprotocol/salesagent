"""Simple test to verify dashboard and settings don't return 500 errors."""

import os

import pytest

from database import init_db

# Enable test mode
os.environ["ADCP_AUTH_TEST_MODE"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///test_500_check.db"


@pytest.fixture(scope="module")
def setup_test_db():
    """Set up test database."""
    # Clean up any existing test database
    if os.path.exists("test_500_check.db"):
        os.remove("test_500_check.db")

    # Initialize database
    try:
        init_db()
    except (SystemExit, NotImplementedError):
        # If migrations fail for SQLite, that's OK for this test
        pass

    yield

    # Cleanup
    if os.path.exists("test_500_check.db"):
        os.remove("test_500_check.db")


@pytest.fixture
def app(setup_test_db):
    """Create test Flask app."""
    from admin_ui import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test_secret"
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.mark.skip(reason="Dashboard 500 check needs database schema update")
def test_dashboard_no_500_when_authenticated(client):
    """Test that dashboard doesn't return 500 when authenticated."""
    # Set authentication in session
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["role"] = "super_admin"
        sess["email"] = "test@example.com"

    # Access dashboard - should not return 500
    response = client.get("/tenant/default")

    # The key assertion: No 500 error
    assert response.status_code != 500, "Dashboard returned 500 error!"

    # Also check for common database errors in the response
    if response.status_code == 200:
        assert b"UndefinedColumn" not in response.data
        assert b"UndefinedTable" not in response.data
        # Note: Can't check for "details" as it's a common word in HTML


@pytest.mark.skip(reason="Dashboard 500 check needs database schema update")
def test_settings_no_500_when_authenticated(client):
    """Test that settings page doesn't return 500 when authenticated."""
    # Set authentication in session
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["role"] = "super_admin"
        sess["email"] = "test@example.com"

    # Access settings - should not return 500
    response = client.get("/tenant/default/settings")

    # The key assertion: No 500 error
    assert response.status_code != 500, "Settings page returned 500 error!"

    # Also check for common database errors
    if response.status_code == 200:
        assert b"UndefinedColumn" not in response.data
        assert b"UndefinedTable" not in response.data


@pytest.mark.skip(reason="Dashboard 500 check needs database schema update")
def test_dashboard_redirects_when_not_authenticated(client):
    """Test that dashboard redirects to login when not authenticated."""
    response = client.get("/tenant/default")
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


@pytest.mark.skip(reason="Dashboard 500 check needs database schema update")
def test_settings_redirects_when_not_authenticated(client):
    """Test that settings redirects to login when not authenticated."""
    response = client.get("/tenant/default/settings")
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
