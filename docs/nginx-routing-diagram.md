# Nginx Routing Visual Diagram

## Request Flow Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                USER'S BROWSER                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
         ┌──────────▼──────────┐ ┌───▼────────────┐ ┌─▼─────────────────────┐
         │ sales-agent.scope3  │ │ wonderstruck.  │ │ test-agent.adcontext  │
         │    .com             │ │ sales-agent... │ │   protocol.org        │
         │  (Main Domain)      │ │ (Tenant Sub)   │ │ (External Domain)     │
         └──────────┬──────────┘ └───┬────────────┘ └─┬─────────────────────┘
                    │                │                 │
         ┌──────────┘      (Direct) │                 └──────────┐
         │ (via Approximated)       │                   (via Approximated)
         │                           │                            │
         │  ┌──────────────────┐     │                            │
         └─►│  APPROXIMATED    │     │     ┌──────────────────┐   │
            │  Sets headers:   │     │     │  APPROXIMATED    │   │
            │  Host: sales..   │     │    ◄┤  Sets headers:   │◄──┘
            │  Apx-Incoming-   │     │     │  Host: sales..   │
            │  Host: original  │     │     │  Apx-Incoming-   │
            └────────┬─────────┘     │     │  Host: original  │
                     │                │     └──────────────────┘
                     └────────────────┼──────────┘
                                      │
                          ┌───────────▼───────────┐
                          │    FLY.IO NGINX        │
                          │                        │
                          │  For subdomains:       │
                          │    Host has subdomain  │
                          │  For others:           │
                          │    Check Apx-Incoming  │
                          └───────────┬────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
   ┌─────▼─────┐              ┌───────▼──────┐           ┌────────▼───────┐
   │ Admin UI  │              │ MCP Server   │           │  A2A Server    │
   │  :8001    │              │   :8080      │           │    :8091       │
   └───────────┘              └──────────────┘           └────────────────┘
```

## Routing Decision Matrix

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        REQUEST ARRIVES AT NGINX                             │
│                                                                             │
│  Headers depend on traffic path:                                           │
│                                                                             │
│  Tenant subdomains (Direct to Fly):                                        │
│    Host: wonderstruck.sales-agent.scope3.com  ◄─── Use Host header!       │
│    Apx-Incoming-Host: (not set)                                            │
│                                                                             │
│  Main domain & External (Via Approximated):                                │
│    Host: sales-agent.scope3.com (rewritten by Approximated)               │
│    Apx-Incoming-Host: <original-domain>  ◄─── Use this for routing!       │
└─────────────────────────────────┬──────────────────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │ Check Apx-Incoming-Host   │
                    │ Does it end with          │
                    │ .sales-agent.scope3.com?  │
                    └─────────────┬─────────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                 │
              YES               NO                 │
                │                 │                 │
    ┌───────────▼──────────┐  ┌──▼────────────────▼─────────┐
    │ Extract subdomain    │  │ External Virtual Host        │
    └───────────┬──────────┘  │                              │
                │              │ Examples:                    │
    ┌───────────▼──────────┐  │ - test-agent.adcontext...   │
    │ Subdomain empty?     │  │ - custom-domain.com         │
    └───────────┬──────────┘  │                              │
                │              │ Route: Landing page only     │
          ┌─────┴─────┐       │ Paths: /, /health            │
         YES          NO       │ Block: /admin, /mcp, /a2a   │
          │            │       └──────────────────────────────┘
          │            │
    ┌─────▼─────┐  ┌──▼─────────────┐
    │ MAIN      │  │ TENANT         │
    │ DOMAIN    │  │ SUBDOMAIN      │
    └─────┬─────┘  └──┬─────────────┘
          │           │
          │           │
┌─────────▼─────────┐ │
│ sales-agent.scope3│ │
│       .com        │ │
│                   │ │
│ Routes:           │ │
│ /      → /signup  │ │
│ /signup → OAuth   │ │
│ /login  → form    │ │
│ /admin/* → UI     │ │
│ /mcp/   → 404     │ │
│ /a2a/   → 404     │ │
│ /health → 200     │ │
└───────────────────┘ │
                      │
        ┌─────────────▼──────────────┐
        │ <tenant>.sales-agent.scope3│
        │           .com              │
        │                             │
        │ Routes:                     │
        │ /           → landing       │
        │ /admin/*    → UI + auth     │
        │ /mcp/       → MCP + auth    │
        │ /a2a/       → A2A + auth    │
        │ /.well-known → agent card   │
        │ /health     → 200           │
        │                             │
        │ Headers added:              │
        │ X-Tenant-Id: <tenant>       │
        └─────────────────────────────┘
```

## Path-Based Routing Detail

### Main Domain: `sales-agent.scope3.com`

