# AdCP Sales Agent - Development Guide

Quick reference for AI coding assistants with essential context and gotchas. See `/docs` for detailed documentation.

## External Resources & Services

**AdCP Protocol**
- Spec: https://adcontextprotocol.org/schemas/v1/
- Docs: https://adcontextprotocol.org/docs/
- Current version: 2.2.0 (official), v1 schemas
- Cached schemas: `schemas/v1/` (checked into git)

**Deployment (Reference Implementation)**
- Local: `docker-compose up` → localhost:8001/8080/8091
- Sales Agent (ours): https://adcp-sales-agent.fly.dev (Fly.io, auto-deploys from `main`)
- Test Buyer Agent (ours): https://test-agent.adcontextprotocol.org (Fly.io, for E2E tests)

**Known Test Agent Issues:**
- Auth failures with `create_media_buy` (see `docs/testing/postmortems/2025-10-04-test-agent-auth-bug.md`)
- `get_media_buy_delivery` expects `media_buy_id` (singular) instead of spec-compliant `media_buy_ids` (plural)
- When test agent is down, check: `fly logs --app test-agent`

## Critical Architecture Patterns

### AdCP Schema Compliance
**🚨 SINGLE SOURCE OF TRUTH**: Official AdCP spec at https://adcontextprotocol.org/schemas/v1/

- All Pydantic schemas in `src/core/schemas.py` MUST match official spec exactly
- Validate: `pytest tests/unit/test_adcp_contract.py`
- Never add fields not in spec (common mistake: adding "convenience" fields)
- Never bypass pre-commit hooks with `--no-verify`

### PostgreSQL Only (No SQLite)
**Why**: SQLite hides bugs (different JSONB behavior, no connection pooling, single-threaded)

- All tests require PostgreSQL: `./run_all_tests.sh ci`
- Alembic migrations use PostgreSQL-specific syntax
- Don't add cross-database compatibility code

### Environment-Based Validation
**Why**: Strict validation breaks production when clients use newer schema versions

```bash
ENVIRONMENT=production   # Lenient (extra="ignore") - forward compatible
ENVIRONMENT=development  # Strict (extra="forbid") - catches bugs early
```

### Database Patterns

**JSONType (mandatory):**
- Use `JSONType` for ALL JSON columns (never plain `JSON`)
- Why: Handles PostgreSQL JSONB properly, no manual `json.loads()` needed
- Implementation: `src/core/database/json_type.py`

**SQLAlchemy 2.0:**
```python
# ✅ CORRECT
stmt = select(Model).filter_by(field=value)
instance = session.scalars(stmt).first()

# ❌ WRONG - deprecated
instance = session.query(Model).filter_by(field=value).first()
```

**Integration tests:**
```python
@pytest.mark.requires_db
def test_something(integration_db):  # Use integration_db, not db_session
    with get_db_session() as session:
        # Real PostgreSQL database
```

### MCP/A2A Shared Implementation
**Why**: Avoid code duplication between protocols

All tools use shared `_tool_name_impl()`:
```python
# main.py
def _tool_impl(...) -> Response:
    # Real implementation - ALL business logic here

@mcp.tool()
def tool(...) -> Response:
    return _tool_impl(...)

# tools.py
def tool_raw(...) -> Response:
    from src.core.main import _tool_impl  # Lazy import
    return _tool_impl(...)
```

## Critical Gotchas

### Database Initialization Dependencies
**🚨 Products require CurrencyLimit + PropertyTag to exist first**

```python
# MUST create in this order:
1. Tenant
2. CurrencyLimit (at least USD) - needed for budget validation
3. PropertyTag (at least "all_inventory") - needed for property_tags array
4. Products (can now reference both)
```

**Why**:
- Products validate budgets against currency limits
- AdCP spec requires products have `properties` OR `property_tags` (oneOf)
- Missing these causes "Must have at least one product" errors

**Check in init scripts:**
```python
# Validate CurrencyLimit exists
stmt = select(CurrencyLimit).filter_by(tenant_id=tenant_id, currency_code="USD")
if not session.scalars(stmt).first():
    raise ValueError("Create CurrencyLimit before products")

# Validate PropertyTag exists
stmt = select(PropertyTag).filter_by(tenant_id=tenant_id, tag_id="all_inventory")
if not session.scalars(stmt).first():
    raise ValueError("Create PropertyTag before products")
```

### Admin UI Route Architecture
**Debugging tip**: Routes split between blueprints

- `settings.py`: POST operations for tenant settings
- `tenants.py`: GET requests for tenant settings pages

```
/admin/tenant/{id}/settings         → tenants.py::tenant_settings() (GET)
/admin/tenant/{id}/settings/adapter → settings.py::update_adapter() (POST)
```

### No Quiet Failures
**🚨 ALWAYS fail loudly**

```python
# ❌ WRONG - silent failure
if not self.supports_device_targeting:
    logger.warning("Skipping device targeting...")
    return  # Silently doesn't fulfill contract!

# ✅ CORRECT - explicit failure
if not self.supports_device_targeting and targeting.device_type_any_of:
    raise TargetingNotSupportedException(
        "Device targeting requested but not supported"
    )
```

