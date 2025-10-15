"""Integration tests for tenant serialization utilities."""

import pytest
from sqlalchemy import inspect

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant
from src.core.utils.tenant_utils import serialize_tenant_to_dict


@pytest.mark.requires_db
def test_serialize_tenant_includes_all_expected_fields(integration_db):
    """Ensure serialization includes all expected Tenant fields."""
    with get_db_session() as db_session:
        # Create test tenant
        tenant = Tenant(
            tenant_id="test",
            name="Test Tenant",
            subdomain="test",
            virtual_host="test.example.com",
            ad_server="mock",
            max_daily_budget=10000,
            enable_axe_signals=True,
            authorized_emails=["admin@test.com"],
            authorized_domains=["test.com"],
            slack_webhook_url="https://slack.com/webhook",
            admin_token="test_admin_token",
            auto_approve_formats=["display_300x250"],
            human_review_required=True,
            slack_audit_webhook_url="https://slack.com/audit",
            hitl_webhook_url="https://hitl.com/webhook",
            policy_settings={"key": "value"},
            signals_agent_config={"config": "value"},
            approval_mode="auto",
            gemini_api_key="test_api_key",
            creative_review_criteria="test criteria",
        )
        db_session.add(tenant)
        db_session.flush()

        # Serialize
        result = serialize_tenant_to_dict(tenant)

        # Check all important fields are included
        expected_fields = {
            "tenant_id",
            "name",
            "subdomain",
            "virtual_host",
            "ad_server",
            "max_daily_budget",
            "enable_axe_signals",
            "authorized_emails",
            "authorized_domains",
            "slack_webhook_url",
            "admin_token",
            "auto_approve_formats",
            "human_review_required",
            "slack_audit_webhook_url",
            "hitl_webhook_url",
            "policy_settings",
            "signals_agent_config",
            "approval_mode",
            "gemini_api_key",
            "creative_review_criteria",
        }

        for field in expected_fields:
            assert field in result, f"Missing field: {field}"


@pytest.mark.requires_db
def test_serialize_tenant_field_values(integration_db):
    """Verify serialized field values match Tenant model."""
    with get_db_session() as db_session:
        tenant = Tenant(
            tenant_id="test",
            name="Test Tenant",
            subdomain="test",
            ad_server="gam",
            max_daily_budget=50000,
            gemini_api_key="gemini_key_123",
            approval_mode="manual",
            creative_review_criteria="Must be brand safe",
        )
        db_session.add(tenant)
        db_session.flush()

        result = serialize_tenant_to_dict(tenant)

        assert result["tenant_id"] == "test"
        assert result["name"] == "Test Tenant"
        assert result["subdomain"] == "test"
        assert result["ad_server"] == "gam"
        assert result["max_daily_budget"] == 50000
        assert result["gemini_api_key"] == "gemini_key_123"
        assert result["approval_mode"] == "manual"
        assert result["creative_review_criteria"] == "Must be brand safe"


@pytest.mark.requires_db
def test_serialize_tenant_json_fields(integration_db):
    """Verify JSON fields are properly deserialized."""
    with get_db_session() as db_session:
        tenant = Tenant(
            tenant_id="test",
            name="Test Tenant",
            authorized_emails=["admin@test.com", "user@test.com"],
            authorized_domains=["test.com", "example.com"],
            auto_approve_formats=["display_300x250", "video_640x480"],
            policy_settings={"strict_mode": True, "max_duration": 30},
            signals_agent_config={"endpoint": "https://api.example.com", "timeout": 10},
        )
        db_session.add(tenant)
        db_session.flush()

        result = serialize_tenant_to_dict(tenant)

        # Verify JSON fields are lists/dicts, not strings
        assert isinstance(result["authorized_emails"], list)
        assert result["authorized_emails"] == ["admin@test.com", "user@test.com"]

        assert isinstance(result["authorized_domains"], list)
        assert result["authorized_domains"] == ["test.com", "example.com"]

        assert isinstance(result["auto_approve_formats"], list)
        assert result["auto_approve_formats"] == ["display_300x250", "video_640x480"]

        assert isinstance(result["policy_settings"], dict)
        assert result["policy_settings"]["strict_mode"] is True

        assert isinstance(result["signals_agent_config"], dict)
        assert result["signals_agent_config"]["endpoint"] == "https://api.example.com"


@pytest.mark.requires_db
def test_serialize_tenant_nullable_fields(integration_db):
    """Verify nullable fields are handled correctly."""
    with get_db_session() as db_session:
        tenant = Tenant(
            tenant_id="test",
            name="Test Tenant",
            # All nullable fields omitted
        )
        db_session.add(tenant)
        db_session.flush()

        result = serialize_tenant_to_dict(tenant)

        # Nullable fields should be present but None or empty defaults
        assert "subdomain" in result
        assert "virtual_host" in result
        assert "slack_webhook_url" in result
        assert "admin_token" in result
        assert result["authorized_emails"] == []  # Default empty list
        assert result["authorized_domains"] == []  # Default empty list


@pytest.mark.requires_db
def test_serialize_tenant_model_column_coverage(integration_db):
    """Ensure serialization covers key Tenant model columns."""
    with get_db_session() as db_session:
        # Get all Tenant model columns
        tenant_columns = {col.name for col in inspect(Tenant).columns}

        # Create test tenant
        tenant = Tenant(tenant_id="test", name="Test")
        db_session.add(tenant)
        db_session.flush()

        # Serialize
        result = serialize_tenant_to_dict(tenant)

        # These are the critical fields that must be in the serialization
        # (excludes internal fields like created_at, updated_at, is_active)
        critical_fields = {
            "tenant_id",
            "name",
            "subdomain",
            "virtual_host",
            "ad_server",
            "max_daily_budget",
            "enable_axe_signals",
            "authorized_emails",
            "authorized_domains",
            "slack_webhook_url",
            "admin_token",
            "auto_approve_formats",
            "human_review_required",
            "slack_audit_webhook_url",
            "hitl_webhook_url",
            "policy_settings",
            "signals_agent_config",
            "approval_mode",
            "gemini_api_key",
            "creative_review_criteria",
        }

        # Verify all critical fields are in result
        for field in critical_fields:
            assert field in result, f"Critical field missing: {field}"

        # Verify we're not missing any obvious tenant columns
        # (Allow for internal fields like is_active, created_at to be excluded)
        serialized_keys = set(result.keys())
        for col in ["tenant_id", "name", "ad_server", "approval_mode"]:
            assert col in serialized_keys, f"Expected column {col} in serialized result"
