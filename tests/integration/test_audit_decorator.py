"""Integration tests for audit logging decorator."""

import pytest
from flask import Flask
from sqlalchemy import select

from src.admin.utils.audit_decorator import log_admin_action
from src.core.database.database_session import get_db_session
from src.core.database.models import AuditLog, Tenant


@pytest.mark.requires_db
def test_decorator_logs_successful_action(integration_db):
    """Verify decorator creates audit log for successful action."""
    # Create test tenant
    with get_db_session() as db_session:
        tenant = Tenant(tenant_id="test_tenant", name="Test Tenant", subdomain="test")
        db_session.add(tenant)
        db_session.commit()

    # Create test Flask app and route
    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/test/<tenant_id>")
    @log_admin_action("test_operation")
    def test_route(tenant_id):
        return "success"

    # Simulate request
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"email": "test@example.com"}

        response = client.get("/test/test_tenant")
        assert response.status_code == 200

    # Verify audit log created
    with get_db_session() as db_session:
        stmt = select(AuditLog).filter_by(tenant_id="test_tenant", operation="AdminUI.test_operation")
        audit_log = db_session.scalars(stmt).first()

        assert audit_log is not None
        assert audit_log.principal_name == "test@example.com"
        assert audit_log.success is True
        assert audit_log.details["action"] == "test_operation"


@pytest.mark.requires_db
def test_decorator_filters_password_fields(integration_db):
    """Verify decorator excludes password fields from audit logs."""
    with get_db_session() as db_session:
        tenant = Tenant(tenant_id="test_tenant_2", name="Test Tenant 2", subdomain="test2")
        db_session.add(tenant)
        db_session.commit()

    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/test/<tenant_id>", methods=["POST"])
    @log_admin_action("update_settings")
    def test_route(tenant_id):
        return "success"

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"email": "admin@example.com"}

        response = client.post(
            "/test/test_tenant_2",
            data={
                "name": "Test User",
                "password": "super_secret_123",  # Should be filtered
                "email": "user@example.com",
            },
        )
        assert response.status_code == 200

    # Verify password not in audit log
    with get_db_session() as db_session:
        stmt = select(AuditLog).filter_by(tenant_id="test_tenant_2")
        audit_log = db_session.scalars(stmt).first()

        assert audit_log is not None
        request_data = audit_log.details.get("request_data", {})
        assert "password" not in request_data
        assert request_data.get("name") == "Test User"
        assert request_data.get("email") == "user@example.com"


@pytest.mark.requires_db
def test_decorator_filters_sensitive_json_fields(integration_db):
    """Verify decorator filters sensitive fields from JSON requests."""
    with get_db_session() as db_session:
        tenant = Tenant(tenant_id="test_tenant_3", name="Test Tenant 3", subdomain="test3")
        db_session.add(tenant)
        db_session.commit()

    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/test/<tenant_id>", methods=["POST"])
    @log_admin_action("api_call")
    def test_route(tenant_id):
        return "success"

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"email": "admin@example.com"}

        response = client.post(
            "/test/test_tenant_3",
            json={
                "username": "testuser",
                "api_key": "sk-1234567890",  # Should be filtered
                "access_token": "token_xyz",  # Should be filtered
                "webhook_secret": "secret_abc",  # Should be filtered
                "data": "public_value",
            },
        )
        assert response.status_code == 200

    # Verify sensitive fields not in audit log
    with get_db_session() as db_session:
        stmt = select(AuditLog).filter_by(tenant_id="test_tenant_3")
        audit_log = db_session.scalars(stmt).first()

        assert audit_log is not None
        request_data = audit_log.details.get("request_data", {})
        assert "api_key" not in request_data
        assert "access_token" not in request_data
        assert "webhook_secret" not in request_data
        assert request_data.get("username") == "testuser"
        assert request_data.get("data") == "public_value"


