# AdCP Sales Agent

A reference implementation of the Advertising Context Protocol (AdCP) V2.3 sales agent, enabling AI agents to buy advertising inventory through a standardized MCP (Model Context Protocol) interface.

## What is this?

The AdCP Sales Agent is a server that:
- **Exposes advertising inventory** to AI agents via MCP protocol
- **Manages multi-tenant publishers** with isolated data and configuration
- **Integrates with ad servers** like Google Ad Manager, Kevel, and Triton
- **Provides an admin interface** for managing inventory and monitoring campaigns
- **Handles the full campaign lifecycle** from discovery to reporting

## Quick Start

```bash
# Clone the repository
git clone https://github.com/adcontextprotocol/salesagent.git
cd salesagent

# Copy and configure environment
cp .env.example .env
# Edit .env with your GEMINI_API_KEY and Google OAuth credentials

# Start with Docker Compose
docker-compose up -d

# Access services
open http://localhost:8001  # Admin UI
```

This starts:
- PostgreSQL database (port 5432)
- MCP server (port 8080)
- Admin UI (port 8001)

## Documentation

- **[Setup Guide](docs/SETUP.md)** - Installation and configuration
- **[API Reference](docs/api.md)** - MCP tools and REST endpoints
- **[Development Guide](docs/DEVELOPMENT.md)** - Local development and contributing
- **[Testing Guide](docs/testing.md)** - Running and writing tests
- **[Deployment Guide](docs/deployment.md)** - Production deployment options
- **[Operations Guide](docs/OPERATIONS.md)** - Admin UI and monitoring
- **[Architecture](docs/ARCHITECTURE.md)** - System design and database schema
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

## Key Features

### For AI Agents
- **Product Discovery** - Natural language search for advertising products
- **Campaign Creation** - Automated media buying with targeting
- **Creative Management** - Upload and approval workflows
- **Performance Monitoring** - Real-time campaign metrics

### For Publishers
- **Multi-Tenant System** - Isolated data per publisher
- **Adapter Pattern** - Support for multiple ad servers
- **Admin Interface** - Web UI with Google OAuth
- **Audit Logging** - Complete operational history

### For Developers
- **MCP Protocol** - Standard interface for AI agents
- **A2A Protocol** - Agent-to-Agent communication via JSON-RPC 2.0
- **REST API** - Programmatic tenant management
- **Docker Deployment** - Easy local and production setup
- **Comprehensive Testing** - Unit, integration, and E2E tests

## Protocol Support

### MCP (Model Context Protocol)
The primary interface for AI agents to interact with the AdCP Sales Agent. Uses FastMCP with HTTP/SSE transport.

### A2A (Agent-to-Agent Protocol)
JSON-RPC 2.0 compliant server for agent-to-agent communication:
- **Endpoint**: `/a2a` (also available at port 8091)
- **Discovery**: `/.well-known/agent.json`
- **Authentication**: Bearer tokens via Authorization header
- **Library**: Built with standard `python-a2a` library

## Using the MCP Client

```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

# Connect to server
headers = {"x-adcp-auth": "your_token"}
transport = StreamableHttpTransport(
    url="http://localhost:8080/mcp/",
    headers=headers
)
client = Client(transport=transport)

# Discover products
async with client:
    products = await client.tools.get_products(
        brief="video ads for sports content"
    )

    # Create media buy
    result = await client.tools.create_media_buy(
        product_ids=["ctv_sports"],
        total_budget=50000,
        flight_start_date="2025-02-01",
        flight_end_date="2025-02-28"
    )
```

## Project Structure

```
salesagent/
├── src/                    # Source code
│   ├── core/              # Core MCP server components
│   │   ├── main.py        # MCP server implementation
│   │   ├── schemas.py     # API schemas and data models
│   │   ├── config_loader.py  # Configuration management
│   │   ├── audit_logger.py   # Security and audit logging
│   │   └── database/      # Database layer
│   │       ├── models.py  # SQLAlchemy models
│   │       ├── database.py # Database initialization
│   │       └── database_session.py # Session management
│   ├── services/          # Business logic services
│   │   ├── ai_product_service.py # AI product management
│   │   ├── targeting_capabilities.py # Targeting system
│   │   └── gam_inventory_service.py # GAM integration
│   ├── adapters/          # Ad server integrations
│   │   ├── base.py        # Base adapter interface
│   │   ├── google_ad_manager.py # GAM adapter
│   │   └── mock_ad_server.py # Mock adapter
│   └── admin/             # Admin UI (Flask)
│       ├── app.py         # Flask application
│       ├── blueprints/    # Flask blueprints
│       └── server.py      # Admin server
├── scripts/               # Utility scripts
│   ├── setup/            # Setup and initialization
│   ├── dev/              # Development tools
│   ├── ops/              # Operations scripts
│   └── deploy/           # Deployment scripts
├── tests/                # Test suite
│   ├── unit/            # Unit tests
│   ├── integration/     # Integration tests
│   └── e2e/             # End-to-end tests
├── docs/                 # Documentation
├── examples/             # Example code
├── tools/                # Demo and simulation tools
├── alembic/             # Database migrations
├── templates/           # Jinja2 templates
└── config/              # Configuration files
    └── fly/             # Fly.io deployment configs
```

## Requirements

- Python 3.12+
- Docker and Docker Compose (for easy deployment)
- PostgreSQL (production) or SQLite (development)
- Google OAuth credentials (for Admin UI)
- Gemini API key (for AI features)

## Contributing

We welcome contributions! Please see our [Development Guide](docs/DEVELOPMENT.md) for:
- Setting up your development environment
- Running tests
- Code style guidelines
- Creating pull requests

### Important: Database Access Patterns

When contributing, please follow our standardized database patterns:
```python
# ✅ CORRECT - Use context manager
from database_session import get_db_session
with get_db_session() as session:
    # Your database operations
    session.commit()

# ❌ WRONG - Manual management
conn = get_db_connection()
# operations
conn.close()  # Prone to leaks
```
See [Database Patterns Guide](docs/database-patterns.md) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/adcontextprotocol/salesagent/issues)
- **Discussions**: [GitHub Discussions](https://github.com/adcontextprotocol/salesagent/discussions)
- **Documentation**: [docs/](docs/)

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Related Projects

- [AdCP Specification](https://github.com/adcontextprotocol/adcp-spec) - Protocol specification
- [MCP SDK](https://github.com/modelcontextprotocol) - Model Context Protocol tools
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