```
https://sales-agent.scope3.com
│
├── /
│   └─► nginx: proxy_pass → admin_ui:8001/signup
│       └─► Admin UI: Renders signup page
│
├── /signup
│   └─► nginx: proxy_pass → admin_ui:8001/signup
│       └─► Admin UI: Initiates Google OAuth
│           └─► Redirects to Google
│
├── /auth/google/callback
│   └─► nginx: proxy_pass → admin_ui:8001/auth/google/callback
│       └─► Admin UI: Processes OAuth, creates tenant
│           └─► Redirects to /admin/tenant/<id>
│
├── /login
│   └─► nginx: proxy_pass → admin_ui:8001/login
│       └─► Admin UI: Shows login form
│
├── /admin/*
│   └─► nginx: proxy_pass → admin_ui:8001/admin/*
│       └─► Admin UI: Requires auth, shows dashboard
│
├── /mcp/
│   └─► nginx: return 404
│       (No tenant context on main domain)
│
├── /a2a/
│   └─► nginx: return 404
│       (No tenant context on main domain)
│
└── /health
    └─► nginx: proxy_pass → admin_ui:8001/health
        └─► Admin UI: {"status": "healthy"}
```

### Tenant Subdomain: `wonderstruck.sales-agent.scope3.com`

```
https://wonderstruck.sales-agent.scope3.com
│
├── /
│   └─► nginx: proxy_pass → admin_ui:8001/
│       └─► Admin UI: Renders landing page
│
├── /admin/*
│   └─► nginx: proxy_pass → admin_ui:8001/admin/*
│       │       X-Tenant-Id: wonderstruck
│       └─► Admin UI: Check auth, show tenant data
│
├── /mcp/
│   └─► nginx: proxy_pass → mcp_server:8080/mcp/
│       │       X-Tenant-Id: wonderstruck
│       │       x-adcp-auth: <token>
│       └─► MCP Server:
│           1. Read X-Tenant-Id header
│           2. Validate token for tenant
│           3. Return MCP response
│
├── /a2a/
│   └─► nginx: proxy_pass → a2a_server:8091/a2a/
│       │       X-Tenant-Id: wonderstruck
│       │       Authorization: Bearer <token>
│       └─► A2A Server:
│           1. Read X-Tenant-Id header
│           2. Validate token
│           3. Return A2A response
│
├── /.well-known/agent.json
│   └─► nginx: proxy_pass → a2a_server:8091/.well-known/agent.json
│       │       X-Tenant-Id: wonderstruck
│       └─► A2A Server: Return agent card for tenant
│
└── /health
    └─► nginx: proxy_pass → admin_ui:8001/health
        └─► Admin UI: {"status": "healthy"}
```

### External Domain: `test-agent.adcontextprotocol.org`

```
https://test-agent.adcontextprotocol.org
│
├── /
│   └─► nginx: proxy_pass → admin_ui:8001/
│       └─► Admin UI: Renders marketing landing page
│           (NOT tenant-specific, public marketing)
│
├── /signup
│   └─► nginx: redirect → https://sales-agent.scope3.com/signup
│       (Force users to sign up on main domain)
│
├── /admin/*
│   └─► nginx: return 403
│       (Security: no admin access on external domains)
│
├── /mcp/
│   └─► nginx: return 404
│       (No agent access on external domains)
│
├── /a2a/
│   └─► nginx: return 404
│       (No agent communication on external domains)
│
└── /.well-known/agent.json
    └─► nginx: return 404
        (External domains don't serve agents)
```

## Authentication Flow Detail

### Admin UI OAuth Flow

```
User visits: https://sales-agent.scope3.com/
│
└─► Nginx routes to: /signup
    │
    └─► Admin UI renders signup page
        │
        └─► User clicks "Sign up with Google"
            │
            └─► Admin UI redirects to Google OAuth
                │
                ├─► Google login
                │   └─► User authenticates
                │
                └─► Google redirects to callback
                    │
                    └─► https://sales-agent.scope3.com/auth/google/callback?code=...
                        │
                        └─► Admin UI:
                            1. Exchange code for token
                            2. Get user email/profile
                            3. Create tenant in database
                            4. Create session cookie
                            5. Redirect to /admin/tenant/<tenant_id>
                            │
                            └─► User sees tenant dashboard
```

### MCP Agent Authentication

```
AI Agent requests: https://wonderstruck.sales-agent.scope3.com/mcp/
Headers:
  Host: sales-agent.scope3.com
  Apx-Incoming-Host: wonderstruck.sales-agent.scope3.com
  x-adcp-auth: eyJ0eXAiOiJKV1QiLCJhbGc...
│
└─► Nginx:
    1. Extracts subdomain: "wonderstruck"
    2. Adds X-Tenant-Id: wonderstruck
    3. Forwards to mcp_server:8080
    │
    └─► MCP Server:
        1. Read X-Tenant-Id: wonderstruck
        2. Read x-adcp-auth token
        3. Query database:
           - Find tenant "wonderstruck"
           - Find principal with matching token
        4. Validate token matches tenant
        5. Execute MCP request as that principal
        6. Return MCP response
```

