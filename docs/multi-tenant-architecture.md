# Multi-Tenant Architecture Design

## Overview

A multi-tenant AdCP:Buy platform would allow Scope3 to host a single instance serving multiple publishers, reducing operational overhead while maintaining security isolation between tenants.

## Key Design Considerations

### 1. Tenant Isolation Strategies

#### Option A: Database-Level Isolation (Recommended)
- **Shared Application, Separate Databases**
- Each publisher gets their own database
- Connection routing based on tenant identification
- Strongest data isolation with reasonable operational overhead

```python
class TenantDatabaseRouter:
    def get_connection(self, tenant_id: str):
        return connections[f"db_{tenant_id}"]
```

**Pros:**
- Complete data isolation
- Easy backup/restore per tenant
- Can scale databases independently
- Simple security model

**Cons:**
- More databases to manage
- Connection pool overhead
- Schema migrations across all databases

#### Option B: Schema-Level Isolation
- **Shared Database, Separate Schemas**
- PostgreSQL schemas or MySQL databases
- Each tenant gets their own schema

```sql
CREATE SCHEMA publisher_nytimes;
CREATE SCHEMA publisher_wapo;
```

**Pros:**
- Fewer database connections
- Easier cross-tenant queries (for admin)
- Single database backup

**Cons:**
- Risk of cross-tenant data leaks
- Shared database performance issues
- Complex permission management

#### Option C: Row-Level Isolation
- **Shared Tables with Tenant ID**
- Every table has a `tenant_id` column
- Application enforces filtering

```python
class MediaBuy(BaseModel):
    tenant_id: str
    media_buy_id: str
    # ... other fields
```

**Pros:**
- Simplest to implement initially
- Most efficient resource usage
- Easy to add new tenants

**Cons:**
- Highest risk of data leaks
- Complex query filtering
- Performance degradation with scale
- Difficult compliance/auditing

### 2. Tenant Identification

#### Subdomain-Based (Recommended)
```
nytimes.adcp.scope3.com
wapo.adcp.scope3.com
```

```python
def get_tenant_from_request(request):
    host = request.headers.get('host')
    subdomain = host.split('.')[0]
    return tenant_registry.get(subdomain)
```

#### Header-Based
```
X-Tenant-ID: nytimes
```

#### JWT Claims
```json
{
  "sub": "user@nytimes.com",
  "tenant": "nytimes",
  "exp": 1234567890
}
```

### 3. Configuration Management

#### Tenant-Specific Configuration

```python
class TenantConfig:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.base_config = load_base_config()
        self.tenant_overrides = load_tenant_config(tenant_id)
    
    def get(self, key: str, default=None):
        # Check tenant overrides first
        if key in self.tenant_overrides:
            return self.tenant_overrides[key]
        return self.base_config.get(key, default)
```

#### Per-Tenant Features

```python
TENANT_FEATURES = {
    "nytimes": {
        "adapters": ["google_ad_manager", "kevel"],
        "manual_approval_required": True,
        "creative_auto_approve_formats": ["display_300x250"],
        "max_daily_budget": 100000
    },
    "wapo": {
        "adapters": ["google_ad_manager"],
        "manual_approval_required": False,
        "creative_auto_approve_formats": ["display_300x250", "video_vast"],
        "max_daily_budget": 50000
    }
}
```

### 4. Authentication & Authorization

#### Federated Authentication
- Each tenant configures their own SSO
- Support SAML, OAuth, OpenID Connect
- Map external identities to tenant

```python
class TenantAuthProvider:
    def __init__(self, tenant_id: str):
        self.config = get_tenant_auth_config(tenant_id)
        
    def authenticate(self, token: str) -> Optional[User]:
        if self.config.provider == "saml":
            return self.verify_saml_assertion(token)
        elif self.config.provider == "oauth":
            return self.verify_oauth_token(token)
```

#### Hierarchical Permissions
```python
class Permission:
    GLOBAL_ADMIN = "global.admin"  # Scope3 admins
    TENANT_ADMIN = "tenant.admin"  # Publisher admins
    PRINCIPAL_USER = "principal.user"  # Advertiser users
```

### 5. Multi-Tenant Adapter Management

#### Shared Adapter Instances
```python
class AdapterPool:
    def __init__(self):
        self.adapters = {}
    
    def get_adapter(self, tenant_id: str, adapter_type: str, principal: Principal):
        key = f"{tenant_id}:{adapter_type}:{principal.principal_id}"
        
        if key not in self.adapters:
            config = get_tenant_adapter_config(tenant_id, adapter_type)
            self.adapters[key] = create_adapter(adapter_type, config, principal)
        
        return self.adapters[key]
```

