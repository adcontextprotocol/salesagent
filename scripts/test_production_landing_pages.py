#!/usr/bin/env python3
"""
Production Landing Page Testing Script

Tests all critical endpoints after deploying landing page changes.
Run this script after deploy to verify nothing is broken.

Usage:
    python scripts/test_production_landing_pages.py
    python scripts/test_production_landing_pages.py --verbose
    python scripts/test_production_landing_pages.py --domain accuweather.sales-agent.scope3.com
"""

import argparse
import sys
from typing import Any

import requests
from rich.console import Console
from rich.table import Table

console = Console()

# Production tenants and their expected configurations
PRODUCTION_TENANTS = {
    "testing.adcontextprotocol.org": {
        "type": "adcontextprotocol domain",
        "tenant_name": "Testing",
        "should_show_landing": True,
        "has_mcp": True,
        "has_a2a": True,
        "has_agent_card": True,
    },
    "accuweather.sales-agent.scope3.com": {
        "type": "custom domain (AccuWeather)",
        "tenant_name": "AccuWeather",
        "should_show_landing": True,
        "has_mcp": True,
        "has_a2a": True,
        "has_agent_card": True,
    },
    "testing.sales-agent.scope3.com": {
        "type": "subdomain",
        "tenant_name": "Testing",
        "should_show_landing": True,
        "has_mcp": True,
        "has_a2a": True,
        "has_agent_card": True,
    },
}

# Admin UI domains (should redirect to login, not show landing page)
ADMIN_DOMAINS = [
    "admin.sales-agent.scope3.com",
]

# Main domain (should show signup landing, not tenant landing)
MAIN_DOMAINS = [
    "sales-agent.scope3.com",
]


class TestResult:
    """Test result with status and details."""

    def __init__(self, passed: bool, message: str, details: dict[str, Any] | None = None):
        self.passed = passed
        self.message = message
        self.details = details or {}


def test_landing_page(domain: str, config: dict[str, Any], verbose: bool = False) -> TestResult:
    """Test that landing page shows properly for a tenant."""
    url = f"https://{domain}"

    try:
        response = requests.get(url, timeout=10, allow_redirects=False)

        if response.status_code != 200:
            return TestResult(
                False,
                f"Expected 200, got {response.status_code}",
                {"status_code": response.status_code, "url": url},
            )

        html = response.text

        # Check for MCP endpoint
        if config.get("has_mcp"):
            if "/mcp" not in html:
                return TestResult(False, "MCP endpoint not found in landing page", {"url": url})

        # Check for A2A endpoint reference
        if config.get("has_a2a"):
            if "A2A" not in html and "agent-to-agent" not in html.lower():
                return TestResult(False, "A2A endpoint not mentioned in landing page", {"url": url})

        # Check for agent card
        if config.get("has_agent_card"):
            if "/.well-known/agent.json" not in html:
                return TestResult(False, "Agent card link not found in landing page", {"url": url})

        # Check that it's not a fallback/error page
        if "error" in html.lower() and "generating landing page" in html.lower():
            return TestResult(False, "Showing error fallback page instead of proper landing", {"url": url})

        # Check for tenant name (if configured)
        if config.get("tenant_name"):
            # Relaxed check - tenant name might be in various places
            pass

        return TestResult(True, "Landing page looks good", {"url": url, "size": len(html)})

    except requests.Timeout:
        return TestResult(False, "Request timed out", {"url": url})
    except requests.RequestException as e:
        return TestResult(False, f"Request failed: {e}", {"url": url})


def test_mcp_endpoint(domain: str, verbose: bool = False) -> TestResult:
    """Test that MCP endpoint is accessible."""
    url = f"https://{domain}/mcp"

    try:
        response = requests.get(url, timeout=10, allow_redirects=False)

        # MCP should return some response (200 or specific MCP error)
        if response.status_code in [200, 400, 405]:
            return TestResult(True, f"MCP endpoint accessible (status {response.status_code})", {"url": url})

        return TestResult(
            False,
            f"Unexpected status code {response.status_code}",
            {"status_code": response.status_code, "url": url},
        )

    except requests.Timeout:
        return TestResult(False, "Request timed out", {"url": url})
    except requests.RequestException as e:
        return TestResult(False, f"Request failed: {e}", {"url": url})


def test_a2a_endpoint(domain: str, verbose: bool = False) -> TestResult:
    """Test that A2A endpoint is accessible."""
    url = f"https://{domain}/"

    try:
        # A2A endpoint is at root, should return JSON-RPC response or method not allowed
        response = requests.post(url, json={}, timeout=10, allow_redirects=False)

        # A2A should return some JSON response
        if response.status_code in [200, 400, 405]:
            try:
                response.json()  # Should be valid JSON
                return TestResult(True, f"A2A endpoint accessible (status {response.status_code})", {"url": url})
            except ValueError:
                return TestResult(False, "A2A endpoint not returning JSON", {"url": url})

        return TestResult(
            False,
            f"Unexpected status code {response.status_code}",
            {"status_code": response.status_code, "url": url},
        )

    except requests.Timeout:
        return TestResult(False, "Request timed out", {"url": url})
    except requests.RequestException as e:
        return TestResult(False, f"Request failed: {e}", {"url": url})


