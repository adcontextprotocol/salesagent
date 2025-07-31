# AdCP Sales Agent Server - Claude Agent Notes

## Project Overview

This is a Python-based reference implementation of the Advertising Context Protocol (AdCP) V2.3 sales agent. It demonstrates how publishers expose advertising inventory to AI-driven clients through a standardized MCP (Model Context Protocol) interface.

**Primary Deployment Method**: Docker Compose with PostgreSQL, MCP Server, and Admin UI

The server provides:
- **MCP Server**: FastMCP-based server exposing tools for AI agents (port 8080)
- **Admin UI**: Secure web interface with Google OAuth authentication (port 8001)
- **Multi-Tenant Architecture**: Database-backed tenant isolation with subdomain routing
- **Advanced Targeting**: Comprehensive targeting system with overlay and managed-only dimensions
- **Creative Management**: Auto-approval workflows, creative groups, and admin review
- **Human-in-the-Loop**: Optional manual approval mode for sensitive operations
- **Security & Compliance**: Audit logging, principal-based auth, adapter security boundaries
- **Slack Integration**: Per-tenant webhook configuration (no env vars needed)
- **Production Ready**: PostgreSQL database, Docker deployment, health monitoring

## Key Architecture Decisions

### 1. Database-Backed Multi-Tenancy
- **Tenant Isolation**: Each publisher is a tenant with isolated data
- **Principal System**: Within each tenant, principals (advertisers) have unique tokens
- **Subdomain Routing**: Optional routing like `sports.localhost:8080`
- **Configuration**: Per-tenant adapter config, features, and limits
- **Database Support**: SQLite (dev) and PostgreSQL (production)

### 2. Adapter Pattern for Ad Servers
- Base `AdServerAdapter` class defines the interface
- Implementations for GAM, Kevel, Triton, and Mock
- Each adapter handles its own API call logging in dry-run mode
- Principal object encapsulates identity and adapter mappings
- Adapters can provide custom configuration UIs via Flask routes
- Adapter-specific validation and field definitions

### 3. FastMCP Integration
- Uses FastMCP for the server framework
- HTTP transport with header-based authentication (`x-adcp-auth`)
- Context parameter provides access to HTTP request headers
- Tools are exposed as MCP methods

## Core Components

### `main.py` - Server Implementation
- FastMCP server exposing AdCP tools
- Authentication via `x-adcp-auth` header
- Principal resolution and adapter instantiation
- In-memory state management for media buys

### `schemas.py` - Data Models
- Pydantic models for all API contracts
- `Principal` model with `get_adapter_id()` method
- Request/Response models for all operations
- Adapter-specific response models

### `adapters/` - Ad Server Integrations
- `base.py`: Abstract base class defining the interface
- `mock_ad_server.py`: Mock implementation with realistic simulation
- `google_ad_manager.py`: GAM integration with detailed API logging
- Each adapter accepts a `Principal` object for cleaner architecture

### `simulation_full.py` - Full Lifecycle Test
- 7-phase campaign simulation (discovery → completion)
- Realistic timeline with proper date progression
- Performance tracking and optimization
- Demonstrates all API capabilities

## Recent Major Changes

### Database Migrations Support (Latest)
- **Alembic Integration**: Added Alembic for database schema version control
- **Automatic Migrations**: Migrations run automatically on server startup
- **Multi-Database Support**: Works with both SQLite and PostgreSQL
- **Migration Commands**: `python migrate.py` for running migrations
- **Docker Integration**: `entrypoint.sh` runs migrations before starting server
- **Documentation**: See `docs/database-migrations.md` for detailed guide

### Product Management & Adapter Configuration Improvements
- **Clean Separation of Concerns**: 
  - Basic product fields (name, pricing, countries) in main product form
  - Adapter-specific configuration moved to dedicated UIs
  - Countries field moved to products table (buyer-facing concern)
  - `implementation_config` now exclusively for adapter technical settings
- **Mock Adapter Configuration UI**:
  - Traffic simulation controls (impressions, fill rate, CTR, viewability)
  - Performance simulation (latency, error rates)
  - Test scenarios (normal, high demand, degraded, outage)
  - Debug settings for development
- **UI/UX Improvements**:
  - Fixed creative format cards display with proper CSS
  - Removed duplicate product lists (simplified navigation)
  - Price guidance shown as range for non-guaranteed products
  - "Tenant" terminology removed from user-facing views
  - Dynamic port configuration (no more hardcoded 8001)
