# AdCP Sales Agent Server - Claude Agent Notes

## Documentation Guidelines

### IMPORTANT: Keep Documentation Simple

The documentation has been consolidated into 9 organized files in the `docs/` directory:

1. **index.md** - Documentation index and navigation hub
2. **SETUP.md** - Installation and initial configuration
3. **DEVELOPMENT.md** - Local development, Conductor, code standards
4. **api.md** - Complete MCP and REST API reference
5. **testing.md** - Comprehensive testing guide
6. **deployment.md** - Docker, Fly.io, and production deployment
7. **OPERATIONS.md** - Admin UI, tenant management, monitoring
8. **ARCHITECTURE.md** - System design, database schema, technical details
9. **TROUBLESHOOTING.md** - Common issues and solutions

**Documentation Rules:**
- **DO NOT** create new documentation files unless absolutely necessary
- **DO** update existing documentation files when adding features
- **DO** keep documentation concise and practical
- **DO NOT** duplicate information across files
- **DO** use the appropriate file based on the topic:
  - Installation/config → SETUP.md
  - Local development → DEVELOPMENT.md
  - API documentation → api.md
  - Testing → testing.md
  - Production deployment → deployment.md
  - Admin/operations → OPERATIONS.md
  - Design decisions → ARCHITECTURE.md
  - Error fixes → TROUBLESHOOTING.md

When documenting:
1. Find the most relevant existing file
2. Add to the appropriate section
3. Keep examples practical and tested
4. Remove outdated information
5. Avoid creating new files

## Git Commit Guidelines

### IMPORTANT: Pre-commit Hooks

**DO NOT use `--no-verify` when committing or pushing code.** The pre-commit hooks are there to catch issues early:

- **Always fix pre-commit failures** rather than bypassing them
- **If tests fail**, fix the tests before committing
- **If linting fails**, fix the code style issues
- **If validation fails**, address the validation errors

When committing:
```bash
# CORRECT - Run pre-commit hooks
git commit -m "feat: Your commit message"
git push

# WRONG - Don't bypass checks
git commit --no-verify -m "feat: Your commit message"  # DON'T DO THIS
git push --no-verify  # DON'T DO THIS
```

If pre-commit hooks are failing:
1. Read the error messages carefully
2. Fix the underlying issues
3. Run the hooks locally: `pre-commit run --all-files`
4. Only commit once all checks pass

## Current Project Structure

```
salesagent/
├── README.md              # Main project readme (concise quick start)
├── CLAUDE.md             # This file - AI assistant instructions
├── docs/                 # All documentation
│   ├── index.md         # Documentation navigation
│   ├── SETUP.md         # Installation guide
│   ├── DEVELOPMENT.md   # Developer guide
│   ├── api.md           # API reference
│   ├── testing.md       # Testing guide
│   ├── deployment.md    # Deployment guide
│   ├── OPERATIONS.md    # Operations guide
│   ├── ARCHITECTURE.md  # System design
│   └── TROUBLESHOOTING.md # Common issues
├── adapters/            # Ad server integrations
├── alembic/            # Database migrations
├── data/               # Data files and examples
│   ├── foundational_creative_formats.json
│   └── examples/
├── scripts/            # Utility scripts
├── templates/          # UI templates
├── tests/              # Test suite
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── ui/
├── tools/              # Demo and simulation tools
│   ├── demos/
│   └── simulations/
├── main.py             # MCP server
├── admin_ui.py         # Admin interface
├── models.py           # Database models
└── schemas.py          # API schemas
```

**Note**: The root directory currently has ~68 Python files that should eventually be reorganized into a `src/` structure, but this requires careful planning to update all imports.

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

## Conductor Workspace Guidelines

### IMPORTANT: Understanding Conductor Workspaces

Conductor workspaces use **git worktrees**, which means:
- Each workspace is a checkout of the main repository at a different branch
- Changes made in a workspace affect the main repository when merged
- **DO NOT DELETE** core files like Alembic migrations, entrypoint.sh, etc.
- The workspace is NOT a separate copy - it's the actual repository

### Working in Conductor Workspaces

When working in a Conductor workspace (e.g., `.conductor/quito/`):

1. **Configuration Changes Only**:
   - Modify `.env` files for environment-specific settings
   - Create `docker-compose.override.yml` for development features
   - NEVER modify core application files unless that's the intended change

2. **Environment Variables**:
   - All configuration should use environment variables
   - The `.env` file is generated by `setup_conductor_workspace.sh`
   - OAuth credentials come from environment variables, not mounted files

3. **Development Features**:
   - Hot reloading is enabled via `docker-compose.override.yml`
   - Volume mounts preserve the container's `.venv` directory
   - Flask debug mode is enabled for the admin UI

4. **Testing Changes**:
   - Always verify migrations run correctly
   - Test with `docker compose up` in the workspace
   - Ensure no version-controlled files are modified unintentionally

## Recent Major Changes

### AdCP v2.4 Protocol Updates (Latest)
- **Renamed Endpoints**: `list_products` renamed to `get_products` to align with signals agent spec
- **Signal Discovery**: Added optional `get_signals` endpoint for discovering available signals (audiences, contextual, geographic, etc.)
- **Enhanced Targeting**: Added `signals` field to targeting overlay for direct signal activation
- **Terminology Updates**: Renamed `provided_signals` to `aee_signals` for improved clarity
- **Unified Signal Interface**: Signals can now include audiences, contextual data, and geographic information

### AI-Powered Product Management
- **Default Products**: 6 standard products automatically created for new tenants
- **Industry Templates**: Specialized products for news, sports, entertainment, ecommerce
- **AI Configuration**: Uses Gemini 2.5 Flash to analyze descriptions and suggest configs
- **Bulk Operations**: CSV/JSON upload, template browser, quick-create API
- **Product Suggestions API**: REST endpoints for programmatic product discovery
- **Smart Matching**: AI analyzes ad server inventory to recommend optimal placements

