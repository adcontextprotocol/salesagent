# Template Updates for sales-agent.scope3.com Domain

## Backend Changes Required

### 1. Environment Variables
Add to production environment:
```bash
CUSTOM_DOMAIN=sales-agent.scope3.com
ENABLE_SUBDOMAIN_ROUTING=true
```

### 2. Template Context Updates
Update `src/admin/blueprints/core.py` and `src/admin/blueprints/tenants.py`:

```python
# Add these variables to template context
custom_domain = os.environ.get("CUSTOM_DOMAIN")
enable_subdomain_routing = os.environ.get("ENABLE_SUBDOMAIN_ROUTING", "false").lower() == "true"

return render_template(
    "index.html",
    tenants=tenant_list,
    mcp_port=mcp_port,
    is_production=is_production,
    custom_domain=custom_domain,
    enable_subdomain_routing=enable_subdomain_routing
)
```

## Template Updates

### Updated index.html Logic
```jinja2
<td>
    {% if tenant.virtual_host %}
    <code>{{ tenant.virtual_host }}</code>
    <br><small style="color: #666;">https://{{ tenant.virtual_host }}/mcp/</small>
    <br><small style="color: #999;">(Virtual Host)</small>
    {% elif custom_domain and enable_subdomain_routing and is_production %}
    <code>{{ tenant.subdomain }}</code>
    <br><small style="color: #666;">https://{{ tenant.subdomain }}.{{ custom_domain }}/mcp/</small>
    <br><small style="color: #999;">(Scope3 Subdomain)</small>
    {% elif is_production %}
    <code>{{ tenant.subdomain }}</code>
    <br><small style="color: #666;">https://adcp-sales-agent.fly.dev/mcp/</small>
    <br><small style="color: #999;">(use x-adcp-tenant: {{ tenant.subdomain }})</small>
    {% else %}
    <code>{{ tenant.subdomain }}</code>
    <br><small style="color: #666;">http://localhost:{{ mcp_port }}/mcp/</small>
    <br><small style="color: #999;">(use x-adcp-tenant: {{ tenant.subdomain }})</small>
    {% endif %}
</td>
```

### Updated tenant_settings.html Logic
```jinja2
<!-- MCP Server Endpoint -->
<pre style="margin: 0;">{% if tenant.virtual_host %}https://{{ tenant.virtual_host }}/mcp/{% elif custom_domain and enable_subdomain_routing and is_production %}https://{{ tenant.subdomain }}.{{ custom_domain }}/mcp/{% elif is_production %}https://adcp-sales-agent.fly.dev/mcp/{% else %}http://localhost:{{ mcp_port }}/mcp/{% endif %}</pre>

<!-- Python Client Example -->
headers = {
    "x-adcp-auth": "YOUR_ACCESS_TOKEN"{% if not tenant.virtual_host and not (custom_domain and enable_subdomain_routing and is_production) %},
    "x-adcp-tenant": "{{ tenant.subdomain }}"{% endif %}
}
```

## Expected Display Results

### Production with Scope3 Domain (After Setup):
```
Tenant Name       | Tenant Access
Default Publisher | default
                  | https://default.sales-agent.scope3.com/mcp/
                  | (Scope3 Subdomain)

Scribd           | scribd
                 | https://scribd.sales-agent.scope3.com/mcp/
                 | (Scope3 Subdomain)

Custom Publisher  | example.com
                  | https://example.com/mcp/
                  | (Virtual Host)
```

### Production Fallback (Current):
```
Tenant Name       | Tenant Access
Default Publisher | default
                  | https://adcp-sales-agent.fly.dev/mcp/
                  | (use x-adcp-tenant: default)

Scribd           | scribd
                 | https://adcp-sales-agent.fly.dev/mcp/
                 | (use x-adcp-tenant: scribd)
```

### Development (Unchanged):
```
Tenant Name       | Tenant Access
Default Publisher | default
                  | http://localhost:8148/mcp/
                  | (use x-adcp-tenant: default)

Scribd           | scribd
                 | http://localhost:8148/mcp/
                 | (use x-adcp-tenant: scribd)
```

## API Call Examples

### With Scope3 Subdomain (Clean):
```bash
# No headers needed for tenant identification
curl -H "x-adcp-auth: TOKEN" \
     https://scribd.sales-agent.scope3.com/mcp/tools/get_products

curl -H "x-adcp-auth: TOKEN" \
     https://nytimes.sales-agent.scope3.com/mcp/tools/get_products
```

### Fallback Path-based (Current):
```bash
# Requires tenant header
curl -H "x-adcp-auth: TOKEN" \
     -H "x-adcp-tenant: scribd" \
     https://adcp-sales-agent.fly.dev/mcp/tools/get_products
```

## Migration Strategy

1. **Setup DNS and certificates** (scope3.com zone)
2. **Deploy environment variables** (CUSTOM_DOMAIN, ENABLE_SUBDOMAIN_ROUTING)
3. **Deploy template updates**
4. **Test both old and new URLs** (backward compatibility)
5. **Update documentation** to show new primary URLs
6. **Gradually migrate tenants** to new subdomain URLs

The system will gracefully handle the transition with full backward compatibility.
