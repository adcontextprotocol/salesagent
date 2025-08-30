# AdCP Sales Agent Server - Development Guide

## 🚨 DEPLOYMENT ARCHITECTURE - CRITICAL TO UNDERSTAND 🚨

This project has **TWO COMPLETELY SEPARATE** deployment environments:

### 1. LOCAL DEVELOPMENT (Docker Compose)
- **Control**: `docker-compose up/down`
- **URLs**: localhost:8001 (Admin), localhost:8080 (MCP), localhost:8091 (A2A)
- **Database**: Local PostgreSQL container on port 5526
- **Config**: `docker-compose.yml`, `.env`
- **Purpose**: Development and testing only

### 2. PRODUCTION (Fly.io)
- **Control**: `fly deploy`, `fly status`, `fly logs`
- **URL**: https://adcp-sales-agent.fly.dev
- **Database**: Fly PostgreSQL cluster (completely separate)
- **Config**: `config/fly/*.toml`
- **Status**: ✅ **CURRENTLY DEPLOYED AND RUNNING**
- **App Name**: `adcp-sales-agent`

**⚠️ IMPORTANT**: Docker and Fly.io are INDEPENDENT. Starting/stopping Docker does NOT affect production on Fly.io!

## Project Overview

This is a Python-based reference implementation of the Advertising Context Protocol (AdCP) V2.3 sales agent. It demonstrates how publishers expose advertising inventory to AI-driven clients through a standardized MCP (Model Context Protocol) interface.

The server provides:
- **MCP Server**: FastMCP-based server exposing tools for AI agents (port 8080)
- **Admin UI**: Secure web interface with Google OAuth authentication (port 8001)
- **A2A Server**: Standard python-a2a server for agent-to-agent communication (port 8091)
- **Multi-Tenant Architecture**: Database-backed tenant isolation with subdomain routing
- **Advanced Targeting**: Comprehensive targeting system with overlay and managed-only dimensions
- **Creative Management**: Auto-approval workflows, creative groups, and admin review
- **Human-in-the-Loop**: Optional manual approval mode for sensitive operations
- **Security & Compliance**: Audit logging, principal-based auth, adapter security boundaries
- **Slack Integration**: Per-tenant webhook configuration (no env vars needed)
- **Production Ready**: PostgreSQL database, Docker deployment, health monitoring

## Key Architecture Decisions

### 0. Admin UI Route Architecture (IMPORTANT FOR DEBUGGING)
**⚠️ CRITICAL**: The admin interface has confusing route handling that can waste debugging time:

- **`src/admin/blueprints/settings.py`**: Handles SUPER ADMIN settings and POST operations for tenant settings
  - Functions: `admin_settings()` (GET) and `update_admin_settings()` (POST) for superadmin settings
  - Also contains POST-only routes for updating tenant settings (`update_adapter()`, `update_general()`, etc.)
- **`src/admin/blueprints/tenants.py`**: Handles TENANT-SPECIFIC settings GET requests
  - Function: `tenant_settings()` - Renders the main tenant settings page

**Route Architecture**:
- **GET** `/admin/tenant/{id}/settings` → `tenants.py::tenant_settings()` (displays the page)
- **POST** `/admin/tenant/{id}/settings/adapter` → `settings.py::update_adapter()` (updates data, redirects back)

**Route Mapping**:
```
/admin/settings                           → src/admin/blueprints/settings.py::admin_settings()
/admin/tenant/{id}/settings               → src/admin/blueprints/tenants.py::tenant_settings()
/admin/tenant/{id}/settings/adapter       → src/admin/blueprints/settings.py::update_adapter()
/admin/tenant/{id}/settings/general       → src/admin/blueprints/settings.py::update_general()
/admin/tenant/{id}/settings/slack         → src/admin/blueprints/settings.py::update_slack()
```

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

### 4. A2A Protocol Support
- Standard `python-a2a` library implementation
- No custom protocol code - using library's base classes only
- Supports both REST and JSON-RPC transports
- Compatible with `a2a` CLI and other standard A2A clients
- Intelligent response handling for product queries

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

### `src/a2a/adcp_a2a_server.py` - A2A Server
- Standard `python-a2a` server implementation
- Extends `A2AServer` base class from python-a2a library
- Handles product, targeting, and pricing queries
- Integrates with MCP server for real data when available
- Uses Waitress WSGI server for production reliability
- **Authentication**: Supports Bearer tokens via Authorization headers
- **Security**: Query parameter auth deprecated in favor of headers

## Recent Major Changes

