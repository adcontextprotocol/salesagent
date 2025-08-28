"""
End-to-end test specific fixtures.

These fixtures are for complete system tests that exercise the full AdCP protocol.
Implements testing hooks from https://github.com/adcontextprotocol/adcp/pull/34
"""

import json
import subprocess
import time
import uuid

import httpx
import pytest
import requests


@pytest.fixture(scope="session")
def docker_services_e2e():
    """Start Docker services for E2E tests with proper health checks."""
    # Check if Docker is available
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available")

    # Check if services are already running
    result = subprocess.run(["docker-compose", "ps", "--format", "json"], capture_output=True, text=True)

    services_running = False
    if result.returncode == 0 and result.stdout:
        try:
            # Parse JSON output to check service status
            services = json.loads(result.stdout) if result.stdout.startswith("[") else [json.loads(result.stdout)]
            services_running = any(s.get("State") == "running" for s in services)
        except (json.JSONDecodeError, TypeError):
            # Fallback to simple check
            services_running = "running" in result.stdout.lower()

    if not services_running:
        print("Starting Docker services...")
        subprocess.run(["docker-compose", "up", "-d"], check=True)

        # Wait for services to be healthy
        max_wait = 60
        start_time = time.time()

        mcp_ready = False
        a2a_ready = False

        while time.time() - start_time < max_wait:
            # Check MCP server health
            if not mcp_ready:
                try:
                    response = requests.get("http://localhost:8155/health", timeout=2)
                    if response.status_code == 200:
                        print("✓ MCP server is ready")
                        mcp_ready = True
                except requests.RequestException:
                    pass

            # Check A2A server health
            if not a2a_ready:
                try:
                    # A2A server typically responds to a basic GET request
                    response = requests.get("http://localhost:8091/", timeout=2)
                    if response.status_code in [200, 404, 405]:  # Any response means it's up
                        print("✓ A2A server is ready")
                        a2a_ready = True
                except requests.RequestException:
                    pass

            # Both services ready
            if mcp_ready and a2a_ready:
                break

            time.sleep(2)
        else:
            if not mcp_ready:
                pytest.fail("MCP server did not become healthy in time")
            if not a2a_ready:
                pytest.fail("A2A server did not become healthy in time")
    else:
        print("✓ Docker services already running")

    yield

    # Cleanup based on --keep-data flag
    # Note: pytest.config.getoption is not available in yield, would need request fixture
    # For now, skip cleanup
    pass


@pytest.fixture
def live_server(docker_services_e2e):
    """Provide URLs for live services with correct ports."""
    return {
        "mcp": "http://localhost:8155",  # From .env ADCP_SALES_PORT
        "a2a": "http://localhost:8091",  # From docker-compose.yml A2A_PORT
        "admin": "http://localhost:8076",  # From .env ADMIN_UI_PORT
        "postgres": "postgresql://adcp_user:secure_password_change_me@localhost:5507/adcp",
    }


@pytest.fixture
async def test_auth_token(live_server):
    """Create or get a test principal with auth token."""
    # Try to create a test principal via Docker exec
    # This ensures we have a valid token for testing
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "set-up-production-tenants-adcp-server-1",
            "python",
            "-c",
            """
import sys
sys.path.insert(0, '/app')
from src.core.database.models import Principal, Tenant
from src.core.database.connection import get_db_session
import secrets

with get_db_session() as session:
    # Use the default tenant that already exists
    tenant = session.query(Tenant).filter_by(tenant_id='default').first()
    if not tenant:
        # Create default tenant if it doesn't exist
        tenant = Tenant(
            tenant_id='default',
            name='Default Publisher',
            subdomain='default',
            ad_server='mock',
            admin_token=secrets.token_urlsafe(32)
        )
        session.add(tenant)
        session.commit()

    # Check if test principal exists in default tenant
    principal = session.query(Principal).filter_by(
        tenant_id='default',
        name='E2E Test Advertiser'
    ).first()

    if not principal:
        principal = Principal(
            tenant_id='default',
            principal_id='e2e-test-principal',
            name='E2E Test Advertiser',
            access_token=secrets.token_urlsafe(32),
            platform_mappings={'mock': {'advertiser_id': 'test_123'}}
        )
        session.add(principal)
        session.commit()

    print(principal.access_token)
""",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0 and result.stdout:
        return result.stdout.strip()
    else:
        # Fallback to known working token from previous tests
        return "1sNG-OxWfEsELsey-6H6IGg1HCxrpbtneGfW4GkSb10"


@pytest.fixture
async def e2e_client(live_server, test_auth_token):
    """Provide async client for E2E testing with testing hooks."""
    from fastmcp.client import Client
    from fastmcp.client.transports import StreamableHttpTransport

    # Create MCP client with test session ID
    test_session_id = str(uuid.uuid4())
    headers = {
        "x-adcp-auth": await test_auth_token,
        "X-Test-Session-ID": test_session_id,
        "X-Dry-Run": "true",  # Always use dry-run for tests
    }

    transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)
    client = Client(transport=transport)

    async with client:
        yield client


@pytest.fixture
async def clean_test_data(live_server, request):
    """Clean up test data after tests complete."""
    yield

    # Cleanup happens after test completes
    if not request.config.getoption("--keep-data", False):
        # Could add database cleanup here
        pass


@pytest.fixture
async def a2a_client(live_server, test_auth_token):
    """Provide A2A client for testing."""
    async with httpx.AsyncClient() as client:
        client.base_url = live_server["a2a"]
        client.headers.update(
            {
                "Authorization": f"Bearer {await test_auth_token}",
                "X-Test-Session-ID": str(uuid.uuid4()),
                "X-Dry-Run": "true",
            }
        )
        yield client


@pytest.fixture
def performance_monitor():
    """Monitor performance during E2E tests."""
    try:
        import psutil
    except ImportError:
        # Skip if psutil not available
        class DummyMonitor:
            def checkpoint(self, name):
                pass

            def report(self):
                pass

        yield DummyMonitor()
        return

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
            print(f"\n⏱ Performance: {duration:.2f}s total")
            if self.metrics:
                for m in self.metrics:
                    print(f"  • {m['name']}: {m['time']:.2f}s")

    monitor = PerformanceMonitor()
    yield monitor
    monitor.report()
