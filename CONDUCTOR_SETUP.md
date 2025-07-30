# Conductor Workspace Setup Guide

This guide documents the setup process for Conductor workspace copies to ensure they work correctly with unique ports and configurations.

## Port Configuration

Each Conductor workspace requires unique ports to avoid conflicts. The ports are configured in the `.env` file:

```bash
# Server Ports (unique for this Conductor workspace)
POSTGRES_PORT=5433      # Default: 5432
ADCP_SALES_PORT=8081    # Default: 8080  
ADMIN_UI_PORT=8002      # Default: 8001
DATABASE_URL=postgresql://adcp_user:secure_password_change_me@localhost:5433/adcp
```

## Setup Steps for New Conductor Workspaces

1. **Fix Database Initialization Bug**
   - The `database.py` file has indentation issues where `principals_data` and `products_data` are only defined inside an `if` block but used outside it
   - Ensure the `for p in principals_data:` and `for p in products_data:` loops are properly indented inside the `if` block

2. **Copy Required Files from Root Workspace**
   ```bash
   # Copy OAuth credentials
   cp ../../client_secret_*.json .
   
   # Copy .env file and modify ports
   cp ../../.env .
   ```

3. **Configure Unique Ports**
   - Edit `.env` to set unique ports for this workspace
   - Suggested port allocation scheme:
     - Workspace 1: PostgreSQL 5433, MCP 8081, Admin 8002
     - Workspace 2: PostgreSQL 5434, MCP 8082, Admin 8003
     - etc.

4. **Docker Compose Configuration**
   - The `docker-compose.yml` file now uses environment variables for ports
   - No need to edit docker-compose.yml directly, just set the `.env` values

5. **Start Services**
   ```bash
   docker-compose build
   docker-compose up -d
   ```

## Verification

Check that all services are running:
```bash
docker-compose ps
```

Test endpoints:
- MCP Server: `curl http://localhost:8081/mcp/`
- Admin UI: `http://localhost:8002/`
- PostgreSQL: `psql -h localhost -p 5433 -U adcp_user -d adcp`

## Important Notes

1. **OAuth Redirect URI**: If using Google OAuth, ensure the redirect URI in Google Console matches your Admin UI port (e.g., `http://localhost:8002/auth/google/callback`)

2. **Database URL**: The DATABASE_URL in `.env` must match the POSTGRES_PORT setting

3. **Port Consolidation**: All port definitions are now in `.env` to avoid duplication and make configuration easier

## Automated Setup Script

Consider creating a script to automate this process:

```bash
#!/bin/bash
# setup_conductor_workspace.sh

WORKSPACE_NUM=$1
BASE_DIR="../.."

# Calculate ports based on workspace number
POSTGRES_PORT=$((5432 + $WORKSPACE_NUM))
ADCP_PORT=$((8080 + $WORKSPACE_NUM))
ADMIN_PORT=$((8001 + $WORKSPACE_NUM))

# Copy required files
cp $BASE_DIR/client_secret_*.json .
cp $BASE_DIR/.env .

# Update .env with unique ports
cat >> .env << EOF

# Server Ports (unique for Conductor workspace $WORKSPACE_NUM)
POSTGRES_PORT=$POSTGRES_PORT
ADCP_SALES_PORT=$ADCP_PORT
ADMIN_UI_PORT=$ADMIN_PORT
DATABASE_URL=postgresql://adcp_user:secure_password_change_me@localhost:$POSTGRES_PORT/adcp
EOF

# Fix database.py indentation issues
# (Add sed commands or Python script to fix indentation)

# Build and start
docker-compose build
docker-compose up -d
```

This ensures consistent setup across all Conductor workspaces.