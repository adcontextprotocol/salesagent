# AdCP Sales Agent (V2.3)

This project is a Python-based reference implementation of the Advertising Context Protocol (AdCP) V2.3 sales agent. It demonstrates how publishers expose advertising inventory to AI-driven clients through a standardized MCP (Model Context Protocol) interface.

## Key Features

- **MCP Server Implementation**: Built with FastMCP, exposing tools for AI agents to interact with ad inventory
- **Multi-Tenant Architecture**: Database-backed tenant isolation with subdomain routing support
- **Multiple Ad Server Support**: Adapter pattern supporting Google Ad Manager, Kevel, Triton, and mock implementations
- **Advanced Targeting**: Comprehensive targeting system with overlay and managed-only dimensions
- **Creative Management**: Auto-approval workflows, creative groups, and multi-format support
- **Human-in-the-Loop**: Optional manual approval mode for sensitive operations
- **Security & Compliance**: Comprehensive audit logging, principal-based authentication, and adapter security boundaries
- **AEE Integration**: Built-in support for Ad Effectiveness Engine signals via key-value targeting
- **Admin UI**: Secure web-based interface with Google OAuth authentication
- **Dry-Run Mode**: Preview exact API calls without executing them
- **Production Ready**: PostgreSQL support, Docker deployment, and health monitoring

## Quick Start

### Prerequisites
- Python 3.12+
- `uv` for package management
- Optional: PostgreSQL for production deployments

### Installation
```bash
# Install uv if not already installed
pip install uv

# Install dependencies (with PostgreSQL support)
uv sync --extra postgresql

# Initialize database
uv run python database.py
```

### Database Configuration

By default, the server uses SQLite with data stored in `~/.adcp/adcp.db` for persistence.

For production, configure PostgreSQL:

```bash
# PostgreSQL (recommended for production)
export DATABASE_URL=postgresql://user:pass@localhost/adcp

# Or use individual environment variables
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_USER=adcp_user
export DB_PASSWORD=secure_password
```

See [Database Configuration Guide](docs/database-configuration.md) for details.

### Authentication

The server uses token-based authentication with the `x-adcp-auth` header:

```bash
# View demo tokens
./manage_auth.py demo

# List all principals
./manage_auth.py list

# Create new principal
./manage_auth.py create my_company --name "My Company"
```

### Running the Full Simulation

The easiest way to see the system in action is to run the automated simulation:

```bash
# Run with mock adapter (default) - uses temporary test database
python run_simulation.py

# Run with dry-run mode to see API calls
python run_simulation.py --dry-run --adapter gam

# Use production database (careful!)
python run_simulation.py --use-prod-db

# See all options
python run_simulation.py --help
```

This will:
1. Create a temporary test database (unless --use-prod-db is specified)
2. Start the AdCP server on a random port
3. Run a full campaign lifecycle simulation
4. Show detailed progress through all 7 phases
5. Clean up test database and exit

**Note**: By default, simulations use an isolated test database to protect your production data. Use `--use-prod-db` only if you need to test with real data.

### Running the Server Standalone

```bash
# Start the server (default port 8000)
python run_server.py

# Custom port
ADCP_SALES_PORT=9000 python run_server.py

# Access the Admin UI
open http://localhost:8001  # OAuth-based secure login

# Test with MCP client
python client_mcp.py --token "purina_token" --test
```

## Using the MCP Interface

AdCP Sales Agent is an MCP server, not a REST API. AI agents connect using the MCP protocol:

```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

# Connect with authentication
headers = {"x-adcp-auth": "your_access_token"}
transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
client = Client(transport=transport)

# Use the tools
async with client:
    # List available products
    products = await client.tools.list_products()
    
    # Create a media buy
    result = await client.tools.create_media_buy(
        product_ids=["prod_1"],
        total_budget=5000.0,
        flight_start_date="2025-02-01",
        flight_end_date="2025-02-28"
    )
```

### Available MCP Tools

- `list_products` - Discover available ad inventory
- `create_media_buy` - Create new campaigns
- `get_media_buy_delivery` - Check campaign performance
- `update_media_buy` - Modify active campaigns
- `add_creative_assets` - Submit creative materials
- `get_creatives` - List creative assets
- `update_performance_index` - Adjust optimization parameters
- `get_all_media_buy_delivery` - Bulk delivery reporting (admin only)
- `review_pending_creatives` - Approve/reject creatives (admin only)
- `list_human_tasks` - View manual approval queue (admin only)
- `complete_human_task` - Process manual approvals (admin only)

## Architecture Overview

### Core Components

- **`main.py`**: FastMCP server implementing the AdCP protocol
  - Authentication via `x-adcp-auth` headers
  - Principal-based multi-tenancy
  - Tools: `list_products`, `create_media_buy`, `get_media_buy_delivery`, `update_performance_index`

- **`adapters/`**: Ad server integrations following the adapter pattern
  - `base.py`: Abstract base class defining the interface
  - `mock_ad_server.py`: Full-featured mock implementation
  - `google_ad_manager.py`: Google Ad Manager integration
  - Each adapter handles its own dry-run logging

- **`schemas.py`**: Pydantic models for API contracts
  - `Principal`: Encapsulates identity and adapter mappings
  - Request/Response models for all operations
  - Strict validation ensuring data integrity

- **`database.py`**: SQLite database initialization
  - Principals table with authentication tokens
  - Products catalog with targeting templates
  - Sample data for testing

