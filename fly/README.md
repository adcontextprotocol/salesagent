# Fly.io Deployment Files

This directory contains configuration and scripts for deploying AdCP Sales Agent to Fly.io.

## Files

- `supervisord.conf` - Process manager configuration to run both MCP server and Admin UI
- `setup-secrets.sh` - Script to configure Fly.io secrets from environment variables
- `setup-postgres.sh` - Script to create and attach PostgreSQL database
- `deploy.sh` - One-command deployment script
- `../Dockerfile.fly` - Optimized Dockerfile for Fly.io deployment
- `../fly.toml` - Fly.io application configuration

## Quick Start

1. Install Fly CLI and authenticate:
   ```bash
   brew install flyctl  # or see https://fly.io/docs/hands-on/install-flyctl/
   fly auth login
   ```

2. Configure your environment:
   ```bash
   cp .env.example .env
   # Edit .env with your values
   source .env
   ```

3. Deploy:
   ```bash
   ./fly/deploy.sh
   ```

4. Set secrets:
   ```bash
   ./fly/setup-secrets.sh
   ```

5. Initialize database (first time only):
   ```bash
   fly ssh console -C "cd /app && python init_database.py"
   ```

See [docs/fly-deployment.md](../docs/fly-deployment.md) for detailed instructions.