# Quickstart: Docker (Local)

**Time: 2 minutes** | **Difficulty: Easy** | **Cost: Free**

Run the AdCP Sales Agent locally with Docker. This is the fastest way to evaluate or develop.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

## Steps

### 1. Download and Start (30 seconds)

```bash
curl -O https://raw.githubusercontent.com/adcontextprotocol/salesagent/main/docker-compose.yml
docker compose up -d
```

### 2. Verify It's Running

```bash
curl http://localhost:8000/health
```

You should see `{"status": "healthy"}`.

### 3. Access the Admin UI

Open http://localhost:8000/admin

**Test credentials:**
- Email: `test_super_admin@example.com`
- Password: `test123`

## What You Get

- **Admin UI** at http://localhost:8000/admin
- **MCP Server** at http://localhost:8000/mcp/
- **A2A Server** at http://localhost:8000/a2a
- **PostgreSQL** database (managed by Docker)
- **Demo tenant** with mock adapter and sample data

## Test the MCP Interface

```bash
# List available tools
uvx adcp http://localhost:8000/mcp/ --auth test-token list_tools

# Search for products
uvx adcp http://localhost:8000/mcp/ --auth test-token get_products '{"brief":"video"}'
```

## Configuration

### Add Your Email as Admin

Edit `.env` file (create if needed):

```bash
SUPER_ADMIN_EMAILS=your-email@example.com
```

Then restart:
```bash
docker compose down && docker compose up -d
```

### Add Google OAuth (Optional)

For production-like authentication:

```bash
# .env
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

Add `http://localhost:8000/auth/google/callback` to your OAuth redirect URIs.

### Add Gemini API Key (Optional)

For AI-powered creative review:

```bash
# .env
GEMINI_API_KEY=your-gemini-key
```

## Common Commands

```bash
# View logs
docker compose logs -f

# Stop services
docker compose down

# Reset everything (including database)
docker compose down -v

# Rebuild after code changes
docker compose build && docker compose up -d
```

## Troubleshooting

### Container won't start

```bash
docker compose logs adcp-server | head -50
```

### Port 8000 already in use

```bash
# Find what's using it
lsof -i :8000

# Use a different port
PORT=9000 docker compose up -d
```

### Database issues

```bash
# Reset the database
docker compose down -v
docker compose up -d
```

## Next Steps

- **Production deployment**: See [Fly.io Guide](quickstart-fly.md) or [Cloud Run Guide](quickstart-cloud-run.md)
- **Configure GAM**: See [GAM Adapter Guide](adapters/gam.md)
- **Full documentation**: See [Deployment Guide](deployment.md)
