# Model Import Conventions

## Problem Statement

The codebase has two types of models that are easily confused:

1. **SQLAlchemy ORM Models** (`models.py`) - For database operations
2. **Pydantic Models** (`schemas.py`) - For API contracts and validation

This confusion leads to runtime errors like:
- `AttributeError: type object 'AdapterConfig' has no attribute 'model_validate_json'`
- `TypeError: the JSON object must be str, bytes or bytearray, not AdapterConfig`

## Import Conventions

### ✅ CORRECT Patterns

#### 1. Use Clear Naming for Mixed Imports
```python
# When you need both versions
from models import Principal as PrincipalModel
from schemas import Principal as PrincipalSchema

# Or use module imports
import models
import schemas

principal_db = models.Principal()  # Database model
principal_api = schemas.Principal() # API model
```

#### 2. Import Only What You Need
```python
# For database operations only
from models import Tenant, AdapterConfig

# For API/validation only
from schemas import CreateMediaBuyRequest, MediaBuyResponse
```

#### 3. Accessing Relationships Correctly
```python
# CORRECT - AdapterConfig is a relationship
with get_db_session() as db_session:
    tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
    if tenant.adapter_config:
        adapter_type = tenant.adapter_config.adapter_type
        network_code = tenant.adapter_config.gam_network_code
```

### ❌ WRONG Patterns

#### 1. Using Pydantic Methods on SQLAlchemy Models
```python
# WRONG - AdapterConfig from models.py doesn't have model_validate_json
from models import AdapterConfig
config = AdapterConfig.model_validate_json(data)  # AttributeError!
```

#### 2. Treating Relationships as JSON
```python
# WRONG - tenant.adapter_config is a relationship, not JSON string
import json
config = json.loads(tenant.adapter_config)  # TypeError!
```

#### 3. Mixed Imports Without Clear Naming
```python
# WRONG - Confusing which is which
from models import Principal
from schemas import Principal  # This overwrites the first import!
```

## Database Schema Migration Issues

### Legacy vs Current Schema

The codebase went through a schema migration:

**Legacy (OLD):**
```sql
-- adapter_config was a JSON string in tenants table
tenants (
  tenant_id TEXT,
  adapter_config TEXT  -- JSON string
)
```

**Current (NEW):**
```sql
-- adapter_config is now a separate table
tenants (tenant_id TEXT, ad_server TEXT)
adapter_config (tenant_id TEXT, adapter_type TEXT, gam_network_code TEXT, ...)
```

### Fixing Legacy Code

If you find code expecting the old schema:

```python
# OLD (BROKEN)
if tenant.adapter_config:
    config = json.loads(tenant.adapter_config)
    if config.get("google_ad_manager", {}).get("enabled"):
        ...

# NEW (CORRECT)
if tenant.adapter_config:
    if tenant.adapter_config.adapter_type == "google_ad_manager":
        ...
```

## Validation

Use the validation script to catch these issues:

```bash
python3 scripts/validate_model_confusion.py
```

This will detect:
- Pydantic methods called on SQLAlchemy models
- `json.loads()` called on relationship fields
- Other common confusion patterns

## When to Use Which Model

| Use Case | Import From | Example |
|----------|-------------|---------|
| Database queries | `models` | `session.query(Tenant).filter_by(...)` |
| API request/response | `schemas` | `request_data = CreateTenantRequest(**data)` |
| Adapter logic | `schemas` | `principal.get_adapter_id()` |
| Template context | `models` | Passing DB objects to templates |
| Data validation | `schemas` | Validating form input |

## Migration Checklist

When migrating code from legacy to current schema:

1. ✅ Check if code uses `json.loads(tenant.adapter_config)`
2. ✅ Replace with direct field access: `tenant.adapter_config.field_name`
3. ✅ Update imports to be explicit about model source
4. ✅ Run validation script to catch remaining issues
5. ✅ Test with actual database to ensure it works

## Common Fields Migration

| Legacy JSON Path | New Field Access |
|------------------|------------------|
| `config["google_ad_manager"]["network_code"]` | `adapter_config.gam_network_code` |
| `config["google_ad_manager"]["enabled"]` | `adapter_config.adapter_type == "google_ad_manager"` |
| `config["mock"]["dry_run"]` | `adapter_config.mock_dry_run` |
| `config["kevel"]["network_id"]` | `adapter_config.kevel_network_id` |
