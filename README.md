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
- **Slack Integration**: Tenant-specific webhooks for task notifications and audit logs, configurable via UI
- **AEE Integration**: Built-in support for Ad Effectiveness Engine signals via key-value targeting
- **Admin UI**: Secure web-based interface with Google OAuth authentication for tenant management
- **Operations Dashboard**: Real-time monitoring of media buys, tasks, and audit trails
- **Database Persistence**: All operations logged to database with full audit trail
- **Database Migrations**: Automated schema management with Alembic for consistent updates
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

# Install dependencies
uv sync

# Run database migrations (creates/updates schema)
uv run python migrate.py

# Initialize default data (optional)
uv run python init_database.py
```

### Environment Configuration

Create a `.env` file in your project root with the following variables:

```bash
# API Keys (required)
GEMINI_API_KEY=your-gemini-api-key-here

# OAuth Configuration (choose one method)
# Method 1: Environment variables (recommended)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Method 2: File path (legacy - not recommended)
# GOOGLE_OAUTH_CREDENTIALS_FILE=/path/to/client_secret.json

# Admin Configuration
SUPER_ADMIN_EMAILS=admin1@example.com,admin2@example.com
SUPER_ADMIN_DOMAINS=example.com,company.com

# Port Configuration (defaults shown)
POSTGRES_PORT=5432
ADCP_SALES_PORT=8080
ADMIN_UI_PORT=8001

# Database URL (for Docker deployments)
DATABASE_URL=postgresql://adcp_user:secure_password_change_me@postgres:5432/adcp
```

**Important Notes:**
- OAuth credentials should be set as environment variables, not mounted files
- Each Conductor workspace automatically gets unique ports
- Slack webhooks are configured per-tenant in the Admin UI
- See `.env.example` for a complete template

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
open http://localhost:8001  # OAuth-based secure login (default port, configurable via ADMIN_UI_PORT)

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

## Admin UI & Operations Dashboard

The system includes a comprehensive web-based administration interface:

### Admin UI Features
- **Tenant Management**: Create and configure multi-tenant publishers
- **User Management**: OAuth-based user authentication with role-based access
- **Ad Server Setup**: Guided configuration for GAM, Kevel, Triton adapters
- **Principal Management**: Create API clients and map to ad server entities
- **Operations Dashboard**: Real-time monitoring and reporting
- **Slack Integration**: Configure webhooks for notifications per tenant

### Accessing the Admin UI
```bash
# Start with Docker
docker-compose up -d

# Access at http://localhost:8001
# Login with Google OAuth
```

### Operations Dashboard
The Operations Dashboard provides comprehensive visibility:
- **Summary Metrics**: Active media buys, total spend, pending tasks
- **Media Buys**: List all campaigns with filtering by status
- **Tasks**: Track manual approvals and pending operations
- **Audit Logs**: Complete audit trail with security violation alerts

## Architecture Overview

### Core Components

- **`main.py`**: FastMCP server implementing the AdCP protocol
  - Authentication via `x-adcp-auth` headers
  - Principal-based multi-tenancy
  - Tools: `list_products`, `create_media_buy`, `get_media_buy_delivery`, `update_performance_index`
  - Database persistence for all operations

- **`admin_ui.py`**: Flask-based administration interface
  - Google OAuth authentication
  - Tenant and user management
  - Operations monitoring dashboard
  - Secure role-based access control

- **`adapters/`**: Ad server integrations following the adapter pattern
  - `base.py`: Abstract base class defining the interface
  - `mock_ad_server.py`: Full-featured mock implementation
  - `google_ad_manager.py`: Google Ad Manager integration
  - Each adapter handles its own dry-run logging and audit trail

- **`schemas.py`**: Pydantic models for API contracts
  - `Principal`: Encapsulates identity and adapter mappings
  - Request/Response models for all operations
  - Strict validation ensuring data integrity

- **`database_schema.py`**: Multi-database schema definitions
  - Support for SQLite (development) and PostgreSQL (production)
  - Tables: tenants, users, principals, products, media_buys, tasks, audit_logs
  - Full referential integrity and indexing

- **`audit_logger.py`**: Comprehensive audit logging system
  - Database-backed audit trail with tenant isolation
  - Security violation tracking
  - File backup for redundancy

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

### Slack Integration

Each tenant can configure Slack notifications through the Admin UI:

1. **Navigate to Integrations Tab**: In tenant management, click on the Integrations tab
2. **Configure Webhooks**:
   - **Task Notifications**: Receives alerts for new tasks and creative approvals
   - **Audit Log Channel** (optional): Separate channel for security events and high-value transactions
3. **Test Configuration**: Use the "Send Test Message" button to verify webhook setup

Notifications are sent for:
- New tasks requiring attention
- Creative approval requests
- Security violations (audit channel)
- Failed operations (audit channel)
- High-value transactions over $10,000 (audit channel)

Configuration is stored per-tenant in the database - no environment variables required.

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

Deploy the AdCP Sales Agent to Fly.io with managed PostgreSQL and automatic SSL:

```bash
# 1. Install Fly CLI and login
fly auth login

