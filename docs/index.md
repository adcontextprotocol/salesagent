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

### Security & Features
- **[security.md](security.md)** - Authentication architecture and security best practices
- **[webhooks.md](webhooks.md)** - Webhook integration guide
- **[encryption.md](encryption.md)** - Data encryption and security
- **[delivery-simulation.md](delivery-simulation.md)** - Delivery reporting simulation
- **[ai-creative-summary.md](ai-creative-summary.md)** - AI creative summarization

## Specialized Documentation

### Adapters
- **[adapters/](adapters/)** - Ad server adapter documentation
  - Mock adapter guide
  - GAM configuration and testing
  - Real-world examples

### Development
- **[development/](development/)** - Development guides
  - Database patterns and migrations
  - Model import conventions
  - Schema auto-generation

### Testing
- **[testing/](testing/)** - Testing documentation
  - AdCP compliance testing (MANDATORY)
  - Pre-push workflow
  - Mocking policies

### Deployment
- **[deployment/](deployment/)** - Deployment guides
  - Docker Hub authentication

### Partners
- **[partners/](partners/)** - Partner-specific documentation
  - Bug analyses and postmortems
  - Integration notes

### Reference
- **[adcp-field-mapping.md](adcp-field-mapping.md)** - AdCP protocol field mappings

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
├── deployment.md                  # Deployment guide
├── adapters/                      # Adapter documentation
├── development/                   # Development guides
├── deployment/                    # Deployment guides
├── partners/                      # Partner-specific docs
└── testing/                       # Testing documentation
```

## Finding Information

### By Topic

**Getting Started**
- [SETUP.md](SETUP.md) - Initial setup
- [CLAUDE.md](../CLAUDE.md) - Essential development guide

**Writing Code**
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development practices
- [development/database-patterns.md](development/database-patterns.md) - Database patterns
- [development/model-import-conventions.md](development/model-import-conventions.md) - Import conventions

**Testing**
- [testing/adcp-compliance.md](testing/adcp-compliance.md) - Protocol compliance (MANDATORY)
- [testing/pre-push-workflow.md](testing/pre-push-workflow.md) - Pre-push validation

**Adapters**
- [adapters/mock-adapter-guide.md](adapters/mock-adapter-guide.md) - Mock adapter usage
- [adapters/gam-product-configuration-guide.md](adapters/gam-product-configuration-guide.md) - GAM configuration

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
3. [development/database-patterns.md](development/database-patterns.md) - Database patterns

**Adapter Development**
1. [adapters/README.md](adapters/README.md) - Adapter overview
2. [adapters/adapter-real-world-example.md](adapters/adapter-real-world-example.md) - Example implementation
3. [ARCHITECTURE.md](ARCHITECTURE.md#adapter-pattern) - Adapter architecture

**DevOps/Operations**
1. [deployment.md](deployment.md) - Deployment guide
2. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Issue resolution
3. [security.md](security.md) - Security configuration

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

## Key Concepts

### System Components
- **MCP Server** (port 8080) - FastMCP-based tools for AI agents
- **Admin UI** (port 8001) - Google OAuth secured web interface
- **A2A Server** (port 8091) - Standard python-a2a agent-to-agent communication
- **Database** - PostgreSQL (production and testing)

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
   - Adapter guides in `docs/adapters/`
   - Development guides in `docs/development/`
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
