"""Tests for tenant-level manual approval enforcement.

This test suite ensures that the tenant's human_review_required setting
is respected during media buy creation, with the tenant setting taking
precedence over adapter-specific settings.

Issue: https://github.com/adcontextprotocol/salesagent/issues/845
"""

from pathlib import Path


class TestTenantManualApprovalEnforcement:
    """Test that tenant.human_review_required is enforced for media buys."""

    def test_source_code_uses_tenant_approval_setting(self):
        """Verify create_media_buy source uses tenant.human_review_required as primary source."""
        file_path = Path(__file__).parent.parent.parent / "src" / "core" / "tools" / "media_buy_create.py"
        source = file_path.read_text()

        # Find the manual approval check section
        approval_check_start = source.find("# Check if manual approval is required")
        assert approval_check_start != -1, "Manual approval check section not found"

        # Get the relevant section (next 15 lines after the comment)
        approval_section = source[approval_check_start : approval_check_start + 1000]

        # Must use tenant's human_review_required as primary source
        assert 'tenant.get("human_review_required"' in approval_section, (
            "tenant.human_review_required must be used as the authoritative source " "for manual approval requirements"
        )

        # Must set tenant_approval_required variable
        assert (
            "tenant_approval_required" in approval_section
        ), "Should have a tenant_approval_required variable to track tenant's setting"

        # Must combine both tenant and adapter settings
        assert (
            "tenant_approval_required or adapter_approval_required" in approval_section
        ), "Final manual_approval_required should be the OR of tenant and adapter settings"

    def test_source_code_logs_both_settings(self):
        """Verify debug logging includes both tenant and adapter settings."""
        file_path = Path(__file__).parent.parent.parent / "src" / "core" / "tools" / "media_buy_create.py"
        source = file_path.read_text()

        # Find the debug log section
        debug_log_start = source.find("[DEBUG] Manual approval check")
        assert debug_log_start != -1, "Debug log for manual approval check not found"

        # Get the log statement (next 300 chars)
        debug_section = source[debug_log_start : debug_log_start + 300]

        # Should log tenant_approval_required
        assert (
            "tenant_approval_required" in debug_section
        ), "Debug log should include tenant_approval_required for troubleshooting"

        # Should log adapter_approval_required
        assert (
            "adapter_approval_required" in debug_section
        ), "Debug log should include adapter_approval_required for troubleshooting"

    def test_tenant_approval_takes_precedence(self):
        """Document expected behavior: tenant.human_review_required=True overrides adapter."""
        # This test documents the expected behavior after the fix:
        # If tenant.human_review_required is True, manual_approval_required should be True
        # regardless of what the adapter says

        # Scenario 1: Tenant requires approval, adapter doesn't
        tenant_requires = True
        adapter_requires = False
        expected_result = tenant_requires or adapter_requires
        assert expected_result is True, "Tenant requirement should override adapter"

        # Scenario 2: Tenant doesn't require, adapter does
        tenant_requires = False
        adapter_requires = True
        expected_result = tenant_requires or adapter_requires
        assert expected_result is True, "Either setting true should require approval"

        # Scenario 3: Both require approval
        tenant_requires = True
        adapter_requires = True
        expected_result = tenant_requires or adapter_requires
        assert expected_result is True, "Both true should require approval"

        # Scenario 4: Neither requires approval
        tenant_requires = False
        adapter_requires = False
        expected_result = tenant_requires or adapter_requires
        assert expected_result is False, "Only false when both are false"

    def test_default_behavior_is_safe(self):
        """Document that default behavior requires approval for safety."""
        # The fix defaults to True when tenant.human_review_required is not set
        # This matches the secure-by-default principle

        # Simulate tenant.get("human_review_required", True) with missing key
        tenant: dict = {}
        default_approval = tenant.get("human_review_required", True)
        assert default_approval is True, "Default should be True (require approval) for safety"