### Principal-Level Advertiser Management (Latest)
- **Architecture Change**: Advertisers are now configured per-principal, not per-tenant
- **Each Principal = One Advertiser**: Clear separation between publisher (tenant owner) and advertisers (principals)
- **GAM Integration**: Each principal selects their own GAM advertiser ID during creation
- **No Admin Principals**: Publishers don't need principals - they own the tenant
- **UI Improvements**:
  - "Principals" renamed to "Advertisers" throughout UI
  - "Create Principal" → "Add Advertiser"
  - Clear messaging that principals represent advertisers buying inventory
- **API Tokens**: Each advertiser gets their own token for MCP API access
- **Migration**: Existing tenants have company_id migrated to all principals automatically

### Test Authentication Mode (UI Testing)
- **Purpose**: Bypass OAuth for automated UI testing in CI/CD pipelines
- **Activation**: Set `ADCP_AUTH_TEST_MODE=true` environment variable
- **Test Users**: Pre-configured users for super admin, tenant admin, and tenant user roles
- **Security**: Disabled by default, returns 404 when not enabled, visual warnings throughout UI
- **Customizable Credentials**: Test user emails and passwords configurable via environment variables (TEST_*_EMAIL, TEST_*_PASSWORD)
- **Login Methods**: Test form on login pages, dedicated `/test/login` page, POST to `/test/auth`
- **Docker Setup**: Use `docker-compose.override.yml` (never modify main docker-compose.yml)
- **Documentation**: See `docs/test-authentication-mode.md` for complete guide
- **Test Suite**: `tests/ui/test_auth_mode.py` - Complete pytest suite for UI testing
- **IMPORTANT**: Never enable in production! Clear warning banners shown when active

### Database Migrations Support
- **Alembic Integration**: Added Alembic for database schema version control
- **Automatic Migrations**: Migrations run automatically on server startup
- **Multi-Database Support**: Works with both SQLite and PostgreSQL
- **Migration Commands**: `uv run python migrate.py` for running migrations
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

## Dependency Management

This project uses **`uv`** for Python dependency management. `uv` is a fast Python package installer and resolver written in Rust.

### Installing Dependencies
```bash
# Install all dependencies (creates .venv automatically)
uv sync

# Add a new dependency
uv add package-name

# Add a development dependency
uv add --dev pytest-asyncio

# Run commands in the virtual environment
uv run python script.py
uv run pytest
```

### Key Dependencies
- **pyproject.toml**: Contains all project dependencies
- **uv.lock**: Lock file ensuring reproducible builds
- Python 3.12+ is required

## Testing Strategy

### Test Organization

Tests are organized in a clear directory structure:

```
tests/
├── unit/           # Fast, isolated unit tests
├── integration/    # Tests requiring database/services
├── e2e/           # End-to-end full system tests
├── ui/            # Admin UI interface tests
├── fixtures/      # Test data and fixtures
└── utils/         # Test utilities
```

### 1. Unit Tests (`tests/unit/`)
- **Purpose**: Test individual components in isolation
- **Runtime**: < 1 second per test
- **Key tests**:
  - `test_targeting.py`: Targeting system validation
  - `test_creative_parsing.py`: Creative format parsing
  - `test_auth.py`: Authentication logic
  - `test_admin_api.py`: Admin API endpoints
  - `adapters/test_base.py`: Adapter interface compliance

### 2. Integration Tests (`tests/integration/`)
- **Purpose**: Test component interactions with database
- **Runtime**: < 5 seconds per test
- **Key tests**:
  - `test_main.py`: MCP server functionality
  - `test_creative_approval.py`: Creative approval workflows
  - `test_human_tasks.py`: Human-in-the-loop tasks
  - `test_ai_products.py`: AI product features
  - `test_policy.py`: Policy compliance checks
  - `test_gam_country_adunit.py`: GAM country and ad unit reporting functionality
  - `test_gam_reporting.py`: GAM reporting service and API endpoints

### 3. End-to-End Tests (`tests/e2e/`)
- **Purpose**: Test complete user workflows
- **Runtime**: < 30 seconds per test
- **Key tests**:
  - `test_gam_integration.py`: Real GAM adapter integration
  - Full campaign lifecycle testing

### 4. UI Tests (`tests/ui/`)
- **Purpose**: Test web interface functionality
- **Key tests**:
  - `test_auth_mode.py`: Test authentication mode
  - `test_gam_viewer.py`: GAM line item viewer
  - `test_parsing_ui.py`: Creative parsing UI

### Running Tests

#### With uv (Recommended)
```bash
# Run all tests
uv run pytest

# Run by category
uv run pytest tests/unit/              # Unit tests only
uv run pytest tests/integration/       # Integration tests
uv run pytest tests/e2e/               # End-to-end tests

# Run with markers
uv run pytest -m unit                  # Fast unit tests
uv run pytest -m "not slow"            # Skip slow tests
uv run pytest -m ai                    # AI-related tests

# Run with coverage
uv run pytest --cov=. --cov-report=html

# Use the test runner script
uv run python scripts/run_tests.py unit       # Unit tests only
uv run python scripts/run_tests.py integration # Integration tests
uv run python scripts/run_tests.py all        # All tests
uv run python scripts/run_tests.py --list     # List categories
uv run python scripts/run_tests.py --coverage # With coverage
```

