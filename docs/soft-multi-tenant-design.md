# Soft Multi-Tenant Design (Shared Database)

## Overview

A practical multi-tenant design using a shared database with tenant isolation at the application level. This provides multi-publisher support without the complexity of managing multiple databases.

## Core Design

### 1. Tenant Model

```python
class Tenant(BaseModel):
    """Publisher tenant configuration stored in database."""
    tenant_id: str  # Unique identifier (e.g., "nytimes")
    name: str  # Display name
    subdomain: str  # Subdomain for access
    
    # Configuration
    config: Dict[str, Any] = {
        "adapters": {
            "google_ad_manager": {
                "enabled": True,
                "network_code": "123456",
                "company_id": "789",
                "manual_approval_required": False
            },
            "kevel": {
                "enabled": True,
                "network_id": "456",
                "manual_approval_required": True
            }
        },
        "creative_engine": {
            "auto_approve_formats": ["display_300x250", "display_728x90"],
            "human_review_required": True
        },
        "features": {
            "max_daily_budget": 100000,
            "allow_cross_device_targeting": True,
            "enable_aee_signals": True
        },
        "branding": {
            "logo_url": "https://...",
            "primary_color": "#000000"
        }
    }
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    
    # Billing
    billing_plan: str = "standard"  # standard, premium, enterprise
    billing_contact: Optional[str] = None
```

### 2. Database Schema Changes

Add `tenant_id` to all primary tables:

```sql
-- Existing tables with tenant_id added
ALTER TABLE principals ADD COLUMN tenant_id VARCHAR(50) NOT NULL;
ALTER TABLE media_buys ADD COLUMN tenant_id VARCHAR(50) NOT NULL;
ALTER TABLE creatives ADD COLUMN tenant_id VARCHAR(50) NOT NULL;
ALTER TABLE human_tasks ADD COLUMN tenant_id VARCHAR(50) NOT NULL;

-- New tenant management table
CREATE TABLE tenants (
    tenant_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    subdomain VARCHAR(100) UNIQUE NOT NULL,
    config JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    billing_plan VARCHAR(50) DEFAULT 'standard',
    billing_contact VARCHAR(255)
);

-- Indexes for performance
CREATE INDEX idx_principals_tenant ON principals(tenant_id);
CREATE INDEX idx_media_buys_tenant ON media_buys(tenant_id);
CREATE INDEX idx_subdomain ON tenants(subdomain);
```

### 3. Tenant Context Management

```python
from contextvars import ContextVar

# Thread-safe tenant context
current_tenant: ContextVar[Optional[Tenant]] = ContextVar('current_tenant', default=None)

class TenantMiddleware:
    """FastAPI/MCP middleware to set tenant context."""
    
    async def __call__(self, request: Request, call_next):
        # Extract subdomain
        host = request.headers.get('host', '')
        subdomain = host.split('.')[0] if '.' in host else None
        
        if subdomain:
            # Load tenant from database
            tenant = await get_tenant_by_subdomain(subdomain)
            if not tenant:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Tenant not found"}
                )
            
            # Set context for this request
            current_tenant.set(tenant)
            
            # Add tenant info to request state
            request.state.tenant = tenant
        
        response = await call_next(request)
        return response

def get_current_tenant() -> Tenant:
    """Get current tenant from context."""
    tenant = current_tenant.get()
    if not tenant:
        raise RuntimeError("No tenant in context")
    return tenant
```

### 4. Tenant-Aware Database Access

```python
class TenantAwareDB:
    """Database wrapper that automatically filters by tenant."""
    
    def __init__(self, db: Database):
        self.db = db
        
    def query(self, model):
        """Auto-filter queries by current tenant."""
        tenant = get_current_tenant()
        return self.db.query(model).filter(model.tenant_id == tenant.tenant_id)
    
    def create(self, model_instance):
        """Auto-set tenant_id on create."""
        tenant = get_current_tenant()
        model_instance.tenant_id = tenant.tenant_id
        return self.db.add(model_instance)

# Usage in tools
@mcp.tool
def list_products(req: ListProductsRequest, context: Context) -> ListProductsResponse:
    tenant = get_current_tenant()
    
    # Products are now filtered by tenant
    products = db.query(Product).filter(
        Product.tenant_id == tenant.tenant_id
    ).all()
    
    return ListProductsResponse(products=products)
```

### 5. Tenant Configuration Access

