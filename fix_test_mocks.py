#!/usr/bin/env python3
"""
Fix test mocks to use get_db_session instead of get_db_connection.
"""

import os
import re


def fix_test_file(filepath):
    """Update a test file to use get_db_session instead of get_db_connection."""

    with open(filepath) as f:
        content = f.read()

    original_content = content

    # Replace get_db_connection imports
    content = re.sub(r"from db_config import get_db_connection", "from database_session import get_db_session", content)

    # Replace patches of get_db_connection
    content = re.sub(
        r'patch\(["\']db_config\.get_db_connection["\']\)', 'patch("database_session.get_db_session")', content
    )

    content = re.sub(r'patch\(["\'](\w+)\.get_db_connection["\']\)', r'patch("\1.get_db_session")', content)

    # Replace mock assignments
    content = re.sub(r"(\w+)\.get_db_connection = MagicMock", r"\1.get_db_session = MagicMock", content)

    # Replace direct calls
    content = re.sub(r"get_db_connection\(\)", "get_db_session()", content)

    # Fix mock_db patterns to mock_session
    if "mock_db = MagicMock()" in content:
        # Create proper session mock
        session_mock = """# Mock the database session
mock_session = MagicMock()
mock_session.query.return_value.filter_by.return_value.first.return_value = None
mock_session.query.return_value.filter_by.return_value.all.return_value = []
mock_session.query.return_value.filter.return_value.first.return_value = None
mock_session.query.return_value.filter.return_value.all.return_value = []
mock_session.query.return_value.all.return_value = []
mock_session.__enter__ = MagicMock(return_value=mock_session)
mock_session.__exit__ = MagicMock(return_value=None)"""

        # Replace mock_db creation
        content = re.sub(
            r"mock_db = MagicMock\(\).*?mock_db\.execute\.return_value = mock_cursor",
            session_mock,
            content,
            flags=re.DOTALL,
        )

        # Replace mock_db references with mock_session
        content = re.sub(r"\bmock_db\b", "mock_session", content)
        content = re.sub(r"\bmock_cursor\b", "mock_query", content)

    if content != original_content:
        with open(filepath, "w") as f:
            f.write(content)
        return True
    return False


def main():
    """Fix all test files."""
    test_dirs = ["tests/unit", "tests/integration", "tests/e2e"]
    fixed_files = []

    for test_dir in test_dirs:
        if not os.path.exists(test_dir):
            continue

        for root, dirs, files in os.walk(test_dir):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    if fix_test_file(filepath):
                        fixed_files.append(filepath)

    if fixed_files:
        print(f"Fixed {len(fixed_files)} test files:")
        for f in fixed_files:
            print(f"  - {f}")
    else:
        print("No test files needed fixing.")


if __name__ == "__main__":
    main()