#### In Docker Container
```bash
# Run tests inside the container
docker exec -it adcp-buy-server-adcp-server-1 pytest tests/unit/

# Run specific test
docker exec -it adcp-buy-server-adcp-server-1 pytest tests/integration/test_main.py -v

# Run with test runner
docker exec -it adcp-buy-server-adcp-server-1 python scripts/run_tests.py all
```

#### CI/CD Pipeline
Tests run automatically on push/PR via GitHub Actions:
- Unit tests with mocked dependencies
- Integration tests with PostgreSQL
- Coverage reporting to track test completeness
- AI tests with mocked Gemini API
- See `.github/workflows/test.yml` for details

### Writing New Tests

#### Guidelines for Adding Tests

1. **Choose the Right Category**:
   - `tests/unit/` - For testing individual functions/classes in isolation (no DB/server required)
   - `tests/integration/` - For testing component interactions (may require DB)
   - `tests/e2e/` - For testing complete workflows
   - `tests/ui/` - For testing web interface functionality

2. **Use Appropriate Markers**:
   ```python
   @pytest.mark.requires_db    # Test needs database with tables
   @pytest.mark.requires_server # Test needs running MCP server
   @pytest.mark.slow           # Test takes >5 seconds
   @pytest.mark.ai             # Test involves AI features
   ```

3. **Leverage Fixtures**:
   ```python
   from tests.fixtures import TenantFactory, PrincipalFactory, ProductFactory

   def test_my_feature():
       tenant = TenantFactory.create()
       principal = PrincipalFactory.create(tenant_id=tenant["tenant_id"])
   ```

4. **Mock External Dependencies**:
   ```python
   from unittest.mock import patch, MagicMock

   @patch('module.external_service')
   def test_with_mock(mock_service):
       mock_service.return_value = {"result": "success"}
   ```

5. **Database Testing**:
   - Unit tests: Mock database connections
   - Integration tests: Use test database (automatic cleanup)
   - Never test against production database

6. **Naming Conventions**:
   - Test files: `test_feature_name.py`
   - Test classes: `TestFeatureName`
   - Test methods: `test_specific_behavior`

7. **Running Your New Tests**:
   ```bash
   # Run specific test file
   uv run pytest tests/unit/test_my_feature.py -v

   # Run with debugging output
   uv run pytest tests/unit/test_my_feature.py -v -s

   # Run only tests matching pattern
   uv run pytest -k "test_my_feature"
   ```

### UI Testing with Test Mode

When testing the Admin UI without dealing with OAuth:

#### Quick Start
```bash
# Enable test mode in docker-compose.override.yml
cp docker-compose.override.example.yml docker-compose.override.yml
# Edit the file and uncomment ADCP_AUTH_TEST_MODE=true

# Start services
docker-compose up

# Run UI tests
ADCP_AUTH_TEST_MODE=true uv run pytest tests/ui/test_auth_mode.py -v
```

#### Available Test Users
- `test_super_admin@example.com` / `test123` - Full admin access
- `test_tenant_admin@example.com` / `test123` - Tenant admin (requires tenant_id)
- `test_tenant_user@example.com` / `test123` - Tenant user (requires tenant_id)

#### Test Login Options
1. **Web UI**: Visit `/test/login` for dedicated test login page
2. **Programmatic**: POST to `/test/auth` with credentials
3. **Regular Login**: Test form appears on normal login pages when enabled

#### Important Notes
- **NEVER** enable `ADCP_AUTH_TEST_MODE` in production
- Visual warnings appear throughout UI when test mode is active
- Test endpoints return 404 when test mode is disabled
- Use `docker-compose.override.yml`, never modify main `docker-compose.yml`

## Configuration

### Docker Setup (Primary Method)

The system runs with Docker Compose, which manages all services:

```yaml
# docker-compose.yml services:
postgres      # PostgreSQL database
adcp-server   # MCP server on port 8080
admin-ui      # Admin interface on port 8001
```

**Docker Caching**: The system automatically uses Docker BuildKit caching to speed up builds. Shared volumes (`adcp_global_pip_cache` and `adcp_global_uv_cache`) cache dependencies across all Conductor workspaces, reducing build times from ~2-3 minutes to ~30 seconds.

### Required Configuration (.env file)

```bash
# API Keys
GEMINI_API_KEY=your-gemini-api-key-here

# OAuth Configuration (choose one method)
# Method 1: Environment variables (recommended)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Method 2: File path (legacy)
# GOOGLE_OAUTH_CREDENTIALS_FILE=/path/to/client_secret.json

# Admin Configuration
SUPER_ADMIN_EMAILS=user1@example.com,user2@example.com
SUPER_ADMIN_DOMAINS=example.com

# Port Configuration (for Conductor workspaces)
POSTGRES_PORT=5432          # Default: 5432
ADCP_SALES_PORT=8080       # Default: 8080
ADMIN_UI_PORT=8001         # Default: 8001

# Database Configuration
DATABASE_URL=postgresql://adcp_user:secure_password_change_me@localhost:5432/adcp
```

### Important Configuration Notes

1. **OAuth Setup**:
   - Prefer environment variables (`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`)
   - File mounting is legacy - avoid hardcoding paths in docker-compose.yml
   - Admin UI will check environment variables first, then look for client_secret*.json files

2. **Slack Webhooks**: Configure per-tenant in Admin UI, NOT via environment variables

3. **Database**: Docker Compose manages PostgreSQL automatically

4. **Conductor Workspaces**: Each workspace gets unique ports via `.env` file

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

## Fly.io Deployment

### Overview

The AdCP Sales Agent can be deployed to Fly.io with a single-machine architecture that runs all services (MCP server, Admin UI, and proxy) on one VM. This deployment uses:

