# Documentation Index

Welcome to the AdCP Sales Agent documentation. This guide will help you find the information you need.

## Getting Started

- **[Setup Guide](SETUP.md)** - Installation, configuration, and initial setup
- **[Quick Start](../README.md#quick-start)** - Get running in under 5 minutes

## For Developers

- **[Development Guide](DEVELOPMENT.md)** - Local development, Conductor workspaces, code standards
- **[API Reference](api.md)** - Complete MCP and REST API documentation
- **[Testing Guide](testing.md)** - Running tests, writing tests, CI/CD pipeline
- **[Architecture](ARCHITECTURE.md)** - System design, database schema, technical decisions

## For Operators

- **[Deployment Guide](deployment.md)** - Docker, Fly.io, and production deployment
- **[Operations Guide](OPERATIONS.md)** - Admin UI, monitoring, tenant management
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common issues and solutions

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
- **MCP Server** - Handles AI agent requests via Model Context Protocol
- **Admin UI** - Web interface for managing tenants and monitoring
- **Adapters** - Integrations with ad servers (GAM, Kevel, Triton, Mock)
- **Database** - PostgreSQL (production) or SQLite (development)

### Core Features
- **Multi-Tenancy** - Isolated publisher environments
- **Targeting System** - Advanced audience and contextual targeting
- **Creative Management** - Upload, approval, and tracking
- **Audit Logging** - Complete operational history

## Protocol Documentation

- **[A2A Overview](a2a-overview.md)** - Agent-to-Agent protocol implementation
- **[A2A Authentication Guide](a2a-authentication-guide.md)** - Authentication patterns and security
- **[A2A Spec Clarification Issue](a2a-spec-clarification-issue.md)** - Proposed improvements to A2A artifacts specification
- **[MCP Usage Guide](mcp-usage.md)** - Model Context Protocol integration

## Documentation Structure

```
docs/
├── index.md           # This file - documentation index
├── SETUP.md           # Installation and configuration
├── DEVELOPMENT.md     # Development environment and guidelines
├── api.md             # API reference (MCP and REST)
├── testing.md         # Testing guide
├── deployment.md      # Production deployment
├── OPERATIONS.md      # Admin UI and operations
├── ARCHITECTURE.md    # System design and architecture
├── TROUBLESHOOTING.md # Common problems and solutions
├── a2a-*.md          # A2A protocol documentation
└── adcp-*.md         # AdCP protocol mappings
```

## Quick Links

- [AdCP Protocol Specification](https://github.com/adcontextprotocol/spec)
- [MCP Protocol Documentation](https://modelcontextprotocol.io)
- [GitHub Issues](https://github.com/adcontextprotocol/salesagent/issues)
- [GitHub Discussions](https://github.com/adcontextprotocol/salesagent/discussions)
