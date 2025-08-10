# AdCP Sales Agent Documentation

## Quick Start

The AdCP Sales Agent is a reference implementation of the Advertising Context Protocol (AdCP) that enables AI agents to buy advertising inventory programmatically. It provides a unified MCP interface that abstracts away platform-specific differences.

### Running with Docker (Recommended)

```bash
# Clone and setup
git clone https://github.com/adcontextprotocol/salesagent.git
cd salesagent

# Configure environment
cp .env.example .env
# Edit .env and add:
# - GEMINI_API_KEY=your-key
# - GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET for OAuth
# - SUPER_ADMIN_EMAILS=your-email@example.com

# Start services
docker-compose up -d

# Access:
# - MCP Server: http://localhost:8080
# - Admin UI: http://localhost:8001
```

### Core Documentation

1. **[SETUP.md](SETUP.md)** - Installation, configuration, and deployment
2. **[DEVELOPMENT.md](DEVELOPMENT.md)** - Adapter development and extending the system
3. **[OPERATIONS.md](OPERATIONS.md)** - Admin UI, tenant management, and monitoring
4. **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and technical details
5. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions

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

## Key Features

- **Multi-tenant architecture** with database isolation
- **MCP protocol** implementation using FastMCP
- **Admin UI** with Google OAuth authentication
- **Multiple ad server adapters** (GAM, Kevel, Mock)
- **AI-powered product management** using Gemini
- **Creative approval workflows** with auto-approval
- **Comprehensive targeting system** with signal support
- **Audit logging** and security compliance

## Quick Links

- [AdCP Protocol Specification](https://github.com/adcontextprotocol/spec)
- [MCP Protocol Documentation](https://modelcontextprotocol.io)
- [Issue Tracker](https://github.com/adcontextprotocol/salesagent/issues)