- **Proxy Architecture**: A lightweight aiohttp proxy (port 8000) routes requests to internal services
- **MCP Server**: FastMCP server running on internal port 8080
- **Admin UI**: Flask application running on internal port 8001
- **PostgreSQL**: Managed PostgreSQL cluster on Fly.io
- **Persistent Volume**: 1GB volume mounted at `/data` for file storage

### Architecture Diagram

```
Internet
    ↓
Fly.io Edge (ports 80/443)
    ↓
Proxy (port 8000)
    ├── /mcp/* → MCP Server (8080)
    ├── /admin, /auth, /api, /static → Admin UI (8001)
    └── / → redirect to /admin
```

### Prerequisites

1. **Fly.io CLI**: Install from https://fly.io/docs/flyctl/install/
2. **Fly.io Account**: Sign up at https://fly.io
3. **Google OAuth Credentials**: For Admin UI authentication
4. **Gemini API Key**: For AI features

### Initial Setup

1. **Clone and navigate to the repository**:
   ```bash
   git clone https://github.com/adcontextprotocol/salesagent.git
   cd salesagent
   ```

2. **Login to Fly.io**:
   ```bash
   fly auth login
   ```

3. **Create the app**:
   ```bash
   fly apps create adcp-sales-agent
   ```

4. **Create PostgreSQL cluster**:
   ```bash
   fly postgres create --name adcp-db --region iad --initial-cluster-size 1 --vm-size shared-cpu-1x --volume-size 10
   fly postgres attach adcp-db --app adcp-sales-agent
   ```

5. **Create persistent volume**:
   ```bash
   fly volumes create adcp_data --region iad --size 1
   ```

6. **Set required secrets**:
   ```bash
   # OAuth configuration
   fly secrets set GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
   fly secrets set GOOGLE_CLIENT_SECRET="your-client-secret"

   # Admin configuration
   fly secrets set SUPER_ADMIN_EMAILS="admin1@example.com,admin2@example.com"
   fly secrets set SUPER_ADMIN_DOMAINS="example.com"

   # API keys
   fly secrets set GEMINI_API_KEY="your-gemini-api-key"
   ```

7. **Configure OAuth redirect URI**:

   In your Google Cloud Console, add this redirect URI:
   ```
   https://adcp-sales-agent.fly.dev/auth/google/callback
   ```

   This single URI handles both super admin and tenant-specific authentication.

8. **Deploy the application**:
   ```bash
   fly deploy
   ```

### How It Works

#### Single OAuth Redirect URI

The system uses a consolidated OAuth callback that handles multiple authentication flows:

1. **Super Admin Login** (`/login`):
   - Initiates OAuth flow
   - Callback checks if email is in `SUPER_ADMIN_EMAILS` or domain in `SUPER_ADMIN_DOMAINS`
   - Grants full system access

2. **Tenant Login** (`/tenant/<tenant_id>/login`):
   - Stores `tenant_id` in session before OAuth
   - Callback retrieves `tenant_id` from session
   - Checks user authorization for specific tenant
   - Grants tenant-specific access

#### Proxy Configuration

The `fly-proxy.py` handles:
- **Request Routing**: Routes based on path prefixes
- **SSE Support**: Streams Server-Sent Events for MCP protocol
- **Header Forwarding**: Adds X-Forwarded-* headers for proper URL generation
- **Path Rewriting**: Strips `/admin` prefix when routing to Admin UI

#### Service Management

The deployment uses `debug_start.sh` which:
1. Runs database migrations
2. Starts MCP server and Admin UI as background processes
3. Waits for services to be healthy
4. Starts the proxy as the main process

### Accessing the Deployment

- **Admin UI**: https://adcp-sales-agent.fly.dev/admin
- **MCP Endpoint**: https://adcp-sales-agent.fly.dev/mcp/
- **Health Check**: https://adcp-sales-agent.fly.dev/health

### Using with MCP Inspector

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Connect to your deployed server
npx inspector https://adcp-sales-agent.fly.dev/mcp/
```

You'll need to add the `x-adcp-auth` header with a valid token.

### Monitoring and Logs

```bash
# View real-time logs
fly logs

# Check app status
fly status

# SSH into the machine
fly ssh console

# View specific service logs inside machine
fly ssh console -C "tail -f /tmp/mcp_server.log"
fly ssh console -C "tail -f /tmp/admin_ui.log"
```

### Updating the Deployment

```bash
# Make your changes
git add -A
git commit -m "Your changes"

# Deploy updates
fly deploy

# If you need to update secrets
fly secrets set KEY="new-value"
```

### Scaling Considerations

The current setup runs all services on a single machine. For production scaling:

1. **Horizontal Scaling**: Use `Dockerfile.fly.processgroups` for multi-machine setup
2. **Database Scaling**: Upgrade PostgreSQL cluster size
3. **Volume Scaling**: Increase volume size as needed
4. **Region Scaling**: Add more regions for global availability

### Troubleshooting

1. **502 Errors**: Check if all services started correctly:
   ```bash
   fly ssh console -C "ps aux | grep python"
   ```

2. **OAuth Issues**: Ensure redirect URI is exactly:
   ```
   https://adcp-sales-agent.fly.dev/auth/google/callback
   ```

3. **Database Connection**: Verify DATABASE_URL is set:
   ```bash
   fly ssh console -C "env | grep DATABASE_URL"
   ```

4. **Service Health**: Check individual service health:
   ```bash
   fly ssh console -C "curl http://localhost:8080/health"
   fly ssh console -C "curl http://localhost:8001/health"
   ```

## Database Migration Best Practices

### CRITICAL: Never Modify Existing Migration Files

**⚠️ ABSOLUTE RULE: NEVER modify a migration file that has been committed and may have run in production!**

Once a migration file is created and committed, it becomes immutable. Modifying it can cause:
- Database inconsistencies between environments
- Failed deployments
- Data corruption
- Inability to roll back changes

#### ✅ CORRECT: Create New Migrations
```python
# If migration 014 has an issue, create 015 to fix it
# alembic/versions/015_fix_migration_issue.py
def upgrade():
    # Fix the issue here
    if not column_exists('table', 'column'):
        op.add_column('table', sa.Column('column', sa.String(100)))
