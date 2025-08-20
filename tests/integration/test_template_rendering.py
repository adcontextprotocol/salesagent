"""Integration tests for template rendering with url_for.

These tests catch BuildError exceptions during template rendering that
occur when url_for() calls reference non-existent endpoints during
incremental refactoring.

Key approach: PROPAGATE_EXCEPTIONS=True catches template errors
that would otherwise be masked by status code checks.
"""

import pytest
from flask import url_for
from jinja2 import TemplateRuntimeError
from werkzeug.routing.exceptions import BuildError

from admin_ui import app


@pytest.mark.requires_db
@pytest.mark.integration
@pytest.mark.ui
class TestTemplateRendering:
    """Test that templates render without BuildError exceptions."""

    def test_products_page_renders_without_builderror(self, authenticated_admin_session, test_tenant_with_data):
        """Test that the products page renders without url_for BuildError."""
        response = authenticated_admin_session.get(f"/tenant/{test_tenant_with_data['tenant_id']}/products")

        # Must be 200 - not redirect or error
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # Verify substantial content rendered (not error page)
        assert len(response.data) > 1000, "Response too small - likely an error page"

        # Check for template-specific elements (both empty and populated states)
        assert (
            b"Product Management" in response.data or b"Products -" in response.data or b"Setup Wizard" in response.data
        ), "Missing products page content"

        # The critical test: "Back to Home" link should work (when products exist)
        # OR the page should show empty state (no products)
        assert (
            b"Back to Home" in response.data or b"Product Setup Wizard" in response.data
        ), "Missing navigation or empty state"

        # Verify no error indicators
        assert b"500" not in response.data
        assert b"Internal Server Error" not in response.data
        assert b"BuildError" not in response.data

    def test_creative_formats_page_renders_without_builderror(self, authenticated_admin_session, test_tenant_with_data):
        """Test that the creative formats page renders without url_for BuildError."""
        response = authenticated_admin_session.get(f"/tenant/{test_tenant_with_data['tenant_id']}/creative-formats")

        # Must be 200 for proper render test
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # Verify template rendered
        assert len(response.data) > 500, "Response too small - likely an error"
        assert b"Creative Formats" in response.data or b"creative" in response.data

    def test_targeting_browser_renders_without_builderror(self, authenticated_admin_session, test_tenant_with_data):
        """Test that the targeting browser page renders without url_for BuildError.

        Note: This route may not exist in all configurations. We'll skip if 404.
        """
        response = authenticated_admin_session.get(f"/tenant/{test_tenant_with_data['tenant_id']}/targeting-browser")

        # Skip test if route doesn't exist (404)
        if response.status_code == 404:
            import pytest

            pytest.skip("targeting-browser route does not exist")

        # Must be 200 for proper render test
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # Verify template rendered
        assert len(response.data) > 500, "Response too small - likely an error"
        assert b"Targeting" in response.data or b"targeting" in response.data

    def test_critical_url_for_calls_resolve(self, authenticated_admin_session, test_tenant_with_data):
        """Test that critical url_for calls in templates resolve correctly."""
        from admin_ui import app

        with app.test_request_context():
            # Test the specific routes used in products.html
            critical_routes = [
                ("tenant_dashboard", {"tenant_id": test_tenant_with_data["tenant_id"]}),
                ("add_product", {"tenant_id": test_tenant_with_data["tenant_id"]}),
                ("browse_product_templates", {"tenant_id": test_tenant_with_data["tenant_id"]}),
                ("bulk_product_upload_form", {"tenant_id": test_tenant_with_data["tenant_id"]}),
                ("add_product_ai_form", {"tenant_id": test_tenant_with_data["tenant_id"]}),
                ("list_products", {"tenant_id": test_tenant_with_data["tenant_id"]}),
            ]

            for endpoint, kwargs in critical_routes:
                try:
                    url = url_for(endpoint, **kwargs)
                    assert url, f"url_for('{endpoint}') returned empty"
                except BuildError as e:
                    pytest.fail(f"Critical url_for('{endpoint}') failed: {e}")

    def test_invalid_tenant_id_handling(self, authenticated_admin_session):
        """Test graceful handling of invalid tenant ID."""
        response = authenticated_admin_session.get("/tenant/nonexistent/products")
        # Should redirect to login or show 404
        assert response.status_code in [302, 404], f"Expected 302/404, got {response.status_code}"

        # Should not expose internal errors
        if response.status_code == 404:
            assert b"BuildError" not in response.data
            assert b"Traceback" not in response.data

    def test_template_error_propagation(self, admin_client, test_tenant_with_data):
        """Test that template errors are properly caught with PROPAGATE_EXCEPTIONS."""
        # This test verifies our test configuration works
        app.config["PROPAGATE_EXCEPTIONS"] = True

        with admin_client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["role"] = "super_admin"
            sess["email"] = "test@example.com"

        try:
            response = admin_client.get(f"/tenant/{test_tenant_with_data['tenant_id']}/products")
            # Should succeed with current fixed templates
            assert response.status_code == 200
        except BuildError as e:
            # This would indicate templates still have bad url_for calls
            pytest.fail(f"Template contains invalid url_for: {e}")
        except TemplateRuntimeError as e:
            # This would indicate other template errors
            pytest.fail(f"Template runtime error: {e}")
