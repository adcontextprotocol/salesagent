# AdCP Sales Agent Documentation

## Quick Start

- **[CLAUDE.md](../CLAUDE.md)** - Essential development guide (START HERE)
- **[SETUP.md](SETUP.md)** - Installation and configuration
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture overview

## Hosting Flexibility

**This reference implementation can be hosted anywhere:**
- Docker (any platform that supports containers)
- Kubernetes (enterprise deployments)
- Cloud providers (AWS, GCP, Azure, DigitalOcean, etc.)
- Platform services (Fly.io, Heroku, Railway, Render, etc.)
- Bare metal (direct Python deployment)

See [deployment.md](deployment.md) for platform-specific guides. We support your chosen infrastructure!

## Core Documentation

### Development
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Development workflows and best practices
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[deployment.md](deployment.md)** - Production deployment guide

### Security & Authentication
- **[security.md](security.md)** - Authentication architecture and security best practices
- **[a2a-authentication-guide.md](a2a-authentication-guide.md)** - A2A authentication specifics

## Testing Documentation

### Overview
- **[testing.md](testing.md)** - Testing strategy overview
- **[testing/README.md](testing/README.md)** - Testing directory index

### Detailed Guides
- **[testing/adcp-compliance.md](testing/adcp-compliance.md)** - AdCP protocol compliance testing (MANDATORY)
- **[testing/mcp-roundtrip-validation.md](testing/mcp-roundtrip-validation.md)** - MCP tool roundtrip patterns
- **[testing/a2a-regression-prevention.md](testing/a2a-regression-prevention.md)** - A2A regression prevention

### Specialized Testing
- **[testing-database-field-access.md](testing-database-field-access.md)** - Database field access patterns
- **[gam-testing-setup.md](gam-testing-setup.md)** - GAM testing configuration

## Protocol Implementation

### A2A (Agent-to-Agent)
- **[a2a-implementation-guide.md](a2a-implementation-guide.md)** - Complete A2A implementation guide
- **[a2a-overview.md](a2a-overview.md)** - A2A protocol overview

### MCP (Model Context Protocol)
- **[api.md](api.md)** - MCP API reference
- **[mcp-usage.md](mcp-usage.md)** - Using the MCP client

### AdCP (Advertising Context Protocol)
- **[adcp-field-mapping.md](adcp-field-mapping.md)** - AdCP protocol field mappings

## Database & Schema

- **[database-patterns.md](database-patterns.md)** - Database design patterns
- **[schema-sync-enforcement.md](schema-sync-enforcement.md)** - Schema validation and alignment
- **[model-import-conventions.md](model-import-conventions.md)** - Import patterns and conventions

## System Overview

```
┌─────────────────┐     ┌──────────────────┐
│   AI Agent      │────▶│  AdCP Sales Agent│
└─────────────────┘     └──────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
        ┌──────────────┐ ┌────────┐ ┌──────────────┐
        │ Google Ad    │ │ Kevel  │ │ Mock         │
        │ Manager      │ │        │ │ Adapter      │
        └──────────────┘ └────────┘ └──────────────┘
```

## Documentation Structure

```
docs/
├── index.md (this file)           # Documentation index
├── CLAUDE.md (../CLAUDE.md)       # Essential dev guide
├── SETUP.md                       # Getting started
├── ARCHITECTURE.md                # System design
├── DEVELOPMENT.md                 # Dev workflows
├── TROUBLESHOOTING.md             # Issue resolution
├── security.md                    # Security & auth
├── a2a-implementation-guide.md    # A2A complete guide
└── testing/                       # Testing documentation
    ├── README.md                  # Testing index
    ├── adcp-compliance.md         # Protocol compliance
    ├── mcp-roundtrip-validation.md # MCP patterns
    └── a2a-regression-prevention.md # A2A regression tests
```

## Finding Information

### By Topic

**Getting Started**
- [SETUP.md](SETUP.md) - Initial setup
- [CLAUDE.md](../CLAUDE.md) - Essential development guide

**Writing Code**
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development practices
- [database-patterns.md](database-patterns.md) - Database patterns
- [model-import-conventions.md](model-import-conventions.md) - Import conventions

**Testing**
- [testing/adcp-compliance.md](testing/adcp-compliance.md) - Protocol compliance (MANDATORY)
- [testing/mcp-roundtrip-validation.md](testing/mcp-roundtrip-validation.md) - MCP tool testing
- [testing/a2a-regression-prevention.md](testing/a2a-regression-prevention.md) - A2A regression prevention

**Protocols**
- [a2a-implementation-guide.md](a2a-implementation-guide.md) - Complete A2A guide
- [mcp-usage.md](mcp-usage.md) - MCP client usage
- [adcp-field-mapping.md](adcp-field-mapping.md) - AdCP field mappings

**Deployment & Operations**
- [deployment.md](deployment.md) - Production deployment
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
- [security.md](security.md) - Security best practices

### By Role

**New Developers**
1. Read [CLAUDE.md](../CLAUDE.md)
2. Follow [SETUP.md](SETUP.md)
3. Review [ARCHITECTURE.md](ARCHITECTURE.md)
4. Study [testing/adcp-compliance.md](testing/adcp-compliance.md)

**Feature Development**
1. [DEVELOPMENT.md](DEVELOPMENT.md) - Workflows
2. [testing/adcp-compliance.md](testing/adcp-compliance.md) - Compliance testing
3. [database-patterns.md](database-patterns.md) - Database patterns

**Protocol Implementation**
1. [a2a-implementation-guide.md](a2a-implementation-guide.md) - A2A complete guide
2. [mcp-usage.md](mcp-usage.md) - MCP patterns
3. [adcp-field-mapping.md](adcp-field-mapping.md) - AdCP mappings

**DevOps/Operations**
1. [deployment.md](deployment.md) - Deployment guide
2. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Issue resolution
3. [security.md](security.md) - Security configuration

## Key Concepts

### System Components
- **MCP Server** (port 8080) - FastMCP-based tools for AI agents
- **Admin UI** (port 8001) - Google OAuth secured web interface
- **A2A Server** (port 8091) - Standard python-a2a agent-to-agent communication
- **Database** - PostgreSQL (production) or SQLite (development)

### Core Features
- **Multi-Tenancy** - Database-backed isolation with subdomain routing
- **Authorized Properties** - AdCP-compliant property management
- **Advanced Targeting** - Comprehensive targeting system
- **Creative Management** - Auto-approval workflows and admin review
- **Audit Logging** - Complete operational history and security tracking

## Need Help?

If you can't find what you're looking for:

1. Check [CLAUDE.md](../CLAUDE.md) for essentials
2. Search this documentation directory
3. Review [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
4. Check test files for usage examples
5. Consult code comments and docstrings

## Contributing to Documentation

When adding new documentation:

1. **Location**: Place in appropriate directory
   - Core guides in `docs/`
   - Testing guides in `docs/testing/`
2. **Style**: Use clear, descriptive headings
3. **Examples**: Include code examples where helpful
4. **Links**: Link to related documents
5. **Focus**: Keep content focused and concise
6. **Index**: Update this index file

### Documentation Standards

- Use Markdown format
- Start with clear overview
- Include table of contents for long docs
- Use code blocks with syntax highlighting
- Add "See Also" links at the end
- Keep examples realistic and tested

## Quick Links

- [AdCP Protocol Specification](https://adcontextprotocol.org/docs/)
- [MCP Protocol Documentation](https://modelcontextprotocol.io)
- [python-a2a Library](https://github.com/google/python-a2a)
- [GitHub Repository](https://github.com/adcontextprotocol/salesagent)