```

#### ❌ WRONG: Modify Existing Migration
```python
# NEVER DO THIS to alembic/versions/014_original.py after it's committed!
def upgrade():
    # Adding "if exists" checks after the fact
    if not table_exists('my_table'):  # DON'T ADD THIS LATER!
        op.create_table('my_table', ...)
```

#### Migration Rules:
1. **Test locally first**: Run migrations on a test database before committing
2. **One-way only**: Migrations should work going forward, not be edited retroactively
3. **Create fix migrations**: If a migration fails, create a NEW migration to fix it
4. **Check production state**: Always verify what migrations have run in production
5. **Use safe operations**: In fix migrations, use conditional checks (see 015_handle_partial_schemas.py)

#### Checking Migration Status:
```bash
# See which migrations have run
sqlite3 adcp_local.db "SELECT * FROM alembic_version;"

# PostgreSQL
psql $DATABASE_URL -c "SELECT * FROM alembic_version;"
```

## CRITICAL: Database Field Name Changes

### MediaBuy Model Field Names (MUST READ)
The MediaBuy model underwent significant field renames. **Always use the correct field names:**

| OLD (WRONG) | NEW (CORRECT) | Used In |
|-------------|---------------|---------|
| `flight_start_date` | `start_date` | MediaBuy model |
| `flight_end_date` | `end_date` | MediaBuy model |
| `total_budget` | `budget` | MediaBuy model |

**Impact**: These field names are used throughout:
- Templates (tenant_dashboard.html, operations.html)
- API schemas (schemas.py)
- Database queries
- Tests
- Admin UI routes

**To check for issues**: Run `uv run pytest tests/integration/test_schema_field_validation.py`

## Database Access Patterns

### IMPORTANT: Standardized Database Access

The codebase is transitioning to standardized database patterns. **Always use context managers**:

#### ✅ CORRECT Pattern (Use This)
```python
from database_session import get_db_session
from models import Tenant

# For ORM operations (PREFERRED)
with get_db_session() as session:
    tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
    if tenant:
        tenant.name = "New Name"
        session.commit()  # Explicit commit required
```

#### ❌ WRONG Pattern (Avoid)
```python
# DO NOT USE - Prone to connection leaks
conn = get_db_connection()
cursor = conn.execute(...)
conn.close()  # May not be called on error
```

**Key Rules**:
1. Always use `with get_db_session()` for new code
2. Explicit commits required (`session.commit()`)
3. Context manager handles cleanup automatically
4. See `docs/database-patterns.md` for complete guide

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

**Note on Database Initialization**: The `entrypoint.sh` script runs `init_db()` which is **safe and non-destructive**:
- All tables use `CREATE TABLE IF NOT EXISTS` - existing tables are never dropped
- Default data is only created if tables are empty (checks tenant count first)
- No existing data is ever modified or deleted
- The function is idempotent and can be run multiple times safely

### Running Standalone (Development Only)
```bash
# Install dependencies with uv
uv sync

# Run database migrations
uv run python migrate.py

# Initialize default data (if needed)
uv run python init_database.py

# Start MCP server and Admin UI
uv run python run_server.py
```

### Managing Tenants (Publishers)
```bash
# Create new publisher/tenant (inside Docker container)
docker exec -it adcp-buy-server-adcp-server-1 python setup_tenant.py "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code 123456 \
  --gam-refresh-token YOUR_REFRESH_TOKEN
# Note: No --gam-company-id needed anymore - advertisers are configured per-principal

# Create publisher with mock adapter for testing
docker exec -it adcp-buy-server-adcp-server-1 python setup_tenant.py "Publisher Name" \
  --adapter mock

# Access Admin UI
open http://localhost:8001

# After creating tenant:
# 1. Login to Admin UI with Google OAuth
# 2. Go to "Advertisers" tab (formerly "Principals")
# 3. Click "Add Advertiser" to create advertisers who will buy inventory
# 4. Each advertiser selects their own GAM advertiser ID
# 5. Share API tokens with advertisers for MCP API access
```

### Running Simulations
```bash
# Full lifecycle with temporary test database
uv run python run_simulation.py

# Dry-run with GAM adapter
uv run python run_simulation.py --dry-run --adapter gam

# Use production database (careful!)
uv run python run_simulation.py --use-prod-db

# Run with custom token
uv run python simulation_full.py http://localhost:8080 \
  --token "your_token" \
  --principal "your_principal"

# Demo AI product features
uv run python demo_ai_products.py
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

    # Discover available signals (optional)
    signals = await client.tools.get_signals(
        query="sports",
        type="contextual"
    )

    # Create media buy with signals
    result = await client.tools.create_media_buy(
        product_ids=["prod_1"],
        total_budget=5000.0,
        flight_start_date="2025-02-01",
        flight_end_date="2025-02-28",
        targeting_overlay={
            "geo_country_any_of": ["US"],
            "signals": ["sports_content", "auto_intenders_q1_2025"]
        }
    )
```

### Product Management APIs
```bash
# Get product suggestions
curl -H "Cookie: session=YOUR_SESSION" \
  "http://localhost:8001/api/tenant/TENANT_ID/products/suggestions?industry=news&max_cpm=20"

