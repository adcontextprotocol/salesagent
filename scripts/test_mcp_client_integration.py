#!/usr/bin/env python3
"""
Automated MCP Client Integration Test Runner
This script tests the browser MCP client integration without requiring manual browser testing.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("❌ Missing requests library. Install with: pip install requests")
    sys.exit(1)


class MCPClientIntegrationTester:
    def __init__(self, base_url: str = "http://localhost:8101"):
        self.base_url = base_url
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(total=3, status_forcelist=[429, 500, 502, 503, 504], backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.test_results = []
        self.readiness_score = 0

    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log test result with details."""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")

        self.test_results.append({"test": test_name, "passed": passed, "details": details})

        if passed:
            self.readiness_score += 10

    def test_server_health(self) -> bool:
        """Test if server is running and healthy."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            passed = response.status_code == 200
            self.log_test("Server Health Check", passed, f"Status: {response.status_code}")
            return passed
        except Exception as e:
            self.log_test("Server Health Check", False, f"Error: {str(e)}")
            return False

    def test_static_file_serving(self) -> bool:
        """Test if static MCP client file is served correctly."""
        try:
            response = self.session.get(f"{self.base_url}/static/js/mcp-browser-client.js", timeout=5)
            passed = (
                response.status_code == 200
                and "createMCPClient" in response.text
                and "BrowserMCPClient" in response.text
            )

            details = f"Status: {response.status_code}, Size: {len(response.text)} bytes"
            if not passed and response.status_code == 200:
                details += " (Missing expected functions)"

            self.log_test("Static MCP Client File", passed, details)
            return passed
        except Exception as e:
            self.log_test("Static MCP Client File", False, f"Error: {str(e)}")
            return False

    def test_landing_page_loads(self) -> bool:
        """Test if landing page loads with MCP client integration."""
        try:
            # Use a test hostname
            headers = {"Host": "test-publisher.localhost"}
            response = self.session.get(f"{self.base_url}/", headers=headers, timeout=10)

            content = response.text
            checks = [
                ("/static/js/mcp-browser-client.js" in content, "MCP client script included"),
                ("window.createMCPClient" in content, "Client factory function used"),
                ("window.searchProducts" in content, "Search function exposed globally"),
                ("window.fillExample" in content, "Example function exposed globally"),
            ]

            passed_checks = [check[0] for check in checks]
            passed = response.status_code == 200 and all(passed_checks)

            failed_checks = [check[1] for check in checks if not check[0]]
            details = f"Status: {response.status_code}"
            if failed_checks:
                details += f", Missing: {', '.join(failed_checks)}"

            self.log_test("Landing Page MCP Integration", passed, details)
            return passed
        except Exception as e:
            self.log_test("Landing Page MCP Integration", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self) -> dict[str, Any]:
        """Run all integration tests and return summary."""
        print("🧪 Starting MCP Client Integration Tests...")
        print("=" * 50)

        start_time = time.time()

        # Run tests in order of dependency
        tests = [
            self.test_server_health,
            self.test_static_file_serving,
            self.test_landing_page_loads,
        ]

        passed_count = 0
        for test_func in tests:
            if test_func():
                passed_count += 1
            print()  # Add spacing between tests

        duration = time.time() - start_time
        total_tests = len(tests)

        print("=" * 50)
        print("📊 Test Summary:")
        print(f"   Passed: {passed_count}/{total_tests}")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Readiness Score: {self.readiness_score}/{total_tests * 10}")

        # Provide specific recommendations
        if passed_count < total_tests:
            print("\n🔧 Recommended Fixes:")
            failed_tests = [result for result in self.test_results if not result["passed"]]
            for failed in failed_tests:
                print(f"   • {failed['test']}: {failed['details']}")
        else:
            print("\n🎉 All tests passed! MCP client integration is ready.")

        return {
            "passed": passed_count,
            "total": total_tests,
            "duration": duration,
            "readiness_score": self.readiness_score,
            "details": self.test_results,
        }


def main():
    """Main test runner entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test MCP Client Integration")
    parser.add_argument(
        "--url", default="http://localhost:8101", help="Base URL for testing (default: http://localhost:8101)"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    tester = MCPClientIntegrationTester(args.url)
    results = tester.run_all_tests()

    if args.json:
        print(json.dumps(results, indent=2))

    # Exit with error code if tests failed
    sys.exit(0 if results["passed"] == results["total"] else 1)


if __name__ == "__main__":
    main()