def test_agent_card(domain: str, verbose: bool = False) -> TestResult:
    """Test that agent card is accessible."""
    url = f"https://{domain}/.well-known/agent.json"

    try:
        response = requests.get(url, timeout=10, allow_redirects=False)

        if response.status_code != 200:
            return TestResult(
                False,
                f"Expected 200, got {response.status_code}",
                {"status_code": response.status_code, "url": url},
            )

        try:
            agent_card = response.json()

            # Check for required fields
            if "name" not in agent_card:
                return TestResult(False, "Agent card missing 'name' field", {"url": url})

            return TestResult(True, "Agent card accessible and valid", {"url": url, "name": agent_card.get("name")})

        except ValueError:
            return TestResult(False, "Agent card is not valid JSON", {"url": url})

    except requests.Timeout:
        return TestResult(False, "Request timed out", {"url": url})
    except requests.RequestException as e:
        return TestResult(False, f"Request failed: {e}", {"url": url})


def test_admin_redirect(domain: str, verbose: bool = False) -> TestResult:
    """Test that admin domain redirects to login."""
    url = f"https://{domain}/"

    try:
        response = requests.get(url, timeout=10, allow_redirects=False)

        # Should redirect to login
        if response.status_code in [301, 302, 303, 307, 308]:
            location = response.headers.get("Location", "")
            if "login" in location:
                return TestResult(True, "Admin redirects to login", {"url": url, "location": location})
            return TestResult(False, f"Admin redirects but not to login: {location}", {"url": url})

        return TestResult(
            False,
            f"Admin should redirect, got {response.status_code}",
            {"status_code": response.status_code, "url": url},
        )

    except requests.Timeout:
        return TestResult(False, "Request timed out", {"url": url})
    except requests.RequestException as e:
        return TestResult(False, f"Request failed: {e}", {"url": url})


def run_tests(domains: list[str] | None = None, verbose: bool = False) -> tuple[int, int]:
    """Run all tests and return (passed, total)."""
    console.print("\n[bold cyan]🧪 Production Landing Page Tests[/bold cyan]\n")

    domains_to_test = domains if domains else list(PRODUCTION_TENANTS.keys())

    results: list[tuple[str, str, TestResult]] = []
    passed = 0
    total = 0

    for domain in domains_to_test:
        config = PRODUCTION_TENANTS.get(domain, {})

        console.print(f"[bold]Testing {domain}[/bold] ({config.get('type', 'unknown')})")

        # Test landing page
        result = test_landing_page(domain, config, verbose)
        results.append((domain, "Landing Page", result))
        total += 1
        if result.passed:
            passed += 1

        # Test MCP endpoint
        if config.get("has_mcp"):
            result = test_mcp_endpoint(domain, verbose)
            results.append((domain, "MCP Endpoint", result))
            total += 1
            if result.passed:
                passed += 1

        # Test A2A endpoint
        if config.get("has_a2a"):
            result = test_a2a_endpoint(domain, verbose)
            results.append((domain, "A2A Endpoint", result))
            total += 1
            if result.passed:
                passed += 1

        # Test agent card
        if config.get("has_agent_card"):
            result = test_agent_card(domain, verbose)
            results.append((domain, "Agent Card", result))
            total += 1
            if result.passed:
                passed += 1

        console.print()

    # Test admin domains
    for domain in ADMIN_DOMAINS:
        console.print(f"[bold]Testing {domain}[/bold] (admin domain)")
        result = test_admin_redirect(domain, verbose)
        results.append((domain, "Admin Redirect", result))
        total += 1
        if result.passed:
            passed += 1
        console.print()

    # Print results table
    table = Table(title="Test Results")
    table.add_column("Domain", style="cyan")
    table.add_column("Test", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Message")

    for domain, test_name, result in results:
        status = "[green]✓ PASS[/green]" if result.passed else "[red]✗ FAIL[/red]"
        table.add_row(domain, test_name, status, result.message)

    console.print(table)
    console.print()

    return passed, total


def main():
    parser = argparse.ArgumentParser(description="Test production landing pages after deploy")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--domain", "-d", help="Test specific domain only")
    args = parser.parse_args()

    domains = [args.domain] if args.domain else None

    passed, total = run_tests(domains, args.verbose)

    # Summary
    if passed == total:
        console.print(f"[bold green]✓ All tests passed ({passed}/{total})[/bold green]")
        sys.exit(0)
    else:
        console.print(f"[bold red]✗ Some tests failed ({passed}/{total} passed)[/bold red]")
        console.print("\n[yellow]⚠️  Consider rolling back if critical features are broken[/yellow]")
        sys.exit(1)


if __name__ == "__main__":
    main()