# Quick create products from templates
curl -X POST -H "Content-Type: application/json" -H "Cookie: session=YOUR_SESSION" \
  -d '{"product_ids": ["run_of_site_display", "homepage_takeover"]}' \
  "http://localhost:8001/api/tenant/TENANT_ID/products/quick-create"

# Bulk upload products (CSV)
curl -X POST -H "Cookie: session=YOUR_SESSION" \
  -F "file=@products.csv" \
  "http://localhost:8001/api/tenant/TENANT_ID/products/bulk/upload"
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
- **`ai_product_service.py`**: AI-driven product configuration (uses Gemini 2.5 Flash)
- **`default_products.py`**: Default product templates for new tenants
- **`test_ai_product_basic.py`**: Core AI product feature tests

## Best Practices for UI Development

### Template Development
1. **Always extend base.html** - Don't create standalone HTML files
2. **Check CSS dependencies** - If using Bootstrap classes, ensure Bootstrap is loaded
3. **Avoid global CSS** - Use scoped classes or inline styles for specific components
4. **Test in isolation** - Create simple versions first (like targeting_browser_simple.html)

### JavaScript Best Practices
1. **Handle null/undefined** - Always use defensive coding: `(value || defaultValue)`
2. **Check element existence** - Before using: `if (element) { ... }`
3. **Add console logging** - Help future debugging with clear log messages
4. **Use try/catch** - Wrap API calls and DOM manipulation
5. **Test data structure** - Log API responses to verify format

### API Development
1. **Return consistent JSON** - Never mix HTML and JSON responses
2. **Add debug logging** - Use `app.logger.info()` to track execution
3. **Check authentication** - Verify session/token before processing
4. **Handle errors gracefully** - Return proper HTTP status codes with error messages
5. **Document response format** - Add comments showing expected JSON structure

### Docker & Deployment
1. **Always rebuild after changes** - `docker-compose build` before testing
2. **Check container health** - `docker ps` to verify running state
3. **Monitor logs** - `docker-compose logs -f` during debugging
4. **Clean restart if needed** - `docker-compose down && docker-compose up -d`
5. **Use volumes for development** - Mount code for hot reloading

## Template Testing Guidelines (CRITICAL)

### Preventing Template Rendering Errors

**Problem**: Template rendering errors (like `BuildError` from `url_for()` calls) are often not caught by standard tests because Flask's test client doesn't propagate template exceptions by default.

**Solution**: We have comprehensive template validation in place to catch these issues before they reach production.

#### 1. Automatic Template Validation

All templates are automatically validated on commit via pre-commit hooks:
- **Hook**: `template-url-validation` in `.pre-commit-config.yaml`
- **Test**: `tests/integration/test_template_url_validation.py`
- **Coverage**: Every `url_for()` call in every template is validated

#### 2. When Creating New Templates

**ALWAYS** ensure:
1. All `url_for()` calls use the correct endpoint names
2. Blueprint routes use namespaced endpoints (e.g., `auth.login` not `login`)
3. Form actions point to valid POST-accepting endpoints
4. AJAX URLs in JavaScript are valid

**Common Mistakes to Avoid**:
- ❌ `url_for('update_settings')` when route is named `settings`
- ❌ `url_for('tenant_dashboard')` when it's `tenants.dashboard`
- ❌ `url_for('creative_formats')` when it's `list_creative_formats`
- ❌ Missing blueprint namespace (e.g., `select_tenant` vs `auth.select_tenant`)

#### 3. When Migrating Routes to Blueprints

**Checklist**:
1. ✅ Update all templates that reference the moved route
2. ✅ Use blueprint namespace in `url_for()` calls
3. ✅ Update both GET and POST form actions
4. ✅ Check JavaScript/AJAX calls too
5. ✅ Run template validation test: `uv run pytest tests/integration/test_template_url_validation.py`

#### 4. Testing Templates Manually

```bash
# Run comprehensive template validation
uv run pytest tests/integration/test_template_url_validation.py -v

# Check specific template rendering
uv run pytest tests/integration/test_template_rendering.py -v

# Run pre-commit hook manually
pre-commit run template-url-validation --all-files
```

#### 5. Adding Tests for New Templates

When adding a new template with critical navigation:
1. Add it to `test_template_rendering.py` if it's a key page
2. Ensure form actions are covered in `test_form_actions_point_to_valid_endpoints`
3. Add navigation links to `test_navigation_links_are_valid`

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
12. ✅ AI product features (templates, bulk upload, suggestions API)
13. ✅ Default product creation for new tenants
14. ✅ UI test mode (when working on Admin UI features):
    - Enable with `ADCP_AUTH_TEST_MODE=true`
    - Verify warning banners appear
    - Test with provided test users
    - Ensure test endpoints return 404 when disabled
15. ✅ **UI rendering** (new!):
    - Check browser console for errors
    - Verify elements have non-zero dimensions
    - Test with browser dev tools open
    - Clear cache between major CSS changes

## Recent Improvements Summary

1. **Corrected Naming**: "AdCP Sales Agent" (not AdCP:Buy)
2. **Protocol Name**: "Advertising Context Protocol" (not Campaign)
3. **MCP Interface**: Proper MCP examples (not REST/curl)
4. **Test Database**: Simulations use isolated test DB by default
5. **Token Alignment**: Fixed simulation tokens to match database
6. **Documentation**: Comprehensive guides for all features

## Database Migration Best Practices

Based on common issues encountered, follow these guidelines when working with database migrations:

### 1. **Migration File Naming**
- Use consistent revision IDs: `001_description`, `002_description`, etc.
- The revision ID in the filename MUST match the `revision` variable inside the file
- Example: `003_add_policy_compliance_fields.py` should have `revision = '003_add_policy_compliance_fields'`