- **Database Schema Updates**:
  - Added `countries` JSONB column to products table
  - Added `implementation_config` JSONB column for adapter data
  - Proper PostgreSQL JSONB handling vs SQLite JSON strings

### Adapter-Specific Configuration UI System
- Each adapter can provide its own configuration UI
- Adapters implement `get_config_ui_endpoint()`, `register_ui_routes()`, and `validate_product_config()`
- Google Ad Manager example with comprehensive UI at `/adapters/gam/config/<tenant_id>/<product_id>`
- Mock adapter UI for testing parameters at `/adapters/mock/config/<tenant_id>/<product_id>`
- Separation of basic product settings from adapter-specific configuration

### Operations Dashboard & Database Persistence
- Added comprehensive operations dashboard in Admin UI
- Moved all operational data to database (media_buys, tasks, audit_logs tables)
- Migrated audit logging from file-based to database-backed with redundancy
- Real-time filtering and monitoring of all media buys and tasks
- Summary metrics showing active campaigns, total spend, pending approvals
- Complete audit trail with security violation tracking
- Database persistence for all MCP operations

### Multi-Tenant Architecture
- Moved from file-based config to database-backed tenant management
- Added `tenants`, `products`, `media_buys`, `creatives` tables
- Implemented subdomain-based routing for tenant isolation
- Created `setup_tenant.py` for easy tenant creation
- Added Admin UI with Google OAuth for secure tenant management

### Advanced Targeting System
- Comprehensive targeting dimensions with adapter mappings
- Two-tier access: overlay (principals) vs managed-only (internal)
- AEE integration via `key_value_pairs` targeting
- Platform-specific targeting translation in each adapter
- Targeting capabilities exposed via MCP tools

### Creative Management System
- Creative groups for organization across campaigns
- Auto-approval for standard formats (configurable per tenant)
- Admin review queue for pending creatives
- Creative association with media packages
- Support for multiple creative formats per buy

### Human-in-the-Loop Support
- Optional manual approval mode per adapter
- Task queue for human review (`human_tasks` table)
- AI verification of task completion
- Async operation support (pending → active states)
- Admin tools for task management

### Security Enhancements
- Comprehensive audit logging with `AuditLogger`
- Principal context tracking for all operations
- Adapter security boundaries documented
- Admin-only tools with separate authentication
- Structured logging for compliance

### Production Features
- PostgreSQL support with connection pooling
- Docker multi-stage builds with health checks
- Environment-based configuration
- Graceful shutdown handling
- Prometheus metrics preparation

## Testing Strategy

### 1. Unit Tests (`test_adapters.py`)
- Test adapter interfaces and base functionality
- Verify Principal object behavior
- Schema validation tests

### 2. Integration Tests (`simulation_full.py`)
- Full end-to-end campaign lifecycle
- Tests all API operations in sequence
- Verifies state management and data flow

### 3. Dry-Run Testing (`demo_dry_run.py`)
- Demonstrates adapter-specific API logging
- Shows exact calls that would be made in production
- Useful for debugging integrations

## Configuration

### Docker Setup (Primary Method)

The system runs with Docker Compose, which manages all services:

```yaml
# docker-compose.yml services:
postgres      # PostgreSQL database
adcp-server   # MCP server on port 8080  
admin-ui      # Admin interface on port 8001
```

### Required Configuration (.env file)

```bash
# Minimal .env for Docker deployment
GEMINI_API_KEY=your-gemini-api-key-here
SUPER_ADMIN_EMAILS=bokelley@scope3.com
```

### Important Configuration Notes

1. **Slack Webhooks**: Configure per-tenant in Admin UI, NOT via environment variables
2. **Database**: Docker Compose manages PostgreSQL automatically
3. **OAuth**: Mount your `client_secret*.json` file (see docker-compose.yml)
4. **Ports**: 8080 (MCP), 8001 (Admin UI), 5432 (PostgreSQL)

### Legacy Environment Variables (Standalone Only)

For standalone development without Docker:
- `DATABASE_URL`: Full database connection string
- `DB_TYPE`: Database type: `sqlite` or `postgresql`
- `ADCP_SALES_PORT`: MCP server port (default: 8080)
- `ADMIN_UI_PORT`: Admin UI port (default: 8001)

### Database Schema
```sql
-- Multi-tenant tables
tenants (tenant_id, name, subdomain, config, billing_plan)
principals (tenant_id, principal_id, name, access_token, platform_mappings)
products (tenant_id, product_id, name, formats, targeting_template)
media_buys (tenant_id, media_buy_id, principal_id, status, config, budget, dates)
creatives (tenant_id, creative_id, principal_id, status, format)
creative_associations (media_buy_id, package_id, creative_id)
human_tasks (tenant_id, task_id, task_type, status, assigned_to)
tasks (tenant_id, task_id, media_buy_id, task_type, status, details)
audit_logs (tenant_id, timestamp, operation, principal_id, success, details)
```