```python
class TenantConfigManager:
    """Manage tenant-specific configuration."""
    
    @staticmethod
    def get_config(key: str, default=None):
        """Get config value for current tenant."""
        tenant = get_current_tenant()
        
        # Navigate nested config
        keys = key.split('.')
        value = tenant.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    @staticmethod
    def get_adapter_config(adapter_name: str) -> Dict[str, Any]:
        """Get adapter-specific config for tenant."""
        return TenantConfigManager.get_config(
            f'adapters.{adapter_name}',
            default={}
        )
    
    @staticmethod
    def is_feature_enabled(feature: str) -> bool:
        """Check if feature is enabled for tenant."""
        return TenantConfigManager.get_config(
            f'features.{feature}',
            default=False
        )

# Usage in adapters
def get_adapter(principal: Principal, dry_run: bool = False) -> AdServerAdapter:
    adapter_name = SELECTED_ADAPTER
    tenant = get_current_tenant()
    
    # Get tenant-specific adapter config
    adapter_config = TenantConfigManager.get_adapter_config(adapter_name)
    
    if not adapter_config.get('enabled', False):
        raise ValueError(f"Adapter {adapter_name} not enabled for tenant {tenant.name}")
    
    # Merge with base config
    config = {
        **base_config.get(adapter_name, {}),
        **adapter_config
    }
    
    return create_adapter(adapter_name, config, principal, dry_run)
```

### 6. System Admin API

```python
@router.post("/system/tenants")
async def create_tenant(
    tenant: Tenant,
    x_system_token: str = Header(...)
):
    """Create a new tenant (system admin only)."""
    if x_system_token != SYSTEM_ADMIN_TOKEN:
        raise HTTPException(403, "Unauthorized")
    
    # Validate subdomain is unique
    existing = await get_tenant_by_subdomain(tenant.subdomain)
    if existing:
        raise HTTPException(400, "Subdomain already exists")
    
    # Create tenant
    await db.create(tenant)
    
    # Initialize default data
    await initialize_tenant_data(tenant)
    
    return {"status": "created", "tenant_id": tenant.tenant_id}

@router.put("/system/tenants/{tenant_id}/config")
async def update_tenant_config(
    tenant_id: str,
    config_update: Dict[str, Any],
    x_system_token: str = Header(...)
):
    """Update tenant configuration."""
    if x_system_token != SYSTEM_ADMIN_TOKEN:
        raise HTTPException(403, "Unauthorized")
    
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    
    # Deep merge config
    tenant.config = deep_merge(tenant.config, config_update)
    tenant.updated_at = datetime.now()
    
    await db.update(tenant)
    
    return {"status": "updated"}

@router.get("/system/tenants")
async def list_tenants(
    x_system_token: str = Header(...)
):
    """List all tenants (system admin only)."""
    if x_system_token != SYSTEM_ADMIN_TOKEN:
        raise HTTPException(403, "Unauthorized")
    
    tenants = await db.query(Tenant).all()
    
    return {
        "tenants": [
            {
                "tenant_id": t.tenant_id,
                "name": t.name,
                "subdomain": t.subdomain,
                "is_active": t.is_active,
                "billing_plan": t.billing_plan,
                "created_at": t.created_at
            }
            for t in tenants
        ]
    }
```

### 7. System Admin UI

```python
# Simple Flask admin UI
from flask import Flask, render_template, request, jsonify
from flask_login import login_required, current_user

admin_app = Flask(__name__)

@admin_app.route('/admin/tenants')
@login_required
@require_system_admin
def tenant_list():
    """List all tenants."""
    tenants = Tenant.query.all()
    return render_template('tenants/list.html', tenants=tenants)

@admin_app.route('/admin/tenants/<tenant_id>')
@login_required
@require_system_admin
def tenant_detail(tenant_id):
    """Tenant configuration editor."""
    tenant = Tenant.query.get_or_404(tenant_id)
    return render_template('tenants/detail.html', tenant=tenant)

@admin_app.route('/admin/tenants/<tenant_id>/config', methods=['POST'])
@login_required
@require_system_admin
def update_tenant_config(tenant_id):
    """Update tenant configuration."""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    # Update config from form
    config_json = request.form.get('config')
    try:
        tenant.config = json.loads(config_json)
        tenant.updated_at = datetime.now()
        db.session.commit()
        
        flash('Configuration updated successfully', 'success')
    except json.JSONDecodeError:
        flash('Invalid JSON configuration', 'error')
    
    return redirect(url_for('tenant_detail', tenant_id=tenant_id))
```

