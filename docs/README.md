# AdCP Sales Agent Server Documentation

This directory contains documentation for running and extending the AdCP Sales Agent reference server implementation.

## Documentation Structure

### Implementation Guides
- **[Server Setup](server-setup.md)**: Installation and configuration guide
- **[Adapter Development](adapter-development.md)**: How to create new ad server adapters
- **[Platform Mapping Guide](platform-mapping-guide.md)**: How AdCP concepts map to platforms
- **[Targeting Implementation](targeting-implementation.md)**: Targeting capabilities and examples
- **[Configuration Guide](configuration.md)**: Detailed configuration options
- **[API Testing](api-testing.md)**: How to test the API endpoints
- **[Deployment Guide](deployment.md)**: Production deployment instructions

## Quick Links

- **AdCP Protocol Specification**: See the `adcp-spec/` directory
- **Main README**: See the root `README.md` for quick start
- **Example Config**: See `config.json.sample`

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐
│   AI Agent      │────▶│  AdCP Sales Agent│
└─────────────────┘     └──────────────────┘
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
         ┌──────────────┐ ┌────────┐ ┌──────────────┐
         │ Google Ad    │ │ Kevel  │ │ Triton       │
         │ Manager      │ │        │ │ Digital      │
         └──────────────┘ └────────┘ └──────────────┘
```

The server provides a unified MCP interface that abstracts away platform differences.