### Tenant Configuration
Each tenant has a JSON config in the database:
```json
{
  "adapters": {
    "google_ad_manager": {
      "enabled": true,
      "network_code": "123456",
      "manual_approval_required": false
    }
  },
  "creative_engine": {
    "auto_approve_formats": ["display_300x250"],
    "human_review_required": true
  },
  "features": {
    "max_daily_budget": 10000,
    "enable_aee_signals": true
  },
  "admin_token": "secret_admin_token"
}
```

## Common Operations

### Running the Server (Docker - Recommended)
```bash
# Start all services with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild after code changes
docker-compose build
docker-compose up -d
```

### Running Standalone (Development Only)
```bash
# Run database migrations
python migrate.py

# Initialize default data (if needed)
python init_database.py

# Start MCP server and Admin UI
python run_server.py
```

### Managing Tenants
```bash
# Create new tenant (inside Docker container)
docker exec -it adcp-buy-server-adcp-server-1 python setup_tenant.py "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code 123456

# Access Admin UI
open http://localhost:8001
```

### Running Simulations
```bash
# Full lifecycle with temporary test database
python run_simulation.py

# Dry-run with GAM adapter
python run_simulation.py --dry-run --adapter gam

# Use production database (careful!)
python run_simulation.py --use-prod-db

# Run with custom token
python simulation_full.py http://localhost:8080 \
  --token "your_token" \
  --principal "your_principal"
```

### Using MCP Client
```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

headers = {"x-adcp-auth": "your_token"}
transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
client = Client(transport=transport)

async with client:
    # List products
    products = await client.tools.list_products()
    
    # Create media buy
    result = await client.tools.create_media_buy(
        product_ids=["prod_1"],
        total_budget=5000.0,
        flight_start_date="2025-02-01",
        flight_end_date="2025-02-28"
    )
```

## Debugging Tips

1. **Authentication Issues**: 
   - Check x-adcp-auth header matches token in principals table
   - Verify tenant_id routing for subdomain access
   - Use Admin UI to view/copy correct tokens

2. **Adapter Errors**: 
   - Enable dry-run mode to see exact API calls
   - Check adapter security documentation in `adapters/*_security.md`
   - Verify platform_mappings in principal record

3. **Targeting Issues**:
   - Review targeting capabilities in `targeting_capabilities.py`
   - Check adapter-specific targeting translation
   - Verify overlay vs managed-only access levels

4. **Database Issues**:
   - PostgreSQL: Check JSONB fields are dicts not strings
   - SQLite: Ensure proper boolean handling (not 0/1)
   - Use correct environment variables for connection

5. **Creative Approval**:
   - Check tenant config for auto_approve_formats
   - Review pending creatives in admin UI
   - Verify creative format matches product specifications

## Key Files for Understanding

- **`main.py`**: MCP server implementation and tool definitions
- **`schemas.py`**: All data models and API contracts
- **`config_loader.py`**: Tenant resolution and configuration
- **`targeting_capabilities.py`**: Complete targeting system definition
- **`audit_logger.py`**: Security logging implementation (now database-backed)
- **`database_schema.py`**: Multi-database schema support
- **`admin_ui.py`**: Flask-based admin interface with operations dashboard
- **`templates/operations.html`**: Operations dashboard UI implementation

## Testing Checklist

When making changes, test:
1. ✅ Multi-tenant isolation (create test tenant)
2. ✅ Both SQLite and PostgreSQL databases
3. ✅ Targeting translation for each adapter
4. ✅ Creative approval workflow
5. ✅ Human-in-the-loop task creation
6. ✅ Audit logging for security events (database persistence)
7. ✅ Admin UI with Google OAuth authentication
8. ✅ Operations dashboard functionality (filtering, metrics)
9. ✅ Docker deployment
10. ✅ Media buy persistence to database
11. ✅ Task persistence and status updates

## Recent Improvements Summary

1. **Corrected Naming**: "AdCP Sales Agent" (not AdCP:Buy)
2. **Protocol Name**: "Advertising Context Protocol" (not Campaign)
3. **MCP Interface**: Proper MCP examples (not REST/curl)
4. **Test Database**: Simulations use isolated test DB by default
5. **Token Alignment**: Fixed simulation tokens to match database
6. **Documentation**: Comprehensive guides for all features