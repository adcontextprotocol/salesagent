#!/usr/bin/env python3
"""
MCP Server for UI Testing Tools
Provides tools for Claude to run and analyze UI tests.
"""

import os
import sys
import asyncio
import subprocess
import json
import base64
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError

# Initialize the MCP server
mcp = FastMCP("ui-test-assistant")

# Configuration
UI_TESTS_DIR = Path(__file__).parent.parent
PROJECT_ROOT = UI_TESTS_DIR.parent
SCREENSHOTS_DIR = UI_TESTS_DIR / "screenshots"
REPORTS_DIR = UI_TESTS_DIR / "reports"

# Ensure directories exist
SCREENSHOTS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

@mcp.tool()
async def list_ui_tests(
    test_directory: str = "tests",
    pattern: str = "test_*.py"
) -> Dict[str, List[str]]:
    """
    List all available UI tests.
    
    Args:
        test_directory: Directory to search for tests (default: tests)
        pattern: File pattern to match (default: test_*.py)
    
    Returns:
        Dictionary with test files and their test functions
    """
    tests_path = UI_TESTS_DIR / test_directory
    test_files = {}
    
    for test_file in tests_path.glob(pattern):
        # Read file and extract test functions
        with open(test_file, 'r') as f:
            content = f.read()
        
        # Find test functions
        import re
        test_functions = re.findall(r'async def (test_\w+)\(', content)
        
        test_files[str(test_file.relative_to(UI_TESTS_DIR))] = test_functions
    
    return test_files

@mcp.tool()
async def run_ui_test(
    test_path: str,
    headed: bool = False,
    verbose: bool = True,
    timeout: int = 60
) -> Dict[str, Any]:
    """
    Run a specific UI test or test file.
    
    Args:
        test_path: Path to test file or specific test (e.g., tests/test_login.py::TestLogin::test_login)
        headed: Run with visible browser (default: False)
        verbose: Verbose output (default: True)
        timeout: Timeout in seconds (default: 60)
    
    Returns:
        Test execution results including output, status, and any screenshots
    """
    # Change to UI tests directory
    os.chdir(UI_TESTS_DIR)
    
    # Build command
    cmd = ["uv", "run", "python", "-m", "pytest", test_path]
    
    if verbose:
        cmd.append("-v")
    cmd.append("-s")  # No capture for better output
    
    # Set environment variables
    env = os.environ.copy()
    env["HEADLESS"] = "false" if headed else "true"
    
    # Run test
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        
        # Check for new screenshots
        screenshots = []
        screenshot_files = sorted(SCREENSHOTS_DIR.glob("*.png"))
        recent_screenshots = [
            f for f in screenshot_files 
            if (datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)).seconds < 120
        ]
        
        for screenshot in recent_screenshots[:3]:  # Limit to 3 most recent
            with open(screenshot, 'rb') as f:
                screenshots.append({
                    "filename": screenshot.name,
                    "data": base64.b64encode(f.read()).decode('utf-8')
                })
        
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "screenshots": screenshots,
            "command": " ".join(cmd)
        }
        
    except subprocess.TimeoutExpired:
        raise ToolError(f"Test timed out after {timeout} seconds")
    except Exception as e:
        raise ToolError(f"Failed to run test: {str(e)}")

@mcp.tool()
async def generate_ui_test(
    feature_description: str,
    test_type: str = "functional",
    page_objects: List[str] = None
) -> str:
    """
    Generate UI test code based on description.
    
    Args:
        feature_description: Description of what to test
        test_type: Type of test (functional, regression, smoke, etc.)
        page_objects: List of page objects to use (e.g., ["LoginPage", "TenantPage"])
    
    Returns:
        Generated test code
    """
    # Template for test generation
    template = '''"""
Generated UI test for: {description}
Test type: {test_type}
"""

import pytest
from playwright.async_api import Page
{imports}

class Test{class_name}:
    """Generated {test_type} tests."""
    
    @pytest.mark.asyncio
    @pytest.mark.{test_type}
    async def test_{test_name}(self, page: Page, base_url: str):
        """Test: {description}"""
        # Navigate to the application
        await page.goto(base_url)
        
        # TODO: Implement test steps based on requirements
        # 1. Setup - prepare test data and state
        # 2. Action - perform the user actions
        # 3. Assert - verify the expected results
        
        # Example structure:
        # page_obj = {page_class}(page, base_url)
        # await page_obj.some_action()
        # assert await page_obj.verify_result()
        
        # Placeholder assertion
        assert True, "Test not yet implemented"
'''
    
    # Generate test details
    class_name = "".join(word.capitalize() for word in feature_description.split()[:3])
    test_name = "_".join(feature_description.lower().split()[:5]).replace("-", "_")
    
    # Generate imports
    imports = []
    if page_objects:
        for page_obj in page_objects:
            imports.append(f"from ..pages.{page_obj.lower()}_page import {page_obj}")
    else:
        imports.append("from ..pages.base_page import BasePage")
    
    page_class = page_objects[0] if page_objects else "BasePage"
    
    return template.format(
        description=feature_description,
        test_type=test_type,
        class_name=class_name,
        test_name=test_name,
        imports="\n".join(imports),
        page_class=page_class
    )

