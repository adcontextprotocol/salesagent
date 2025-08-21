# AdCP Sales Agent Server - Development Guide

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

## Recent Major Changes

### AdCP v2.4 Protocol Updates
- **Renamed Endpoints**: `list_products` renamed to `get_products` to align with signals agent spec
- **Signal Discovery**: Added optional `get_signals` endpoint for discovering available signals
- **Enhanced Targeting**: Added `signals` field to targeting overlay for direct signal activation
- **Terminology Updates**: Renamed `provided_signals` to `aee_signals` for improved clarity

### AI-Powered Product Management
- **Default Products**: 6 standard products automatically created for new tenants
- **Industry Templates**: Specialized products for news, sports, entertainment, ecommerce
- **AI Configuration**: Uses Gemini 2.5 Flash to analyze descriptions and suggest configs
- **Bulk Operations**: CSV/JSON upload, template browser, quick-create API

### Principal-Level Advertiser Management
- **Architecture Change**: Advertisers are now configured per-principal, not per-tenant
- **Each Principal = One Advertiser**: Clear separation between publisher and advertisers
- **GAM Integration**: Each principal selects their own GAM advertiser ID during creation
- **UI Improvements**: "Principals" renamed to "Advertisers" throughout UI

## Configuration

### Docker Setup (Primary Method)

```yaml
# docker-compose.yml services:
postgres      # PostgreSQL database
adcp-server   # MCP server on port 8080
admin-ui      # Admin interface on port 8001
```

### Required Configuration (.env file)

```bash
# API Keys
GEMINI_API_KEY=your-gemini-api-key-here

# OAuth Configuration
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Admin Configuration
SUPER_ADMIN_EMAILS=user1@example.com,user2@example.com
SUPER_ADMIN_DOMAINS=example.com

# Port Configuration (optional)
ADCP_SALES_PORT=8080
ADMIN_UI_PORT=8001
```

### Database Schema

```sql
-- Multi-tenant tables
tenants (tenant_id, name, subdomain, config, billing_plan)
principals (tenant_id, principal_id, name, access_token, platform_mappings)
products (tenant_id, product_id, name, formats, targeting_template)
media_buys (tenant_id, media_buy_id, principal_id, status, config, budget, dates)
creatives (tenant_id, creative_id, principal_id, status, format)
tasks (tenant_id, task_id, media_buy_id, task_type, status, details)
audit_logs (tenant_id, timestamp, operation, principal_id, success, details)
```

## Common Operations

### Running the Server
```bash
# Start all services with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Managing Tenants
```bash
# Create new publisher/tenant
docker exec -it adcp-buy-server-adcp-server-1 python setup_tenant.py "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code 123456 \
  --gam-refresh-token YOUR_REFRESH_TOKEN

# Access Admin UI
open http://localhost:8001
```

### Running Tests
```bash
# Run all tests
uv run pytest

# Run by category
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/e2e/

# Run with coverage
uv run pytest --cov=. --cov-report=html
```

### Using MCP Client
```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

headers = {"x-adcp-auth": "your_token"}
transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
client = Client(transport=transport)

async with client:
    # Get products
    products = await client.tools.get_products(brief="video ads for sports content")

    # Create media buy
    result = await client.tools.create_media_buy(
        product_ids=["prod_1"],
        total_budget=5000.0,
        flight_start_date="2025-02-01",
        flight_end_date="2025-02-28"
    )
```

## Database Migrations

The project uses Alembic for database migrations:

```bash
# Run migrations
uv run python migrate.py

# Create new migration
uv run alembic revision -m "description"
```

**Important**: Never modify existing migration files after they've been committed.

## Testing Guidelines

### Test Organization
```
tests/
├── unit/           # Fast, isolated unit tests
├── integration/    # Tests requiring database/services
├── e2e/           # End-to-end full system tests
└── ui/            # Admin UI interface tests
```

### Running Tests in CI
Tests marked with `@pytest.mark.requires_server` or `@pytest.mark.skip_ci` are automatically skipped in CI.

### Common Test Patterns
- Use `get_db_session()` context manager for database access
- Import `Principal` from `schemas` (not `models`) for business logic
- Use `SuperadminConfig` in fixtures for admin access
- Set `sess["user"]` as a dictionary with email and role

## Development Best Practices

### Code Style
- Use `uv` for dependency management
- Run pre-commit hooks: `pre-commit run --all-files`
- Follow existing patterns in the codebase
- Use type hints for all function signatures

### Database Patterns
- Always use context managers for database sessions
- Explicit commits required (`session.commit()`)
- Handle JSONB fields properly for PostgreSQL vs SQLite

### UI Development
- Extend base.html for all templates
- Use Bootstrap classes for styling
- Test templates with `pytest tests/integration/test_template_rendering.py`
- Check form field names match backend expectations

## Deployment

### Docker Deployment
```bash
# Build and run
docker-compose build
docker-compose up -d

# Check health
docker-compose ps
docker-compose logs --tail=50
```

### Fly.io Deployment
```bash
# Deploy to Fly.io
fly deploy

# Set secrets
fly secrets set GEMINI_API_KEY="your-key"
fly secrets set GOOGLE_CLIENT_ID="your-client-id"
fly secrets set GOOGLE_CLIENT_SECRET="your-secret"

# View logs
fly logs
```

## Support

For issues or questions:
- Check existing documentation in `/docs`
- Review test examples in `/tests`
- Consult adapter implementations in `/adapters`
