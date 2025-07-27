# AdCP Buy-Side Server (V2.3)

This project is a Python-based reference implementation of the Advertising Campaign Protocol (AdCP) V2.3 buy-side server. It demonstrates how publishers expose advertising inventory to AI-driven clients through a standardized, multi-tenant API.

## Key Features

- **Natural Language Processing**: Receive campaign briefs in plain language and get AI-powered product recommendations
- **Multi-Tenant Architecture**: Principal-based authentication with data isolation
- **Multiple Ad Server Support**: Adapter pattern supporting Google Ad Manager, Kevel, Triton, and mock implementations
- **Full Campaign Lifecycle**: From discovery through creative submission, delivery tracking, and optimization
- **Dry-Run Mode**: See exact API calls that would be made without executing them
- **Realistic Simulation**: Proper budget pacing and delivery simulation over campaign duration

## Quick Start

### Prerequisites
- Python 3.12+
- `uv` for package management

### Installation
```bash
# Install uv if not already installed
pip install uv

# Install dependencies
uv sync

# Initialize database
uv run python database.py
```

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
# Run with mock adapter (default)
python run_simulation.py

# Run with dry-run mode to see API calls
python run_simulation.py --dry-run --adapter gam

# See all options
python run_simulation.py --help
```

This will:
1. Start the AdCP server on a random port
2. Run a full campaign lifecycle simulation
3. Show detailed progress through all 7 phases
4. Clean up and exit

### Running the Server Standalone

```bash
# Start the server (default port 8000)
./run_server.py

# Custom port
ADCP_SALES_PORT=9000 ./run_server.py

# Test with MCP client
./client_mcp.py --token "purina_secret_token_abc123" --test

# In another terminal, run a client simulation
python simulation_full.py http://localhost:8000
```

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

### Authentication & Multi-Tenancy

The system uses bearer token authentication with principal isolation:

1. Client sends `x-adcp-auth: <token>` header
2. Server validates token and identifies principal
3. All operations are scoped to that principal
4. Each principal has adapter-specific IDs (e.g., GAM advertiser ID)

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

### Docker

A Dockerfile is included for containerized deployment:

```bash
# Build
docker build -t adcp-sales-agent .

# Run
docker run -p 8000:8000 \
  -e PRODUCTION=true \
  -e AD_SERVER_ADAPTER=mock \
  adcp-sales-agent
```