### 8. Tenant Initialization

```python
async def initialize_tenant_data(tenant: Tenant):
    """Set up initial data for a new tenant."""
    
    # Create default admin principal
    admin_principal = Principal(
        tenant_id=tenant.tenant_id,
        principal_id=f"{tenant.tenant_id}_admin",
        name=f"{tenant.name} Admin",
        platform_mappings={},
        access_token=generate_token()
    )
    await db.create(admin_principal)
    
    # Create default products based on tenant config
    if tenant.config.get('adapters', {}).get('google_ad_manager', {}).get('enabled'):
        await create_default_gam_products(tenant)
    
    # Set up default creative formats
    auto_approve_formats = tenant.config.get(
        'creative_engine', {}
    ).get('auto_approve_formats', [])
    
    # Initialize audit log
    audit_logger.log_operation(
        operation="tenant_created",
        principal_name="system",
        principal_id="system",
        adapter_id="system",
        tenant_id=tenant.tenant_id,
        success=True,
        details={"tenant_name": tenant.name}
    )
```

### 9. Authentication Updates

```python
def get_principal_from_token(token: str) -> Optional[str]:
    """Updated to be tenant-aware."""
    tenant = get_current_tenant()
    
    # Check for tenant admin token
    if token == tenant.config.get('admin_token'):
        return f"{tenant.tenant_id}_admin"
    
    # Regular principal lookup scoped to tenant
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT principal_id FROM principals WHERE access_token = ? AND tenant_id = ?",
        (token, tenant.tenant_id)
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None
```

### 10. Migration Path

```python
# Migration script for existing single-tenant to multi-tenant
def migrate_to_multi_tenant(default_tenant_id: str = "default"):
    """Add tenant_id to existing data."""
    
    # Create default tenant
    default_tenant = Tenant(
        tenant_id=default_tenant_id,
        name="Default Publisher",
        subdomain="default",
        config=load_current_config()
    )
    db.add(default_tenant)
    
    # Update all existing records
    db.execute("UPDATE principals SET tenant_id = :tenant_id", {"tenant_id": default_tenant_id})
    db.execute("UPDATE media_buys SET tenant_id = :tenant_id", {"tenant_id": default_tenant_id})
    db.execute("UPDATE creatives SET tenant_id = :tenant_id", {"tenant_id": default_tenant_id})
    db.execute("UPDATE human_tasks SET tenant_id = :tenant_id", {"tenant_id": default_tenant_id})
    
    db.commit()
```

## Benefits of This Approach

1. **Simple Operations**: One database to backup, monitor, and scale
2. **Easy Configuration**: All tenant config in database, hot-reloadable
3. **Quick Onboarding**: Create tenant, set config, ready to go
4. **Flexible Isolation**: Can add more isolation later if needed
5. **Cost Effective**: Shared resources reduce infrastructure costs

## Security Considerations

1. **Always filter by tenant_id** in queries
2. **Validate tenant context** on every request
3. **Separate system admin authentication** from tenant auth
4. **Audit log** includes tenant_id for all operations
5. **Regular testing** to ensure no cross-tenant data leaks

## Example Tenant Configurations

```python
# New York Times - Enterprise features
{
    "tenant_id": "nytimes",
    "name": "The New York Times",
    "subdomain": "nytimes",
    "config": {
        "adapters": {
            "google_ad_manager": {
                "enabled": true,
                "network_code": "123456",
                "manual_approval_required": false
            }
        },
        "features": {
            "max_daily_budget": 1000000,
            "enable_aee_signals": true,
            "allow_programmatic_guaranteed": true
        }
    },
    "billing_plan": "enterprise"
}

# Small Publisher - Basic features
{
    "tenant_id": "localnews",
    "name": "Local News Network",
    "subdomain": "localnews",
    "config": {
        "adapters": {
            "kevel": {
                "enabled": true,
                "network_id": "789",
                "manual_approval_required": true
            }
        },
        "features": {
            "max_daily_budget": 10000,
            "enable_aee_signals": false
        }
    },
    "billing_plan": "standard"
}
```

This soft multi-tenant approach gives you most of the benefits of true multi-tenancy while keeping operations simple and implementation straightforward.