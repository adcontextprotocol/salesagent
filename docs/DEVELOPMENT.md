# Development Guide

## Creating Ad Server Adapters

### Base Adapter Structure

```python
from adapters.base import AdServerAdapter
from schemas import *

class MyPlatformAdapter(AdServerAdapter):
    adapter_name = "myplatform"
    
    def __init__(self, config, principal, dry_run=False, creative_engine=None):
        super().__init__(config, principal, dry_run, creative_engine)
        self.advertiser_id = self.principal.get_adapter_id("myplatform")
        
    def create_media_buy(self, request, packages, start_time, end_time):
        # Implementation
        
    def get_avails(self, request):
        # Implementation
        
    def activate_media_buy(self, media_buy_id):
        # Implementation
```

### Required Methods

1. **get_avails** - Check inventory availability
2. **create_media_buy** - Create campaigns/orders
3. **activate_media_buy** - Activate pending campaigns
4. **pause_media_buy** - Pause active campaigns
5. **get_media_buy_status** - Get campaign status
6. **get_media_buy_performance** - Get performance metrics

### Adapter Configuration UI

Adapters can provide custom configuration interfaces:

```python
def get_config_ui_endpoint(self) -> Optional[str]:
    return f"/adapters/{self.adapter_name}/config"

def register_ui_routes(self, app, db_session_factory):
    @app.route(self.get_config_ui_endpoint() + "/<tenant_id>/<product_id>")
    def config_ui(tenant_id, product_id):
        # Render configuration UI
        
def validate_product_config(self, config: dict) -> tuple[bool, Optional[str]]:
    # Validate adapter-specific configuration
```

## Targeting System

### Targeting Capabilities

The system supports two-tier targeting:

1. **Overlay Dimensions** - Available to principals
   - Geography, demographics, interests, devices
   - AEE signals, contextual targeting

2. **Managed-Only Dimensions** - Internal use only
   - Platform-specific optimizations
   - Reserved inventory segments

### Platform Mapping

Each adapter translates AdCP targeting to platform-specific format:

```python
def _translate_targeting(self, overlay):
    platform_targeting = {}
    
    if "geo_country_any_of" in overlay:
        platform_targeting["location"] = {
            "countries": overlay["geo_country_any_of"]
        }
    
    if "signals" in overlay:
        platform_targeting["custom_targeting"] = {
            "keys": self._map_signals(overlay["signals"])
        }
    
    return platform_targeting
```

## Testing

### Running Tests

```bash
# All tests
uv run pytest

# Specific category
uv run pytest tests/unit/
uv run pytest tests/integration/

# With coverage
uv run pytest --cov=. --cov-report=html

# Inside Docker
docker exec -it adcp-server pytest
```

### Test Categories

- **Unit Tests** - Component isolation tests
- **Integration Tests** - Full workflow tests
- **Adapter Tests** - Platform-specific tests
- **UI Tests** - Admin interface tests

### Simulation Testing

```bash
# Full lifecycle simulation
uv run python run_simulation.py

# Dry-run mode (logs API calls)
uv run python run_simulation.py --dry-run --adapter gam

# Custom scenarios
uv run python simulation_full.py http://localhost:8080 \
  --token "test_token" \
  --principal "test_principal"
```

## Database Development

### Schema Changes

1. Check existing schema first:
```bash
grep -r "Column(" models.py
sqlite3 adcp_local.db ".schema table_name"
```

2. Create migration:
```bash
uv run alembic revision -m "add_new_column"
```

3. Edit migration file:
```python
def upgrade():
    op.add_column('table_name', 
        sa.Column('new_column', sa.String(100)))

def downgrade():
    op.drop_column('table_name', 'new_column')
```

4. Test migration:
```bash
# Test on copy
cp adcp_local.db test.db
DATABASE_URL=sqlite:///test.db uv run python migrate.py
```

### Database Best Practices

- Always use SQLAlchemy's `sa.table()` in migrations
- Handle both SQLite and PostgreSQL differences
- Use scoped sessions for thread safety
- Test with both database types

## API Development

### MCP Tools

Tools are exposed via FastMCP:

```python
@app.tool
async def get_products(
    context: Context,
    brief: Optional[str] = None
) -> GetProductsResponse:
    # Get auth from headers
    auth_token = context.http.headers.get("x-adcp-auth")
    
    # Resolve principal and tenant
    principal, tenant = await resolve_auth(auth_token)
    
    # Return products
    return GetProductsResponse(products=products)
```

### Adding New Tools

1. Define schema in `schemas.py`
2. Implement tool in `main.py`
3. Add tests in `test_main.py`
4. Update documentation

## UI Development

### Template Development

- Always extend `base.html`
- Use Bootstrap classes (loaded in base)
- Avoid global CSS resets
- Test element visibility

### JavaScript Best Practices

```javascript
// Handle nulls
const value = (data.field || 'default');

// Check elements exist
const element = document.getElementById('id');
if (element) {
    // Safe to use
}

// API calls with error handling
try {
    const response = await fetch('/api/endpoint', {
        credentials: 'same-origin'
    });
    if (!response.ok) throw new Error('Failed');
    const data = await response.json();
} catch (error) {
    console.error('API error:', error);
}
```

## Security Considerations

### Authentication

- MCP uses `x-adcp-auth` header tokens
- Admin UI uses Google OAuth
- Principals have unique tokens per advertiser
- Super admins configured via environment

### Audit Logging

All operations are logged to database:

```python
from audit_logger import AuditLogger

logger = AuditLogger(db_session)
logger.log(
    operation="create_media_buy",
    principal_id=principal.principal_id,
    tenant_id=tenant_id,
    success=True,
    details={"media_buy_id": result.media_buy_id}
)
```

## Development Workflow

1. **Make changes** in feature branch
2. **Run tests** locally with pytest
3. **Test in Docker** with docker-compose
4. **Check migrations** if schema changed
5. **Update documentation** if adding features
6. **Create PR** with description

## Common Patterns

### Error Handling

```python
try:
    result = perform_operation()
except ValidationError as e:
    return {"error": str(e)}, 400
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return {"error": "Internal error"}, 500
finally:
    db_session.remove()
```

### Database Sessions

```python
from sqlalchemy.orm import scoped_session

db_session = scoped_session(SessionLocal)
try:
    db_session.remove()  # Start fresh
    # Do work
    db_session.commit()
except Exception:
    db_session.rollback()
    raise
finally:
    db_session.remove()
```