#### Tenant-Specific Credentials
```python
# Encrypted credential storage per tenant
TENANT_CREDENTIALS = {
    "nytimes": {
        "google_ad_manager": {
            "service_account_key": encrypt("..."),
            "network_code": "123456"
        }
    }
}
```

### 6. Resource Limits & Quotas

```python
class TenantQuotaManager:
    def check_quota(self, tenant_id: str, resource: str, amount: int = 1):
        quota = self.get_quota(tenant_id, resource)
        usage = self.get_current_usage(tenant_id, resource)
        
        if usage + amount > quota.limit:
            raise QuotaExceededError(f"Quota exceeded for {resource}")
        
        return True
    
    def get_quotas(self, tenant_id: str):
        return {
            "media_buys_per_month": 1000,
            "api_calls_per_hour": 10000,
            "total_spend_per_month": 1000000,
            "concurrent_campaigns": 100
        }
```

### 7. Operational Considerations

#### Deployment Architecture

```yaml
# Kubernetes namespace per tenant
apiVersion: v1
kind: Namespace
metadata:
  name: tenant-nytimes
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: adcp-server
  namespace: tenant-nytimes
spec:
  replicas: 3
  env:
    - name: TENANT_ID
      value: "nytimes"
```

#### Monitoring & Alerting
- Tenant-tagged metrics
- Per-tenant dashboards
- Isolated alert channels

```python
def log_metric(metric_name: str, value: float, tenant_id: str):
    statsd.gauge(
        f"adcp.{metric_name}",
        value,
        tags=[f"tenant:{tenant_id}"]
    )
```

#### Backup & Disaster Recovery
- Per-tenant backup schedules
- Isolated restore procedures
- Tenant-specific data retention

### 8. Migration Path

#### Phase 1: Current State (Single-Tenant)
- Each publisher runs their own instance
- Complete isolation
- High operational overhead

#### Phase 2: Soft Multi-Tenancy
- Shared codebase, separate deployments
- Centralized management plane
- Gradual feature convergence

#### Phase 3: True Multi-Tenancy
- Single deployment, multiple tenants
- Database-level isolation
- Full resource sharing

### 9. Implementation Recommendations

1. **Start with Database Isolation**
   - Easiest to reason about
   - Strongest security guarantees
   - Can optimize later if needed

2. **Use Middleware for Tenant Context**
   ```python
   @app.middleware("http")
   async def tenant_middleware(request: Request, call_next):
       tenant = get_tenant_from_request(request)
       request.state.tenant = tenant
       
       # Set database connection
       request.state.db = get_tenant_db(tenant.id)
       
       response = await call_next(request)
       return response
   ```

3. **Implement Tenant-Aware Caching**
   ```python
   def cache_key(tenant_id: str, key: str) -> str:
       return f"tenant:{tenant_id}:{key}"
   ```

4. **Abstract Tenant Operations**
   ```python
   class TenantAwareRepository:
       def __init__(self, tenant_id: str):
           self.tenant_id = tenant_id
           self.db = get_tenant_db(tenant_id)
       
       def get_media_buys(self):
           # Automatically scoped to tenant
           return self.db.query(MediaBuy).all()
   ```

### 10. Security Considerations

1. **Tenant Isolation Testing**
   - Automated tests for cross-tenant access
   - Regular security audits
   - Penetration testing per tenant

2. **Data Encryption**
   - Per-tenant encryption keys
   - Encrypted data at rest
   - Key rotation policies

3. **Compliance**
   - Per-tenant data residency
   - Isolated audit logs
   - Tenant-specific compliance reports

### 11. Cost Model Implications

#### Resource Attribution
```python
class ResourceTracker:
    def track_api_call(self, tenant_id: str, endpoint: str, duration: float):
        self.db.insert({
            "tenant_id": tenant_id,
            "resource": "api_call",
            "endpoint": endpoint,
            "duration": duration,
            "timestamp": datetime.now()
        })
    
    def calculate_monthly_usage(self, tenant_id: str):
        return {
            "api_calls": self.count_api_calls(tenant_id),
            "storage_gb": self.calculate_storage(tenant_id),
            "compute_hours": self.calculate_compute(tenant_id)
        }
```

#### Billing Integration
- Usage-based pricing per tenant
- Resource consumption reports
- Automated invoicing

### 12. Conclusion

For Scope3's hosted AdCP:Buy platform, I recommend:

1. **Database-level isolation** for security and simplicity
2. **Subdomain-based tenant identification** for clarity
3. **Kubernetes namespaces** for deployment isolation
4. **Centralized configuration** with tenant overrides
5. **Gradual migration path** from single to multi-tenant

This approach balances security, operational efficiency, and implementation complexity while providing a clear path to scale the platform across multiple publishers.