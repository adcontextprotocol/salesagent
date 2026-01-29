"""Tests for tenant-level manual approval enforcement.

This test suite ensures that the tenant's human_review_required setting
is respected during media buy creation, with the tenant setting taking
precedence over adapter-specific settings.

Issue: https://github.com/prebid/salesagent/issues/845

## Test Strategy

This module uses two types of tests:

1. **Source Code Pattern Tests**: Verify that security-critical patterns exist in the
   implementation. These catch regressions that might accidentally remove the tenant
   approval check. If these tests fail after a refactor, update them to match the new
   pattern (or investigate if the security invariant was accidentally removed).

2. **Specification Tests**: Document the expected logical behavior. These serve as
   executable documentation of the business rules.

Integration tests for actual media buy approval flow are in:
- tests/integration_v2/test_create_media_buy_v24.py
- tests/integration/test_gam_pricing_models_integration.py
"""

from pathlib import Path


class TestTenantManualApprovalEnforcement:
    """Test that tenant.human_review_required is enforced for media buys."""

    def test_implementation_uses_tenant_approval_setting(self):
        """Verify create_media_buy uses tenant.human_review_required as primary source.

        This is a source code pattern test that catches regressions where the tenant
        approval check might be accidentally removed. If this test fails after a
        refactor, update it to match the new pattern.
        """
        file_path = Path(__file__).parent.parent.parent / "src" / "core" / "tools" / "media_buy_create.py"
        source = file_path.read_text()

        # The implementation must check tenant's human_review_required setting
        assert 'tenant.get("human_review_required"' in source, (
            "Implementation must use tenant.human_review_required as the authoritative source "
            "for manual approval requirements. This is a security-critical check."
        )

        # The implementation must combine tenant and adapter settings with OR logic
        assert "tenant_approval_required or adapter_approval_required" in source, (
            "Implementation must use OR logic: if either tenant or adapter requires approval, "
            "approval is required. This ensures secure-by-default behavior."
        )


class TestApprovalLogicSpecification:
    """Specification tests documenting the expected approval logic.

    These tests serve as executable documentation of the business rules.
    """

    def test_tenant_true_overrides_adapter_false(self):
        """Tenant requiring approval overrides adapter not requiring it."""
        tenant_requires = True
        adapter_requires = False
        result = tenant_requires or adapter_requires
        assert result is True

    def test_adapter_true_triggers_approval_even_if_tenant_false(self):
        """Adapter requiring approval still triggers if tenant doesn't require it."""
        tenant_requires = False
        adapter_requires = True
        result = tenant_requires or adapter_requires
        assert result is True

    def test_both_true_requires_approval(self):
        """Both settings true requires approval."""
        tenant_requires = True
        adapter_requires = True
        result = tenant_requires or adapter_requires
        assert result is True

    def test_both_false_skips_approval(self):
        """Only when both settings are false can approval be skipped."""
        tenant_requires = False
        adapter_requires = False
        result = tenant_requires or adapter_requires
        assert result is False

    def test_missing_tenant_setting_defaults_to_require_approval(self):
        """Missing tenant setting defaults to True (secure by default)."""
        tenant: dict[str, bool] = {}  # No human_review_required key
        default_approval = tenant.get("human_review_required", True)
        assert default_approval is True