### 2. **Check Existing Schema First**
- Always check `database_schema.py` to see what columns already exist
- The tenant config is stored in a single `config` JSONB/TEXT column - don't add separate columns for config items
- Use `grep -r "column_name" .` to check if a column already exists before adding it

### 3. **Multi-Database Compatibility**
- Use SQLAlchemy's `sa.table()` and `sa.column()` for data operations in migrations
- Avoid raw SQL strings - they may not work across SQLite and PostgreSQL
- Example of correct approach:
  ```python
  tenants_table = sa.table('tenants',
      sa.column('tenant_id', sa.String),
      sa.column('config', sa.Text)
  )
  connection.execute(tenants_table.update().where(...).values(...))
  ```

### 4. **Testing Migrations**
- Always test with a fresh database: `rm adcp_local.db && uv run python init_database.py`
- Check migration status: `sqlite3 adcp_local.db "SELECT * FROM alembic_version;"`
- If migrations fail, check the error carefully - it often indicates duplicate columns

### 5. **Tenant Configuration Pattern**
- Store feature flags and settings in the tenant's `config` JSON field
- Access via: `tenant.get('config', {}).get('policy_settings')`
- Update `setup_tenant.py` to include new config keys for new tenants
- Example structure:
  ```json
  {
    "adapters": {...},
    "features": {...},
    "policy_settings": {
      "enabled": true,
      "custom_rules": {...}
    }
  }
  ```

### 6. **Boolean Fields in SQLite**
- SQLite doesn't have native boolean type - use `server_default='0'` for False
- PostgreSQL handles booleans properly, but keep SQLite compatibility in mind
- Always test with both databases if making schema changes

## Critical Issues to Avoid (MUST READ)

Based on the GAM inventory sync incident (12 cascading errors), here are critical patterns to avoid:

### 1. **Database Schema Changes**
⚠️ **NEVER** remove a column without checking ALL code references:
```bash
# ALWAYS run this before removing any column:
grep -r "column_name" . --include="*.py" | grep -v alembic
```

**Common Mistake**: Removing `tenant.config` column broke 10+ files
**Solution**: Update all code BEFORE running migration

### 2. **Model Import Confusion**
⚠️ **CRITICAL**: Know which model to import:
```python
# WRONG - causes AttributeError
from models import Principal  # SQLAlchemy ORM model (no methods)

# CORRECT - for business logic
from schemas import Principal  # Pydantic model (has get_adapter_id())
```

**Rule**:
- `models.py` = Database ORM models (for queries)
- `schemas.py` = API/business models (for logic)

### 3. **Database Connection Patterns**
⚠️ **ALWAYS** use proper session management:
```python
# WRONG - can cause transaction errors
db_session = SessionLocal()  # Global session

# CORRECT - thread-safe sessions
from sqlalchemy.orm import scoped_session
db_session = scoped_session(SessionLocal)

# In endpoints, ALWAYS clean up:
try:
    db_session.remove()  # Start fresh
    # ... do work ...
    db_session.commit()
except Exception:
    db_session.rollback()
    raise
finally:
    db_session.remove()  # Clean up
```

### 4. **External API Changes**
⚠️ **ALWAYS** check API documentation for deprecations:
```python
# WRONG - deprecated in googleads v24+
statement_builder = client.GetDataDownloader().new_filter_statement()

# CORRECT - current API
from googleads import ad_manager
statement_builder = ad_manager.StatementBuilder(version='v202411')
```

### 5. **PostgreSQL vs SQLite Differences**
⚠️ **ALWAYS** handle database differences:
```python
# WRONG - returns tuple in PostgreSQL
cursor = conn.execute("SELECT * FROM table")
row = cursor.fetchone()
data = row['column']  # AttributeError!

# CORRECT - use DictCursor
from psycopg2.extras import DictCursor
conn = psycopg2.connect(..., cursor_factory=DictCursor)
```

### 6. **Column Length Constraints**
⚠️ **ALWAYS** validate data length before database:
```python
# WRONG - database will reject if too long
inventory_type = "custom_targeting_value"  # 22 chars
Column(String(20))  # Too short!

# CORRECT - check in model
inventory_type = Column(String(30))  # Sufficient length
```

### 7. **SOAP/SUDS Objects**
⚠️ **ALWAYS** convert SOAP objects to dicts:
```python
# WRONG - SUDS objects don't support dict access
ad_unit = gam_response['results'][0]
name = ad_unit['name']  # AttributeError!

# CORRECT - serialize first
from zeep.helpers import serialize_object
ad_unit_dict = serialize_object(ad_unit)
name = ad_unit_dict['name']
```

### 8. **Input Validation & Security**
⚠️ **ALWAYS** validate user input before processing:
```python
# WRONG - Direct use of user input
tenant_id = request.args.get('tenant_id')
cursor.execute(f"SELECT * FROM tenants WHERE id = '{tenant_id}'")  # SQL injection!

# CORRECT - Validate and use parameterized queries
import re
def validate_tenant_id(tid):
    return tid and re.match(r'^[a-zA-Z0-9_-]+$', tid) and len(tid) <= 100

if not validate_tenant_id(tenant_id):
    return jsonify({'error': 'Invalid tenant ID'}), 400
cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
```

**Required Validations**:
- **IDs**: Alphanumeric with `_-` only, max 100 chars
- **Numeric IDs**: Digits only, max 20 chars
- **Timezones**: Must exist in pytz database
- **Date ranges**: Use enum values only