### Real-Time Dashboard & Task Management System (Latest)
- **Activity Stream**: Live dashboard with Server-Sent Events (SSE) for real-time updates
- **Task Management UI**: Complete task management system with listing, detail, and approval pages
- **Database Schema**: Added `tasks` table with full column set matching SQLAlchemy models
- **Templates**: Created `tasks.html`, `task_detail.html`, and enhanced `tenant_dashboard.html`
- **Blueprints**: Added `activity_stream.py` and `tasks.py` for handling task operations
- **Bug Fixes**: Fixed missing table columns, removed invalid model references, corrected import paths

### A2A Protocol Integration with python-a2a
- **Standard Library**: Now using `python-a2a` library for all A2A protocol handling
- **No Custom Protocol Code**: Removed all custom protocol implementations
- **Server Implementation**: Using `python_a2a.server.A2AServer` base class
- **Authentication**: Bearer token auth via Authorization headers (secure approach)
- **Client Script**: `scripts/a2a_query.py` provides authenticated CLI access
- **Intelligent Responses**: Server responds to product, targeting, and pricing queries
- **Production Deployment**: Live at https://adcp-sales-agent.fly.dev/a2a

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

# Run E2E tests with Docker services
docker-compose -f docker-compose.test.yml up -d
uv run pytest tests/e2e/ -v
docker-compose -f docker-compose.test.yml down
```

### End-to-End Testing with Strategy System

The E2E test suite provides comprehensive testing of AdCP protocol operations:

**Test Files:**
- `test_adcp_full_lifecycle.py` - Complete campaign lifecycle testing with all AdCP tools
- `test_strategy_simulation_end_to_end.py` - Strategy-based simulation testing
- `test_testing_hooks.py` - Protocol testing hooks (X-Dry-Run, X-Mock-Time, etc.)

**Key Features:**
- Strategy-based testing with deterministic time progression
- Testing hooks from AdCP spec (PR #34) for controlled testing
- Both MCP and A2A protocol testing with official clients
- Parallel test execution with isolated test sessions

**Testing Hooks:**
- `X-Dry-Run`: Validate operations without executing
- `X-Mock-Time`: Control time for deterministic testing
- `X-Jump-To-Event`: Jump to specific campaign events
- `X-Test-Session-ID`: Isolate parallel test sessions

**Running Specific Tests:**
```bash
# Run full lifecycle test
uv run pytest tests/e2e/test_adcp_full_lifecycle.py -v

# Run strategy simulation
uv run pytest tests/e2e/test_strategy_simulation_end_to_end.py -v

# Run with specific markers
uv run pytest -m "not requires_server" tests/e2e/
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

### LOCAL Docker Deployment (Development Only)
```bash
# Start local development environment
docker-compose up -d

# Check health
docker-compose ps
docker-compose logs --tail=50

# Stop local environment
docker-compose down

# NOTE: This is LOCAL ONLY - does not affect Fly.io production!
```

### PRODUCTION Fly.io Deployment
```bash
# Check current production status
fly status --app adcp-sales-agent

# Deploy changes to production
fly deploy --app adcp-sales-agent

# View production logs
fly logs --app adcp-sales-agent

# SSH into production (BE CAREFUL!)
fly ssh console --app adcp-sales-agent

# Set/update secrets in production
fly secrets set GEMINI_API_KEY="your-key" --app adcp-sales-agent

# IMPORTANT: Production database is separate from local!
# Production URL: https://adcp-sales-agent.fly.dev
```

### Deployment Checklist Before Going to Production
1. ✅ Test changes locally with `docker-compose up`
2. ✅ Run tests: `uv run pytest`
3. ✅ Check migrations work: `uv run python migrate.py`
4. ✅ Verify no hardcoded secrets or debug code
5. ✅ Deploy: `fly deploy --app adcp-sales-agent`
6. ✅ Monitor logs: `fly logs --app adcp-sales-agent`
7. ✅ Verify health: `fly status --app adcp-sales-agent`

## Troubleshooting

### Common Issues and Solutions

#### "Error loading dashboard"
- **Cause**: Missing `tasks` table or columns
- **Solution**: Create the table with all required columns:
```sql
-- Run in PostgreSQL
CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR(100) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    media_buy_id VARCHAR(100),
    task_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    assigned_to VARCHAR(255),
    due_date TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    completed_by VARCHAR(255),
    task_metadata JSONB,
    details JSONB,
    strategy_id VARCHAR(255),
    resolution VARCHAR(50),
    resolution_notes TEXT,
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE,
    context_id VARCHAR(100)
);
```

#### "Task not found" or "Error loading tasks"
- **Cause**: Missing template files
- **Solution**: Ensure `templates/tasks.html` and `templates/task_detail.html` exist

#### Port conflicts
- **Solution**: Update `.env` file:
```bash
ADMIN_UI_PORT=8001  # Change from 8052 or other conflicting port
```

## Support

For issues or questions:
- Check existing documentation in `/docs`
- Review test examples in `/tests`
- Consult adapter implementations in `/adapters`