## Quick Commands

### Testing
```bash
./run_all_tests.sh ci      # Full suite with PostgreSQL (3-5 min, matches CI)
./run_all_tests.sh quick   # Fast, no database (1 min)
pytest tests/unit/test_adcp_contract.py  # AdCP compliance (run before commit)
```

### Development
```bash
docker-compose up -d       # Start all services
docker-compose logs -f     # View logs
uv run python migrate.py   # Run migrations
pre-commit run --all-files # Check code quality
```

### Type Checking
```bash
uv run mypy src/core/your_file.py --config-file=mypy.ini
```

## Key Rules

1. **Schema Compliance**: All client-facing models must match AdCP spec exactly
2. **No Quiet Failures**: Raise exceptions, don't silently skip features
3. **Test Before Commit**: Run unit tests + verify imports for ALL changes
4. **Fix Tests, Don't Skip**: Never use `skip_ci` or `--no-verify` to bypass failures
5. **PostgreSQL Only**: No cross-database compatibility code
6. **Shared Implementation**: MCP and A2A must call same `_impl()` function

## Testing Guidelines

**For ALL changes:**
```bash
uv run pytest tests/unit/ -x
python -c "from src.core.tools import your_function"  # Verify imports
```

**For refactorings (shared implementation, moving code, import changes):**
```bash
uv run pytest tests/integration/ -x  # REQUIRED - catches real bugs
```

**Why unit tests alone aren't enough:**
- Unit tests pass with mocked imports (don't catch missing imports)
- Unit tests don't execute real code paths (don't catch integration bugs)
- Real example: Refactored `get_products_raw`, unit tests passed, integration tests caught missing import

**Pre-commit hooks check:**
- Code formatting (black, isort)
- Max 10 mocks per test file
- AdCP contract tests exist for all client models
- No skipped tests (except marked `skip_ci`)

**Pre-push hook checks:**
- Migration heads only (fast, automatic)
- Tests run in CI, not in hook

## Project Structure

```
src/core/          # MCP server, schemas, database
src/adapters/      # GAM, Kevel, Mock ad server implementations
  └── gam/         # Modular GAM (250-line orchestrator + managers)
src/admin/         # Flask admin UI (Google OAuth secured)
src/a2a_server/    # Agent-to-agent server (python-a2a)
```

## Documentation

**Detailed guides:**
- Architecture: `docs/ARCHITECTURE.md`
- Testing patterns: `docs/testing/`
- Setup: `docs/SETUP.md`
- Deployment: `docs/deployment.md`
- Security: `docs/security.md`

## Adapter Pricing Support

**GAM**: CPM, VCPM, CPC, FLAT_RATE
- Auto line item type selection based on pricing + guarantees
- FLAT_RATE → SPONSORSHIP with CPD translation
- VCPM → STANDARD only (GAM restriction)

**Mock**: All AdCP pricing models (CPM, VCPM, CPCV, CPP, CPC, CPV, FLAT_RATE)

See `docs/ARCHITECTURE.md` for detailed pricing matrices.

## Configuration

**Secrets** (`.env.secrets` - REQUIRED):
```bash
GEMINI_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GAM_OAUTH_CLIENT_ID=...
GAM_OAUTH_CLIENT_SECRET=...
APPROXIMATED_API_KEY=...                           # Custom domains
APPROXIMATED_PROXY_IP=37.16.24.200                 # Proxy cluster IP
APPROXIMATED_BACKEND_URL=adcp-sales-agent.fly.dev  # Backend URL
```

**Database schema:**
```sql
-- Core multi-tenant
tenants, principals, products, media_buys, creatives, audit_logs

-- Workflow system (unified)
workflow_steps, object_workflow_mappings

-- DEPRECATED (don't use)
tasks, human_tasks
```

## Git Workflow

1. Create branch: `git checkout -b feature/name`
2. Make changes, test locally
3. Push and create PR: `gh pr create`
4. Wait for review and merge via GitHub UI
5. **Merging to main auto-deploys to Fly.io production**

**❌ Never push directly to main**

## Common Mistakes to Avoid

1. **Adding non-spec fields to AdCP schemas** - Always verify against official spec first
2. **Using SQLite for tests** - Always use PostgreSQL
3. **Creating products without CurrencyLimit/PropertyTag** - Create dependencies first
4. **Duplicating MCP/A2A code** - Use shared `_impl()` functions
5. **Silent failures** - Always raise exceptions for unsupported features
6. **Using `session.query()`** - Use SQLAlchemy 2.0 `select()` + `scalars()`
7. **Using plain `JSON` type** - Use `JSONType` for all JSON columns
8. **Unit tests only for refactoring** - Run integration tests too
9. **Bypassing hooks with `--no-verify`** - Fix the issue, don't bypass
10. **Using `ENVIRONMENT=production` locally** - Use development mode for strict validation