- **`simulation_full.py`**: Comprehensive lifecycle simulation
  - 7 phases: Discovery → Planning → Buying → Creatives → Pre-flight → Monitoring → Optimization
  - Realistic timeline progression
  - Performance tracking and reporting

### Multi-Tenant Architecture

The system supports full database-backed multi-tenancy:

```bash
# Create a new tenant
python setup_tenant.py "Sports Publisher" \
  --subdomain sports \
  --adapter google_ad_manager \
  --gam-network-code 123456

# Access tenant-specific endpoints
http://sports.localhost:8080/mcp/
```

Each tenant has:
- Isolated data (principals, products, media buys)
- Custom configuration (adapters, features, limits)
- Separate authentication tokens
- Optional subdomain routing

### Authentication & Security

The system uses bearer token authentication with comprehensive security:

1. **Token-based auth**: `x-adcp-auth: <token>` header required
2. **Principal isolation**: All operations scoped to authenticated principal
3. **Admin tokens**: Special tokens for administrative operations
4. **Audit logging**: Every operation logged with timestamp and principal
5. **Adapter boundaries**: Each adapter enforces its own security perimeter

### Human-in-the-Loop Support

For publishers requiring manual approval:

```python
# Configure adapter for manual approval
{
  "adapters": {
    "google_ad_manager": {
      "manual_approval_required": true,
      "manual_approval_operations": ["create_media_buy", "update_media_buy"]
    }
  }
}
```

Operations create tasks for human review instead of executing immediately.

### Adapter Pattern

Each ad server adapter:
- Inherits from `AdServerAdapter` base class
- Accepts a `Principal` object for identity
- Implements standard methods (create_media_buy, get_delivery, etc.)
- Provides detailed logging in dry-run mode

Example dry-run output:
```
GoogleAdManager.create_media_buy for principal 'Purina Pet Foods' (GAM advertiser ID: 12345)
(dry-run) Would call: order_service.createOrders([AdCP Order PO-DEMO-2025])
(dry-run)   Advertiser ID: 12345
(dry-run)   Total Budget: $50,000.00
(dry-run)   Flight Dates: 2025-08-01 to 2025-08-15
```

### Advanced Targeting System

The platform supports comprehensive targeting with two access levels:

**Overlay Targeting** (Available to principals):
- Geographic: country, region, metro/DMA, city, postal code
- Device: type, make, OS, browser  
- Content: categories, language, rating
- Audience: segments, interests
- Time: dayparting, days of week
- Frequency: capping rules

**Managed-Only Targeting** (Internal use only):
- `key_value_pairs`: For AEE signal integration
- Platform-specific custom targeting
- Internal optimization parameters

Example targeting overlay:
```json
{
  "geo_country_any_of": ["US", "CA"],
  "device_type_any_of": ["mobile", "desktop"],
  "content_cat_any_of": ["sports", "entertainment"],
  "day_of_week_any_of": ["mon", "tue", "wed", "thu", "fri"],
  "hour_of_day_any_of": [9, 10, 11, 12, 13, 14, 15, 16, 17]
}
```

## Deployment

### Production Deployment (Fly.io)

The server is ready for deployment on Fly.io:

```bash
# Create app
fly apps create adcp-sales-agent

# Set ad server credentials (example for GAM)
fly secrets set AD_SERVER_ADAPTER="gam" --app adcp-sales-agent
fly secrets set GAM_NETWORK_CODE="123456789" --app adcp-sales-agent
fly secrets set GAM_SERVICE_ACCOUNT_JSON='{"type":"service_account"...}' --app adcp-sales-agent

# Deploy
fly deploy --app adcp-sales-agent
```

For detailed deployment instructions, see [FLY_DEPLOYMENT.md](FLY_DEPLOYMENT.md).

## Documentation

### Protocol Specification
- **[AdCP Sales Agent Specification](adcp-spec/)**: Complete protocol specification, API reference, and design decisions

### Implementation Guides  
- **[Platform Mapping Guide](docs/platform-mapping-guide.md)**: How AdCP concepts map to ad servers
- **[Targeting Implementation](docs/targeting-implementation.md)**: Targeting capabilities and examples
- **[Adapter Development](docs/adapter-development.md)**: How to add new ad server support
- **[Deployment Guide](FLY_DEPLOYMENT.md)**: Production deployment instructions

### Docker Deployment

Complete Docker Compose setup with PostgreSQL and Admin UI:

```bash
# Quick start with Docker Compose
docker-compose up -d

# Services available at:
# - MCP Server: http://localhost:8080/mcp/
# - Admin UI: http://localhost:8001 (Google OAuth)
# - PostgreSQL: localhost:5432

# View logs
docker-compose logs -f

# Create new tenant
docker exec -it adcp-server python setup_tenant.py "Publisher Name"
```

See [Docker Deployment Guide](docs/docker-deployment.md) for production configuration.

### Additional Guides

- **[Database Configuration](docs/database-configuration.md)**: SQLite vs PostgreSQL setup
- **[Multi-Tenant Architecture](docs/multi-tenant-architecture.md)**: Hosting multiple publishers
- **[Admin UI Guide](docs/admin-ui-guide.md)**: Managing tenants with Google OAuth
- **[Google OAuth Setup](docs/google-oauth-setup.md)**: Configuring secure authentication
- **[Creative Auto-Approval](docs/creative-auto-approval.md)**: Configuring creative workflows
- **[Manual Approval Mode](docs/manual-approval-mode.md)**: Human-in-the-loop setup
- **[AEE Integration](docs/aee-integration.md)**: Ad Effectiveness Engine signals
