# UI Tests

This directory contains UI tests for the AdCP Admin interface.

## Test Authentication Mode

The `test_auth_mode.py` file tests the authentication bypass mode for automated testing.

### Running the Tests

1. Enable test mode:
   ```bash
   export ADCP_AUTH_TEST_MODE=true
   ```

2. Start services with test mode enabled:
   ```bash
   # Copy override file if not already done
   cp docker-compose.override.example.yml docker-compose.override.yml
   
   # Edit override file to enable test mode
   # Then start services
   docker-compose up
   ```

3. Run the tests:
   ```bash
   uv run pytest tests/ui/test_auth_mode.py -v
   ```

### Test Users

- `test_super_admin@example.com` / `test123` - Full admin access
- `test_tenant_admin@example.com` / `test123` - Tenant admin
- `test_tenant_user@example.com` / `test123` - Tenant user

**WARNING**: Never enable test mode in production!