"""Test that all registered MCP tools have corresponding test coverage.

This test ensures that no MCP tool ships to production without test coverage.
Issue #816 revealed that list_tasks, get_task, complete_task shipped with zero tests.
Issue #821 requests this automated check to prevent future occurrences.

The test works by:
1. Getting all registered tools from the MCP tool manager
2. Scanning test files for each tool name
3. Failing if any tools lack test references
"""

from pathlib import Path


class TestMCPToolTestCoverage:
    """Verify every registered MCP tool has test coverage."""

    def _get_registered_tools(self) -> list[str]:
        """Get all registered MCP tool names."""
        from src.core.main import mcp

        return list(mcp._tool_manager._tools.keys())

    def _get_test_files_content(self) -> str:
        """Get concatenated content of all test files."""
        tests_dir = Path(__file__).parent.parent
        content_parts = []

        for test_file in tests_dir.rglob("test_*.py"):
            # Skip this file to avoid false positives
            if test_file.name == "test_mcp_tool_test_coverage.py":
                continue
            try:
                content_parts.append(test_file.read_text())
            except Exception:
                # Skip files that can't be read
                pass

        return "\n".join(content_parts)

    def _tool_has_test_coverage(self, tool_name: str, test_content: str) -> bool:
        """Check if a tool has test coverage based on test file content.

        Looks for patterns that indicate the tool is being tested:
        - test_{tool_name} (standard test function naming)
        - _{tool_name}_ (impl function tests)
        - {tool_name}_raw (A2A raw function tests)
        - "{tool_name}" in tool registration tests
        - {tool_name}( (direct function calls in tests)
        """
        patterns = [
            f"test_{tool_name}",  # test_get_products, test_list_tasks
            f"_{tool_name}_",  # _get_products_impl
            f"{tool_name}_raw",  # get_products_raw
            f'"{tool_name}"',  # "get_products" in assertions
            f"'{tool_name}'",  # 'get_products' in assertions
            f"{tool_name}(",  # get_products( direct calls
        ]
        return any(pattern in test_content for pattern in patterns)

    def test_all_tools_have_test_coverage(self):
        """Every registered MCP tool must have at least one test.

        This prevents shipping tools with zero test coverage like issue #816.
        """
        registered_tools = self._get_registered_tools()
        test_content = self._get_test_files_content()

        untested_tools = []
        for tool_name in registered_tools:
            if not self._tool_has_test_coverage(tool_name, test_content):
                untested_tools.append(tool_name)

        if untested_tools:
            untested_list = "\n  - ".join(untested_tools)
            raise AssertionError(
                f"The following MCP tools have no test coverage:\n  - {untested_list}\n\n"
                f"Every MCP tool MUST have tests before shipping. "
                f"See tests/unit/test_task_management_tools.py for examples.\n"
                f"Issue #816 found that untested tools shipped broken - "
                f"this check prevents that."
            )

    def test_tool_coverage_check_detects_patterns(self):
        """Verify the pattern detection works correctly."""
        # Test various patterns that should be detected
        test_content = """
        def test_get_products_returns_list():
            pass

        def test_create_media_buy_validates_input():
            pass

        class TestListTasks:
            def test_list_tasks_returns_tasks(self):
                tool = mcp._tool_manager._tools.get("list_tasks")
                pass

        def test_impl_calls_get_task_impl():
            result = _get_task_impl(task_id)
            pass

        async def test_raw_function():
            result = sync_creatives_raw(creatives=[])
            pass
        """

        # These should be detected
        assert self._tool_has_test_coverage("get_products", test_content)
        assert self._tool_has_test_coverage("create_media_buy", test_content)
        assert self._tool_has_test_coverage("list_tasks", test_content)
        assert self._tool_has_test_coverage("get_task", test_content)
        assert self._tool_has_test_coverage("sync_creatives", test_content)

        # This should NOT be detected
        assert not self._tool_has_test_coverage("nonexistent_tool", test_content)
