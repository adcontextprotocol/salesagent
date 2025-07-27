# AdCP:Buy Server - Claude Agent Notes

## Project Overview

This is a Python-based reference implementation of the Advertising Campaign Protocol (AdCP) V2.3 buy-side server. It demonstrates how publishers expose advertising inventory to AI-driven clients through a standardized protocol.

The server provides:
- Natural language brief processing for campaign recommendations
- Multi-tenant principal-based authentication
- Adapter pattern for multiple ad server integrations (GAM, Kevel, Triton, Mock)
- Full campaign lifecycle simulation with realistic budget pacing
- Dry-run mode with detailed API call logging

## Key Architecture Decisions

### 1. Principal-Based Multi-Tenancy
- Each client (principal) has a unique `principal_id` and bearer token
- Principals have adapter-specific mappings (e.g., GAM advertiser ID)
- All operations are scoped to the authenticated principal
- Data isolation is enforced at the API level

### 2. Adapter Pattern for Ad Servers
- Base `AdServerAdapter` class defines the interface
- Implementations for GAM, Kevel, Triton, and Mock
- Each adapter handles its own API call logging in dry-run mode
- Principal object encapsulates identity and adapter mappings

### 3. FastMCP Integration
- Uses FastMCP for the server framework
- HTTP transport with header-based authentication (`x-adcp-auth`)
- Context parameter provides access to HTTP request headers
- Tools are exposed as MCP methods

## Core Components

### `main.py` - Server Implementation
- FastMCP server exposing AdCP tools
- Authentication via `x-adcp-auth` header
- Principal resolution and adapter instantiation
- In-memory state management for media buys

### `schemas.py` - Data Models
- Pydantic models for all API contracts
- `Principal` model with `get_adapter_id()` method
- Request/Response models for all operations
- Adapter-specific response models

### `adapters/` - Ad Server Integrations
- `base.py`: Abstract base class defining the interface
- `mock_ad_server.py`: Mock implementation with realistic simulation
- `google_ad_manager.py`: GAM integration with detailed API logging
- Each adapter accepts a `Principal` object for cleaner architecture

### `simulation_full.py` - Full Lifecycle Test
- 7-phase campaign simulation (discovery → completion)
- Realistic timeline with proper date progression
- Performance tracking and optimization
- Demonstrates all API capabilities

## Recent Major Changes

### Principal Object Refactoring (Latest)
- Created `Principal` model to encapsulate identity and mappings
- Refactored all adapters to accept Principal instead of separate IDs
- Moved dry-run logging from main.py to individual adapters
- Added detailed API call logging for debugging

### Command-Line Interface
- `--dry-run`: Enable dry-run mode to see API calls without execution
- `--adapter`: Select ad server adapter (mock, gam, kevel, triton)
- `--simulation`: Choose simulation type (full, auth)

### Budget Simulation Fix
- Fixed date handling to use simulation dates not current time
- Implemented realistic budget pacing (daily variance, proper accumulation)
- Fixed media buy ID generation to use PO numbers

## Testing Strategy

### 1. Unit Tests (`test_adapters.py`)
- Test adapter interfaces and base functionality
- Verify Principal object behavior
- Schema validation tests

### 2. Integration Tests (`simulation_full.py`)
- Full end-to-end campaign lifecycle
- Tests all API operations in sequence
- Verifies state management and data flow

### 3. Dry-Run Testing (`demo_dry_run.py`)
- Demonstrates adapter-specific API logging
- Shows exact calls that would be made in production
- Useful for debugging integrations

## Configuration

### Environment Variables
- `PRODUCTION`: Disable sample data in database (default: false)
- `ADCP_SALES_PORT`: Server port (default: 8000)
- `ADCP_SALES_HOST`: Server host (default: 0.0.0.0)
- `GEMINI_API_KEY`: Google Gemini API key (if using AI features)
- `AD_SERVER_ADAPTER`: Select ad server adapter
- `AD_SERVER_BASE_URL`: Ad server API base URL
- `AD_SERVER_AUTH_TOKEN`: Ad server authentication token

### Database (`database.py`)
- SQLite database with principals and products tables
- Sample data includes two principals (purina, acme_corp)
- Platform mappings for each adapter
- Bearer tokens for authentication

### Production Architecture
- **Principals in Database**: All buyer credentials stored in SQLite, not environment variables
- **One Ad Server per Agent**: Each deployment connects to exactly one upstream ad server
- **Secrets**: Only ad server credentials (GAM service account, Triton API key, etc.)
- **Platform Mappings**: Each principal has adapter-specific IDs stored in database

## Common Operations

### Running the Server
```bash
python run_server.py
```

### Running Simulations
```bash
# Full lifecycle with mock adapter
python run_simulation.py

# Dry-run with GAM adapter
python run_simulation.py --dry-run --adapter gam
```

### Testing Specific Features
```bash
# Demo dry-run capabilities
python demo_dry_run.py
```

## Debugging Tips

1. **Authentication Issues**: Check x-adcp-auth header and token in database
2. **Adapter Errors**: Enable dry-run mode to see exact API calls
3. **Budget Issues**: Check MockAdServer delivery calculations
4. **Date Issues**: Ensure simulation uses proper dates, not datetime.now()

## Future Enhancements

See TODO.txt for planned features including:
- Batch operations for better performance
- Creative grouping across ad servers
- Human-in-the-loop capabilities
- Asynchronous request handling
- Additional adapter implementations