@mcp.tool()
async def check_auth_status() -> Dict[str, Any]:
    """
    Check current authentication status of the test environment.
    
    Returns:
        Authentication status including logged in state, email, and role
    """
    # Run the auth check test
    result = await run_ui_test(
        "tests/test_authentication_example.py::TestAuthenticationExample::test_check_auth_status",
        verbose=False
    )
    
    # Parse output for auth status
    output = result["stdout"]
    auth_info = {
        "logged_in": "Logged in: True" in output,
        "email": None,
        "role": None
    }
    
    # Extract email and role from output
    import re
    email_match = re.search(r'Email: (.+@.+)', output)
    role_match = re.search(r'Role: (.+)', output)
    
    if email_match:
        auth_info["email"] = email_match.group(1).strip()
    if role_match:
        auth_info["role"] = role_match.group(1).strip()
    
    return auth_info

@mcp.tool()
async def save_auth_state(
    filename: str = "test_auth_state.json"
) -> Dict[str, str]:
    """
    Save current authentication state for reuse in tests.
    
    Args:
        filename: Name of file to save auth state (default: test_auth_state.json)
    
    Returns:
        Status of save operation
    """
    # Run the save auth state test
    result = await run_ui_test(
        "tests/test_authentication_example.py::TestAuthenticationExample::test_save_current_auth_state",
        verbose=False
    )
    
    if result["success"]:
        auth_file = UI_TESTS_DIR / filename
        if auth_file.exists():
            return {
                "status": "success",
                "message": f"Authentication state saved to {filename}",
                "path": str(auth_file)
            }
        else:
            return {
                "status": "error",
                "message": "Test passed but auth file not found"
            }
    else:
        return {
            "status": "error",
            "message": "Failed to save auth state",
            "error": result["stderr"]
        }

@mcp.tool()
async def analyze_screenshot(
    screenshot_path: str,
    description: str = ""
) -> Dict[str, Any]:
    """
    Analyze a screenshot from UI tests.
    
    Args:
        screenshot_path: Path to screenshot file
        description: Optional description of what to look for
    
    Returns:
        Analysis results including detected elements and issues
    """
    screenshot_file = SCREENSHOTS_DIR / screenshot_path
    
    if not screenshot_file.exists():
        # Try in UI tests dir
        screenshot_file = UI_TESTS_DIR / screenshot_path
        
    if not screenshot_file.exists():
        raise ToolError(f"Screenshot not found: {screenshot_path}")
    
    # Read screenshot
    with open(screenshot_file, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    
    # Return screenshot data and basic info
    # In a real implementation, you might use computer vision here
    return {
        "filename": screenshot_file.name,
        "size": screenshot_file.stat().st_size,
        "modified": datetime.fromtimestamp(screenshot_file.stat().st_mtime).isoformat(),
        "image_data": image_data,
        "description": description or "Screenshot from UI test",
        "note": "Visual analysis would require computer vision integration"
    }

@mcp.tool()
async def create_page_object(
    page_name: str,
    elements: Dict[str, str],
    methods: List[str] = None
) -> str:
    """
    Generate a page object class for UI testing.
    
    Args:
        page_name: Name of the page (e.g., "ProductList")
        elements: Dictionary of element name to selector
        methods: List of method names to generate
    
    Returns:
        Generated page object code
    """
    template = '''"""
Page object for {page_name} page.
Generated by UI Test Assistant.
"""

from .base_page import BasePage
from playwright.async_api import Page
from typing import List, Dict, Optional

class {class_name}Page(BasePage):
    """{page_name} page object model."""
    
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        
        # Selectors
{selectors}
    
    # Navigation
    async def goto_{route}(self) -> None:
        """Navigate to {page_name} page."""
        await self.navigate_to("/{route}")
    
    # Actions
{methods}
    
    # Verifications
    async def is_loaded(self) -> bool:
        """Check if page is loaded."""
        try:
            await self.wait_for_element(self.{first_element})
            return True
        except:
            return False
'''
    
    # Generate class name and route
    class_name = page_name.replace(" ", "")
    route = page_name.lower().replace(" ", "_")
    
    # Generate selectors
    selectors = []
    for name, selector in elements.items():
        selectors.append(f'        self.{name} = \'{selector}\'')
    
    # Generate methods
    method_code = []
    if methods:
        for method in methods:
            method_code.append(f'''    async def {method}(self) -> None:
        """TODO: Implement {method}."""
        pass
    ''')
    else:
        # Default methods
        method_code.append('''    async def click_first_item(self) -> None:
        """Click the first item in the list."""
        # TODO: Implement based on page structure
        pass
    ''')
    
    first_element = list(elements.keys())[0] if elements else "page_title"
    
    return template.format(
        page_name=page_name,
        class_name=class_name,
        route=route,
        selectors="\n".join(selectors),
        methods="\n".join(method_code),
        first_element=first_element
    )

@mcp.tool()
async def get_test_report() -> Dict[str, Any]:
    """
    Get the latest test execution report.
    
    Returns:
        Test report summary with pass/fail counts and details
    """
    # Look for HTML report
    html_report = REPORTS_DIR / "test_report.html"
    
    if html_report.exists():
        # Parse basic info from HTML report
        with open(html_report, 'r') as f:
            content = f.read()
        
        # Extract summary (basic parsing)
        import re
        passed = len(re.findall(r'class="passed"', content))
        failed = len(re.findall(r'class="failed"', content))
        
        return {
            "report_path": str(html_report),
            "generated": datetime.fromtimestamp(html_report.stat().st_mtime).isoformat(),
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": passed + failed
            }
        }
    else:
        return {
            "report_path": None,
            "message": "No test report found. Run tests with --report flag to generate."
        }

# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "ui_test_server:mcp",
        host="0.0.0.0",
        port=8090,
        reload=True
    )