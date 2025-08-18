"""
End-to-end test specific fixtures.

These fixtures are for complete system tests.
"""

import subprocess
import time

import pytest
import requests


@pytest.fixture(scope="session")
def docker_services():
    """Start Docker services for E2E tests."""
    # Check if Docker is available
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available")

    # Start services
    subprocess.run(["docker-compose", "up", "-d"], check=True)

    # Wait for services to be ready
    time.sleep(10)

    yield

    # Cleanup
    subprocess.run(["docker-compose", "down"], check=False)


@pytest.fixture
def live_server(docker_services):
    """Provide URLs for live services."""
    return {
        "mcp": "http://localhost:8080",
        "admin": "http://localhost:8001",
        "postgres": "postgresql://adcp_user:test_password@localhost:5432/adcp_test",
    }


@pytest.fixture
def e2e_client(live_server):
    """Provide client for E2E testing."""
    from fastmcp.client import Client
    from fastmcp.client.transports import StreamableHttpTransport

    # Create MCP client
    headers = {"x-adcp-auth": "test_token"}
    transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)
    client = Client(transport=transport)

    return client


@pytest.fixture
def complete_campaign_setup(live_server):
    """Set up a complete campaign for E2E testing."""

    # Create tenant via Admin API
    response = requests.post(
        f"{live_server['admin']}/api/v1/superadmin/tenants",
        headers={"X-Superadmin-API-Key": "test_key"},
        json={"name": "E2E Test Publisher", "subdomain": "e2e-test", "billing_plan": "standard", "ad_server": "mock"},
    )

    if response.status_code != 201:
        pytest.skip(f"Failed to create tenant: {response.text}")

    tenant_data = response.json()

    # Create principal
    response = requests.post(
        f"{live_server['admin']}/api/tenant/{tenant_data['tenant_id']}/principals",
        json={"name": "E2E Test Advertiser", "platform_mappings": {"mock": {"advertiser_id": "test_adv_123"}}},
    )

    principal_data = response.json()

    return {"tenant": tenant_data, "principal": principal_data, "auth_token": principal_data.get("access_token")}


@pytest.fixture
def browser_session():
    """Provide browser session for UI testing."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        yield page

        browser.close()


@pytest.fixture
def performance_monitor():
    """Monitor performance during E2E tests."""
    import time

    import psutil

    class PerformanceMonitor:
        def __init__(self):
            self.start_time = time.time()
            self.start_cpu = psutil.cpu_percent()
            self.start_memory = psutil.virtual_memory().percent
            self.metrics = []

        def checkpoint(self, name):
            self.metrics.append(
                {
                    "name": name,
                    "time": time.time() - self.start_time,
                    "cpu": psutil.cpu_percent(),
                    "memory": psutil.virtual_memory().percent,
                }
            )

        def report(self):
            duration = time.time() - self.start_time
            print("\nPerformance Report:")
            print(f"Total Duration: {duration:.2f}s")
            print(f"CPU Usage: {self.start_cpu:.1f}% -> {psutil.cpu_percent():.1f}%")
            print(f"Memory Usage: {self.start_memory:.1f}% -> {psutil.virtual_memory().percent:.1f}%")

            if self.metrics:
                print("\nCheckpoints:")
                for metric in self.metrics:
                    print(
                        f"  {metric['name']}: {metric['time']:.2f}s (CPU: {metric['cpu']:.1f}%, Mem: {metric['memory']:.1f}%)"
                    )

    monitor = PerformanceMonitor()

    yield monitor

    monitor.report()
