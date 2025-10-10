"""End-to-end tests for creative lifecycle - DEPRECATED.

These tests use the old MCP client API (client.tools.method_name) which is no longer
supported. The correct pattern is in test_adcp_reference_implementation.py which uses
client.call_tool().

TODO: Rewrite these tests using the new API pattern.
"""


class TestCreativeLifecycle:
    """Creative lifecycle E2E tests - all tests deprecated."""

    def test_placeholder(self):
        """Placeholder test so pytest doesn't fail on empty test file."""
        pass
