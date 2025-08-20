"""
Test for the tenant name update form field fix.

This test ensures that the form field naming issue that caused
"Tenant name is required" errors has been resolved.
"""

from unittest.mock import MagicMock, patch

from flask import Flask


def test_tenant_name_form_field_mapping():
    """
    Test that the settings.py update_general function correctly
    maps the 'name' form field to tenant_name variable.

    This prevents the "Tenant name is required" error.
    """
    # Import the function we're testing
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from src.admin.blueprints.settings import update_general

    # Create a mock Flask app context
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-key"

    with app.test_request_context("/tenant/test123/settings/general", method="POST", data={"name": "Test Tenant Name"}):

        # Mock the database session and tenant
        with patch("src.admin.blueprints.settings.get_db_session") as mock_session:
            with patch("src.admin.blueprints.settings.flash") as mock_flash:
                with patch("src.admin.blueprints.settings.redirect") as mock_redirect:

                    # Set up mock objects
                    mock_tenant = MagicMock()
                    mock_db = MagicMock()
                    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_tenant
                    mock_session.return_value.__enter__.return_value = mock_db
                    mock_session.return_value.__exit__.return_value = None

                    # Set up session mock to simulate logged-in user
                    with patch("src.admin.blueprints.settings.session", {"tenant_id": "test123"}):

                        # Call the function
                        result = update_general("test123")

                        # Verify that the tenant name was set correctly
                        # This should NOT fail with "Tenant name is required"
                        assert mock_tenant.name == "Test Tenant Name"

                        # Verify success flash message was called
                        mock_flash.assert_called_with("General settings updated successfully", "success")

                        # Verify database commit was called
                        mock_db.commit.assert_called_once()

                        print("✅ Form field mapping test passed")


def test_empty_tenant_name_validation():
    """Test that empty tenant name is properly validated."""
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from src.admin.blueprints.settings import update_general

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-key"

    with app.test_request_context("/tenant/test123/settings/general", method="POST", data={"name": ""}):  # Empty name

        with patch("src.admin.blueprints.settings.get_db_session") as mock_session:
            with patch("src.admin.blueprints.settings.flash") as mock_flash:
                with patch("src.admin.blueprints.settings.redirect") as mock_redirect:
                    with patch("src.admin.blueprints.settings.session", {"tenant_id": "test123"}):

                        # Call the function
                        result = update_general("test123")

                        # Verify error flash message was called
                        mock_flash.assert_called_with("Tenant name is required", "error")

                        print("✅ Empty name validation test passed")


def test_whitespace_only_tenant_name():
    """Test that whitespace-only tenant name is treated as empty."""
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from src.admin.blueprints.settings import update_general

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-key"

    with app.test_request_context(
        "/tenant/test123/settings/general", method="POST", data={"name": "   "}
    ):  # Whitespace only

        with patch("src.admin.blueprints.settings.get_db_session") as mock_session:
            with patch("src.admin.blueprints.settings.flash") as mock_flash:
                with patch("src.admin.blueprints.settings.redirect") as mock_redirect:
                    with patch("src.admin.blueprints.settings.session", {"tenant_id": "test123"}):

                        # Call the function
                        result = update_general("test123")

                        # Verify error flash message was called (whitespace stripped)
                        mock_flash.assert_called_with("Tenant name is required", "error")

                        print("✅ Whitespace validation test passed")


if __name__ == "__main__":
    test_tenant_name_form_field_mapping()
    test_empty_tenant_name_validation()
    test_whitespace_only_tenant_name()
    print("🎉 All form field fix tests passed!")