@pytest.mark.requires_db
def test_decorator_logs_failed_actions(integration_db):
    """Verify decorator logs exceptions and re-raises them."""
    with get_db_session() as db_session:
        tenant = Tenant(tenant_id="test_tenant_4", name="Test Tenant 4", subdomain="test4")
        db_session.add(tenant)
        db_session.commit()

    app = Flask(__name__)
    app.secret_key = "test"
    app.config["PROPAGATE_EXCEPTIONS"] = True  # Enable exception propagation for testing

    @app.route("/test/<tenant_id>")
    @log_admin_action("failing_operation")
    def test_route(tenant_id):
        raise ValueError("Test error")

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"email": "test@example.com"}

        # Should raise exception
        with pytest.raises(ValueError, match="Test error"):
            client.get("/test/test_tenant_4")

    # Verify audit log created with failure
    with get_db_session() as db_session:
        stmt = select(AuditLog).filter_by(tenant_id="test_tenant_4")
        audit_log = db_session.scalars(stmt).first()

        assert audit_log is not None
        assert audit_log.success is False
        assert "Test error" in audit_log.error_message


@pytest.mark.requires_db
def test_decorator_truncates_long_values(integration_db):
    """Verify decorator truncates values longer than 100 characters."""
    with get_db_session() as db_session:
        tenant = Tenant(tenant_id="test_tenant_5", name="Test Tenant 5", subdomain="test5")
        db_session.add(tenant)
        db_session.commit()

    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/test/<tenant_id>", methods=["POST"])
    @log_admin_action("long_value_test")
    def test_route(tenant_id):
        return "success"

    long_value = "x" * 200  # 200 characters

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"email": "test@example.com"}

        response = client.post("/test/test_tenant_5", data={"description": long_value})
        assert response.status_code == 200

    # Verify value truncated to 100 chars
    with get_db_session() as db_session:
        stmt = select(AuditLog).filter_by(tenant_id="test_tenant_5")
        audit_log = db_session.scalars(stmt).first()

        assert audit_log is not None
        request_data = audit_log.details.get("request_data", {})
        assert len(request_data.get("description", "")) == 100


@pytest.mark.requires_db
def test_decorator_extracts_custom_details(integration_db):
    """Verify extract_details callback works correctly."""
    with get_db_session() as db_session:
        tenant = Tenant(tenant_id="test_tenant_6", name="Test Tenant 6", subdomain="test6")
        db_session.add(tenant)
        db_session.commit()

    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/test/<tenant_id>/<product_id>")
    @log_admin_action("custom_details", extract_details=lambda r, **kw: {"product_id": kw.get("product_id")})
    def test_route(tenant_id, product_id):
        return "success"

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"email": "test@example.com"}

        response = client.get("/test/test_tenant_6/prod_123")
        assert response.status_code == 200

    # Verify custom details extracted
    with get_db_session() as db_session:
        stmt = select(AuditLog).filter_by(tenant_id="test_tenant_6")
        audit_log = db_session.scalars(stmt).first()

        assert audit_log is not None
        assert audit_log.details.get("product_id") == "prod_123"


@pytest.mark.requires_db
def test_decorator_skips_logging_without_tenant_id(integration_db):
    """Verify decorator skips audit logging when tenant_id not in kwargs."""
    from sqlalchemy import func

    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/test")
    @log_admin_action("no_tenant_operation")
    def test_route():
        return "success"

    initial_count = 0
    with get_db_session() as db_session:
        initial_count = db_session.scalar(select(func.count()).select_from(AuditLog))

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {"email": "test@example.com"}

        response = client.get("/test")
        assert response.status_code == 200

    # Verify no new audit log created
    with get_db_session() as db_session:
        final_count = db_session.scalar(select(func.count()).select_from(AuditLog))
        assert final_count == initial_count


@pytest.mark.requires_db
def test_decorator_handles_missing_session(integration_db):
    """Verify decorator handles missing session gracefully."""
    with get_db_session() as db_session:
        tenant = Tenant(tenant_id="test_tenant_7", name="Test Tenant 7", subdomain="test7")
        db_session.add(tenant)
        db_session.commit()

    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/test/<tenant_id>")
    @log_admin_action("no_session_test")
    def test_route(tenant_id):
        return "success"

    with app.test_client() as client:
        # Don't set session - decorator should handle gracefully
        response = client.get("/test/test_tenant_7")
        assert response.status_code == 200

    # Verify audit log created with "unknown" user
    with get_db_session() as db_session:
        stmt = select(AuditLog).filter_by(tenant_id="test_tenant_7")
        audit_log = db_session.scalars(stmt).first()

        assert audit_log is not None
        assert audit_log.principal_name == "unknown"