# 2. Create the app
fly apps create adcp-sales-agent

# 3. Create PostgreSQL cluster
fly postgres create --name adcp-db --region iad
fly postgres attach adcp-db --app adcp-sales-agent

# 4. Create persistent volume for file storage
fly volumes create adcp_data --region iad --size 1

# 5. Set required secrets
fly secrets set \
  GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com" \
  GOOGLE_CLIENT_SECRET="your-client-secret" \
  SUPER_ADMIN_EMAILS="admin@example.com" \
  SUPER_ADMIN_DOMAINS="example.com" \
  GEMINI_API_KEY="your-gemini-api-key"

# 6. Configure OAuth redirect URI in Google Cloud Console:
#    https://adcp-sales-agent.fly.dev/auth/google/callback

# 7. Deploy
fly deploy
```

After deployment:
- Admin UI: https://adcp-sales-agent.fly.dev/admin
- MCP Endpoint: https://adcp-sales-agent.fly.dev/mcp/
- Single OAuth redirect URI for all authentication flows

For detailed deployment instructions and architecture overview, see the [Fly.io Deployment section in CLAUDE.md](CLAUDE.md#flyio-deployment).

## Documentation

### Protocol Specification
- **[AdCP Sales Agent Specification](adcp-spec/)**: Complete protocol specification, API reference, and design decisions

### Implementation Guides  
- **[Platform Mapping Guide](docs/platform-mapping-guide.md)**: How AdCP concepts map to ad servers
- **[Targeting Implementation](docs/targeting-implementation.md)**: Targeting capabilities and examples
- **[Adapter Development](docs/adapter-development.md)**: How to add new ad server support
- **[Deployment Guide](CLAUDE.md#flyio-deployment)**: Fly.io deployment instructions

### Docker Deployment

Complete Docker Compose setup with PostgreSQL and Admin UI:

```bash
# 1. Create .env file with required configuration (see Environment Configuration above)
cp .env.example .env
# Edit .env with your API keys and OAuth credentials

# 2. Start services with Docker Compose
docker-compose up -d

# Services available at:
# - MCP Server: http://localhost:8080/mcp/
# - Admin UI: http://localhost:8001 (Google OAuth)
# - PostgreSQL: localhost:5432

# Note: Database migrations run automatically on startup via entrypoint.sh

# View logs
docker-compose logs -f

# Create new tenant
docker exec -it adcp-server python setup_tenant.py "Publisher Name"
```

See [Docker Deployment Guide](docs/docker-deployment.md) for production configuration.

### Additional Guides

- **[Database Configuration](docs/database-configuration.md)**: SQLite vs PostgreSQL setup
- **[Database Migrations](docs/database-migrations.md)**: Schema version control with Alembic
- **[Multi-Tenant Architecture](docs/multi-tenant-architecture.md)**: Hosting multiple publishers
- **[Admin UI Guide](docs/admin-ui-guide.md)**: Managing tenants with Google OAuth
- **[Google OAuth Setup](docs/google-oauth-setup.md)**: Configuring secure authentication
- **[Creative Auto-Approval](docs/creative-auto-approval.md)**: Configuring creative workflows
- **[Manual Approval Mode](docs/manual-approval-mode.md)**: Human-in-the-loop setup
- **[AEE Integration](docs/aee-integration.md)**: Ad Effectiveness Engine signals