### A2A Agent Authentication

```
Agent requests: https://wonderstruck.sales-agent.scope3.com/a2a/
Headers:
  Host: sales-agent.scope3.com
  Apx-Incoming-Host: wonderstruck.sales-agent.scope3.com
  Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
│
└─► Nginx:
    1. Extracts subdomain: "wonderstruck"
    2. Adds X-Tenant-Id: wonderstruck
    3. Forwards to a2a_server:8091
    │
    └─► A2A Server:
        1. Read X-Tenant-Id: wonderstruck
        2. Read Authorization Bearer token
        3. Validate token for tenant
        4. Execute A2A skill
        5. Return A2A response
```

## Security Boundaries Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SECURITY LAYERS                                 │
└─────────────────────────────────────────────────────────────────────────────┘

Layer 1: Domain Type Detection (Nginx)
┌──────────────────┬──────────────────┬──────────────────┐
│ Main Domain      │ Tenant Subdomain │ External Domain  │
├──────────────────┼──────────────────┼──────────────────┤
│ Public access    │ Authenticated    │ Public (limited) │
│ to signup        │ access only      │ Landing page only│
└──────────────────┴──────────────────┴──────────────────┘
         │                 │                 │
         ▼                 ▼                 ▼
Layer 2: Path-Based Access Control (Nginx)
┌──────────────────┬──────────────────┬──────────────────┐
│ / → signup       │ / → landing      │ / → landing      │
│ /admin → UI      │ /admin → UI      │ /admin → 403     │
│ /mcp → 404       │ /mcp → auth req  │ /mcp → 404       │
│ /a2a → 404       │ /a2a → auth req  │ /a2a → 404       │
└──────────────────┴──────────────────┴──────────────────┘
                          │
                          ▼
Layer 3: Tenant Isolation (Backend)
┌─────────────────────────────────────────────────────────┐
│ Backend services read X-Tenant-Id header                │
│ Validate auth token matches tenant                      │
│ Query database WHERE tenant_id = <extracted_subdomain>  │
│ NEVER allow cross-tenant data access                    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
Layer 4: Principal Authorization (Backend)
┌─────────────────────────────────────────────────────────┐
│ Resolve principal from auth token                       │
│ Check principal belongs to tenant                       │
│ Apply principal-level permissions                       │
│ Audit log all actions                                   │
└─────────────────────────────────────────────────────────┘
```

## Common Routing Issues - Visual Guide

### ❌ Problem: External domain shows login page

```
User visits: https://test-agent.adcontextprotocol.org/
│
└─► Nginx incorrectly routes to /signup
    │
    └─► /signup redirects to /login
        │
        └─► User sees login page (WRONG!)
            Expected: Landing page
```

**Root Cause**: `$is_external_domain` map not detecting external domain

**Fix**: Ensure regex correctly identifies non-.sales-agent.scope3.com domains

### ❌ Problem: Tenant subdomain MCP returns 404

```
Agent requests: https://wonderstruck.sales-agent.scope3.com/mcp/
│
└─► Nginx returns 404 (WRONG!)
    Expected: Forward to MCP server
```

**Root Cause**: Subdomain extraction failing or MCP location block misconfigured

**Fix**: Verify `$extracted_subdomain` is populated correctly

### ❌ Problem: Infinite redirect loop

```
User visits: https://sales-agent.scope3.com/
│
└─► Nginx redirects to /signup
    │
    └─► /signup redirects to /
        │
        └─► / redirects to /signup
            │
            └─► Loop forever (WRONG!)
```

**Root Cause**: Both `/` and `/signup` configured to redirect

**Fix**: Use `proxy_pass` with variable, not redirect:
```nginx
location = / {
    proxy_pass http://admin_ui$backend_path;  # Use variable
}
```

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────┐
│                    NGINX ROUTING CHEAT SHEET                     │
├─────────────────────────────────────────────────────────────────┤
│ Domain Type           │ Detection Method                         │
├─────────────────────────────────────────────────────────────────┤
│ Main Domain           │ sales-agent.scope3.com (no subdomain)   │
│ Tenant Subdomain      │ *.sales-agent.scope3.com (has subdomain)│
│ External Virtual Host │ NOT ending in .sales-agent.scope3.com   │
├─────────────────────────────────────────────────────────────────┤
│ Critical Headers                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Host                  │ Always: sales-agent.scope3.com          │
│ Apx-Incoming-Host     │ Original domain (use for routing!)      │
│ X-Tenant-Id           │ Set by nginx (subdomain or empty)       │
├─────────────────────────────────────────────────────────────────┤
│ Backend Services                                                 │
├─────────────────────────────────────────────────────────────────┤
│ admin_ui              │ :8001 (Web UI, OAuth, dashboard)        │
│ mcp_server            │ :8080 (MCP protocol for AI agents)      │
│ a2a_server            │ :8091 (A2A protocol for agents)         │
└─────────────────────────────────────────────────────────────────┘
```