### 9. **Resource Cleanup**
⚠️ **ALWAYS** clean up resources with try/finally:
```python
# WRONG - Temp file may not be deleted on error
tmp_file = tempfile.NamedTemporaryFile(delete=False)
process_file(tmp_file.name)
os.unlink(tmp_file.name)  # Never reached if process_file fails!

# CORRECT - Guaranteed cleanup
tmp_file_path = None
try:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_file_path = tmp.name
    process_file(tmp_file_path)
finally:
    if tmp_file_path and os.path.exists(tmp_file_path):
        try:
            os.unlink(tmp_file_path)
        except Exception as e:
            logger.warning(f"Failed to clean up {tmp_file_path}: {e}")
```

## Pre-Change Checklist for Claude

Before making ANY database or API changes:

1. **Check current schema**:
   ```bash
   # See what exists
   grep -r "Column(" models.py
   sqlite3 adcp_local.db ".schema table_name"
   ```

2. **Search for usage**:
   ```bash
   # Find all references
   grep -r "field_name" . --include="*.py"
   ```

3. **Test with both databases**:
   ```bash
   # SQLite
   DATABASE_URL=sqlite:///test.db python your_script.py

   # PostgreSQL
   docker-compose up -d postgres
   DATABASE_URL=postgresql://... python your_script.py
   ```

4. **Run validation scripts**:
   ```bash
   ./scripts/check_schema_references.py
   ./scripts/validate_column_lengths.py
   ./scripts/check_api_deprecations.py
   ```

5. **Test the full workflow**:
   ```bash
   ./scripts/test_migration.sh --full-workflow
   ```

## UI Debugging Guide (Lessons from Targeting Page Fix)

### Problem: UI Pages Show Loading But No Data

**Symptoms:**
- Page shows "Loading..." indefinitely
- Console shows data is loaded (`targetingData` has values)
- DOM elements exist but aren't visible
- `offsetHeight` and `offsetWidth` return 0

**Root Causes & Solutions:**

1. **Missing CSS/JS Dependencies**
   - **Issue**: Templates use Bootstrap classes but Bootstrap isn't loaded
   - **Fix**: Add Bootstrap CSS/JS to base.html:
   ```html
   <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
   <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
   ```

2. **CSS Conflicts**
   - **Issue**: Global CSS reset breaks framework styles
   - **Bad**: `* { margin: 0; padding: 0; }`
   - **Fix**: Remove global resets, use scoped styles

3. **Container Collapse**
   - **Issue**: Parent containers have 0 dimensions
   - **Debug**: Check all parent elements:
   ```javascript
   let el = document.getElementById('target');
   while (el) {
     console.log(el.tagName, el.offsetWidth, el.offsetHeight);
     el = el.parentElement;
   }
   ```
   - **Fix**: Add explicit dimensions: `min-height`, `min-width`

4. **JavaScript Null Handling**
   - **Issue**: Code doesn't handle null/undefined from API
   - **Bad**: `key.display_name.toLowerCase()`
   - **Good**: `(key.display_name || '').toLowerCase()`

5. **Authentication Issues**
   - **Issue**: API returns HTML login page instead of JSON
   - **Check**: Response headers for `Content-Type`
   - **Fix**: Add `credentials: 'same-origin'` to fetch calls

### Debugging Workflow

1. **Check if containers are running:**
   ```bash
   docker ps | grep abu-dhabi
   # If not running: docker-compose up -d
   ```

2. **Verify data in console:**
   ```javascript
   console.log(targetingData);  // Should have data
   document.getElementById('keys-list').children.length;  // Should be > 0
   ```

3. **Check element visibility:**
   ```javascript
   const el = document.querySelector('.list-group-item');
   console.log('Display:', getComputedStyle(el).display);
   console.log('Height:', el.offsetHeight);
   console.log('Width:', el.offsetWidth);
   ```

4. **Force visibility (temporary fix):**
   ```javascript
   el.style.cssText = 'display: block !important; height: auto !important;';
   ```

## Quick Reference: Common Fixes

| Error | Fix |
|-------|-----|
| `'tuple' object has no attribute 'keys'` | Add `cursor_factory=DictCursor` to PostgreSQL |
| `'Principal' object has no attribute 'get_adapter_id'` | Import from `schemas`, not `models` |
| `current transaction is aborted` | Use `db_session.remove()` before operations |
| `value too long for type character varying` | Increase column length in migration |
| `'DataDownloader' object has no attribute 'new_filter_statement'` | Use `StatementBuilder` instead |
| `AdUnit instance has no attribute 'get'` | Use `serialize_object()` on SUDS objects |
| `'Tenant' object has no attribute 'config'` | Config column was removed - use new columns |
| `Requested revision X overlaps with other requested revisions Y` | Run migrations sequentially or check for circular dependencies |
| **UI shows "Loading..." forever** | Check Bootstrap is loaded, remove CSS conflicts, add dimensions |
| **Elements in DOM but invisible** | Parent has 0 width/height - add min dimensions |
| **JavaScript `TypeError` on null** | Add null checks: `(value || '').method()` |
| **API returns HTML not JSON** | Missing auth - add `credentials: 'same-origin'` |
| **SQL Injection vulnerability** | Use parameterized queries, never string concatenation |
| **Invalid input crashes API** | Add validation functions for all user inputs |
| **Temp files not cleaned up** | Use try/finally blocks for resource cleanup |

### Known Issues

#### Alembic Migration Overlap Error
If you encounter "Requested revision 005_move_config_to_columns overlaps with other requested revisions 004_add_superadmin_config" when running migrations:

**Workaround**: This is a known issue with alembic's dependency resolution in complex migration chains. To resolve:
1. Ensure all migration files have consistent revision ID formats
2. Check that down_revision references are correct in each migration file
3. If the issue persists, consider running migrations sequentially or using `alembic stamp` to manually set the version

**Note**: The migration files themselves are correct - this is an alembic-specific issue with how it resolves the dependency graph.
