# Conductor Port Reservation System

This system manages a predefined pool of ports for Conductor workspaces to avoid constantly updating Google OAuth redirect URIs.

## Prerequisites

Before using Conductor workspaces, set these environment variables in your shell:

```bash
# Required for Admin UI access
export SUPER_ADMIN_EMAILS='your-email@example.com'

# Optional - allows any user from these domains
export SUPER_ADMIN_DOMAINS='example.com,company.com'

# Required for creative generation features
export GEMINI_API_KEY='your-gemini-api-key'

# Required for Google OAuth login
export GOOGLE_CLIENT_ID='your-client-id.apps.googleusercontent.com'
export GOOGLE_CLIENT_SECRET='your-client-secret'
```

Add these to your `~/.bashrc` or `~/.zshrc` to make them permanent:

```bash
# AdCP Conductor Configuration
export SUPER_ADMIN_EMAILS='bokelley@scope3.com'
export GEMINI_API_KEY='your-key-here'
export GOOGLE_CLIENT_ID='your-id-here'
export GOOGLE_CLIENT_SECRET='your-secret-here'
```

## Setup

1. **Configure Google OAuth**: Add all the redirect URLs to your Google OAuth app:
   ```bash
   python manage_conductor_ports.py oauth-urls
   ```

   This will output 10 redirect URLs:
   - http://localhost:8002/callback
   - http://localhost:8003/callback
   - http://localhost:8004/callback
   - ... through port 8011

2. **Add these URLs to Google OAuth Console**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Navigate to your OAuth 2.0 Client ID
   - Add all 10 redirect URIs under "Authorized redirect URIs"
   - Save changes

## Usage

### Automatic Port Reservation

When you create a new Conductor workspace, the `setup_conductor_workspace.sh` script will automatically:
1. Reserve an available port set from the pool
2. Configure the workspace to use those ports
3. Update the `.env` file with the assigned ports

### Manual Port Management

```bash
# List all current port reservations
python manage_conductor_ports.py list

# Manually reserve ports for a workspace
python manage_conductor_ports.py reserve my-workspace

# Release ports when done
python manage_conductor_ports.py release my-workspace

# Get OAuth URLs for Google configuration
python manage_conductor_ports.py oauth-urls
```

## Port Pool

The system manages 10 predefined port sets:

| Set | PostgreSQL | MCP Server | Admin UI |
|-----|------------|------------|----------|
| 1   | 5433       | 8081       | 8002     |
| 2   | 5434       | 8082       | 8003     |
| 3   | 5435       | 8083       | 8004     |
| 4   | 5436       | 8084       | 8005     |
| 5   | 5437       | 8085       | 8006     |
| 6   | 5438       | 8086       | 8007     |
| 7   | 5439       | 8087       | 8008     |
| 8   | 5440       | 8088       | 8009     |
| 9   | 5441       | 8089       | 8010     |
| 10  | 5442       | 8090       | 8011     |

## Configuration

The port configuration is stored in `conductor_ports.json`:
- `available_port_sets`: List of all port sets
- `reserved_ports`: Current reservations by workspace name

## Integration with Conductor

1. **Workspace Creation**: `setup_conductor_workspace.sh` automatically reserves ports
2. **Workspace Cleanup**: `cleanup_conductor_workspace.sh` releases ports
3. **Fallback**: If port reservation fails, falls back to hash-based port assignment

## Benefits

1. **No more OAuth updates**: Once configured, all workspaces use pre-approved ports
2. **Predictable ports**: Know exactly which ports are in use
3. **Automatic management**: Ports are reserved/released automatically
4. **Conflict prevention**: File locking prevents port conflicts
5. **Easy monitoring**: See all port usage with one command

## Troubleshooting

### All ports are reserved
If you get "No available port sets!" error:
1. List current reservations: `python manage_conductor_ports.py list`
2. Release unused workspaces: `python manage_conductor_ports.py release <workspace>`
3. Consider adding more port sets to `conductor_ports.json`

### Port conflicts
If you have port conflicts:
1. Check what's using the port: `lsof -i :8002`
2. Stop conflicting services
3. Use the cleanup script to properly release ports

### OAuth still failing
Make sure:
1. All 10 redirect URIs are added to Google OAuth
2. The URIs match exactly (including http:// prefix)
3. You've saved changes in Google Cloud Console
4. The OAuth client ID/secret are correctly configured
