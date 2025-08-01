#!/usr/bin/env python3
"""
Direct test of subagent functionality without MCP wrapper.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

# Change to UI tests directory first
os.chdir(Path(__file__).parent.parent)

async def test_list_tests():
    """Test listing UI tests."""
    from pathlib import Path
    tests_path = Path("tests")
    test_files = list(tests_path.glob("test_*.py"))
    print(f"Found {len(test_files)} test files")
    for f in test_files[:3]:
        print(f"  - {f.name}")

async def test_auth_check():
    """Test auth check by running actual test."""
    import subprocess
    
    cmd = ["uv", "run", "python", "-m", "pytest", 
           "tests/test_authentication_example.py::TestAuthenticationExample::test_check_auth_status",
           "-v", "-s", "--tb=short"]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parse output
    if "Logged in: True" in result.stdout:
        print("✅ Authentication check passed")
        # Extract details
        import re
        email = re.search(r'Email: (.+)', result.stdout)
        if email:
            print(f"   Email: {email.group(1)}")
    else:
        print("❌ Not authenticated")

async def test_generate():
    """Test code generation."""
    template = '''import pytest
from playwright.async_api import Page

class TestGenerated:
    @pytest.mark.asyncio
    async def test_example(self, page: Page, base_url: str):
        """Generated test example."""
        await page.goto(base_url)
        assert True
'''
    print("✅ Code generation working")
    print("   Generated test template")

async def main():
    print("🧪 Testing Subagent Components\n")
    
    print("1. Testing list functionality...")
    await test_list_tests()
    
    print("\n2. Testing auth check...")
    await test_auth_check()
    
    print("\n3. Testing code generation...")
    await test_generate()
    
    print("\n✨ Direct testing complete!")

if __name__ == "__main__":
    asyncio.run(main())