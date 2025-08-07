# Development Best Practices for AdCP Sales Agent

## Preventing Common Issues

### 1. Database Schema Management

#### Use Migration Testing
```bash
# Always test migrations on a copy of production data
python migrate.py --dry-run
python migrate.py --test-rollback
```

#### Schema Validation
```python
# Add to CI/CD pipeline
from alembic import command
from alembic.config import Config

def test_migrations():
    """Ensure all migrations can run up and down."""
    alembic_cfg = Config("alembic.ini")
    
    # Test upgrade
    command.upgrade(alembic_cfg, "head")
    
    # Test downgrade
    command.downgrade(alembic_cfg, "base")
```

#### Column Length Constants
```python
# constants.py
class DBLimits:
    INVENTORY_TYPE_MAX_LENGTH = 30
    TENANT_ID_MAX_LENGTH = 50
    STATUS_MAX_LENGTH = 20

# models.py
inventory_type = Column(String(DBLimits.INVENTORY_TYPE_MAX_LENGTH))
```

### 2. Code Organization

#### Separate Concerns
```
models/
├── __init__.py
├── orm.py          # SQLAlchemy ORM models
├── api.py          # Pydantic API models  
└── converters.py   # ORM ↔ API converters
```

#### Type Safety with Pydantic
```python
from pydantic import BaseModel, validator
from typing import Literal

class InventoryType(BaseModel):
    type: Literal["ad_unit", "placement", "label", "custom_targeting_key", "custom_targeting_value"]
    
    @validator('type')
    def validate_length(cls, v):
        if len(v) > DBLimits.INVENTORY_TYPE_MAX_LENGTH:
            raise ValueError(f"Inventory type too long: {len(v)} > {DBLimits.INVENTORY_TYPE_MAX_LENGTH}")
        return v
```

### 3. External API Management

#### Version Pinning
```python
# requirements.txt
googleads==24.1.0  # Pin specific version
zeep==4.1.0       # Pin SOAP library version
```

#### API Compatibility Layer
```python
# adapters/gam_api_compat.py
class GAMAPICompat:
    """Compatibility layer for GAM API changes."""
    
    @staticmethod
    def create_statement_builder(client, version=None):
        """Create statement builder compatible with multiple API versions."""
        if hasattr(client.GetDataDownloader(), 'new_filter_statement'):
            # Old API
            return client.GetDataDownloader().new_filter_statement()
        else:
            # New API
            from googleads import ad_manager
            return ad_manager.StatementBuilder(version=version or 'v202411')
    
    @staticmethod
    def serialize_response(obj):
        """Convert SUDS/Zeep objects to dictionaries."""
        from zeep.helpers import serialize_object
        return serialize_object(obj) if hasattr(obj, '__dict__') else obj
```

### 4. Testing Strategy

#### Integration Test Suite
```python
# tests/integration/test_gam_sync.py
import pytest
from unittest.mock import Mock, patch

class TestGAMInventorySync:
    @pytest.fixture
    def mock_gam_client(self):
        """Mock GAM client with realistic responses."""
        client = Mock()
        # Mock all expected API calls
        return client
    
    def test_full_sync_workflow(self, mock_gam_client, test_db):
        """Test complete sync workflow."""
        service = GAMInventoryService(test_db)
        summary = service.sync_tenant_inventory("test_tenant", mock_gam_client)
        
        # Verify all data saved correctly
        assert test_db.query(GAMInventory).count() > 0
        assert all(inv.inventory_type in VALID_INVENTORY_TYPES 
                  for inv in test_db.query(GAMInventory).all())
```

#### Schema Compatibility Tests
```python
# tests/test_schema_compat.py
def test_no_config_column_references():
    """Ensure no code references tenant.config."""
    import ast
    import os
    
    for root, dirs, files in os.walk("app"):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file)) as f:
                    tree = ast.parse(f.read())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Attribute):
                            if node.attr == "config" and \
                               isinstance(node.value, ast.Name) and \
                               "tenant" in node.value.id.lower():
                                raise AssertionError(f"Found tenant.config reference in {file}")
```

### 5. Development Workflow

#### Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: check-migrations
        name: Check database migrations
        entry: python scripts/check_migrations.py
        language: system
        pass_filenames: false
      
      - id: validate-models
        name: Validate model constraints
        entry: python scripts/validate_models.py
        language: system
        files: 'models\.py$'
```

#### CI/CD Pipeline
```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Run migrations
        run: |
          python migrate.py
          python migrate.py --rollback
          python migrate.py
      
      - name: Run integration tests
        run: pytest tests/integration -v
      
      - name: Check schema compatibility
        run: python scripts/check_schema_compat.py
```

### 6. Monitoring and Alerting

#### Health Checks
```python
# health_checks.py
async def check_database_schema():
    """Verify database schema matches models."""
    from alembic import script
    from alembic.runtime import migration
    
    alembic_cfg = Config("alembic.ini")
    script_dir = script.ScriptDirectory.from_config(alembic_cfg)
    
    with engine.begin() as conn:
        context = migration.MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        head_rev = script_dir.get_current_head()
        
        if current_rev != head_rev:
            raise HealthCheckError(f"Database schema out of sync: {current_rev} != {head_rev}")
```

#### Error Tracking
```python
# adapters/error_tracking.py
import sentry_sdk
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[SqlalchemyIntegration()],
    traces_sample_rate=0.1,
    before_send=filter_sensitive_data
)

def filter_sensitive_data(event, hint):
    """Remove sensitive data before sending to Sentry."""
    # Filter out tokens, passwords, etc.
    return event
```

## Implementation Checklist

- [ ] Set up pre-commit hooks for migration validation
- [ ] Add integration tests for all external API calls
- [ ] Create compatibility layers for external APIs
- [ ] Implement schema validation in CI/CD
- [ ] Add health checks for schema compatibility
- [ ] Set up error tracking with proper filtering
- [ ] Document all breaking changes in MIGRATION_GUIDE.md
- [ ] Create rollback procedures for all migrations
- [ ] Add type hints and Pydantic validation throughout
- [ ] Set up automated dependency updates with testing

## Conclusion

By implementing these practices, you can significantly reduce the likelihood of similar issues in the future. The key is to catch problems early through:

1. **Build-time validation** instead of runtime errors
2. **Comprehensive testing** including integration tests
3. **Clear separation of concerns** in code organization
4. **Proactive monitoring** of schema and API compatibility
5. **Strict version control** for external dependencies

Remember: every production issue is an opportunity to improve your development processes. Use post-mortems to continuously refine these practices.