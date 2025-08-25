# A2A CLI Evaluation and Recommendations

## Summary

After researching alternatives to `a2a-cli` and evaluating the current setup, we recommend **keeping `a2a-cli`** but using workarounds for its current bug.

## Current Status

### What's Working
✅ Official `a2a-server` library with ChukAgent implementation (`src/a2a/adcp_agent.py`)
✅ Configuration via `.a2a_config.json`
✅ Custom server.py removed to avoid confusion
✅ Wrapper script created (`a2a_cli_wrapper.py`) as workaround

### Known Issues
⚠️ **a2a-cli bug**: The `--server` flag is ignored in the `send` command due to missing context parameter
⚠️ **Production deployment**: Still running old custom FastAPI server (needs deployment update)

## CLI Options Evaluated

### 1. a2a-cli (Current Choice) ⭐ RECOMMENDED
- **Status**: Has a bug but fixable
- **Features**: Rich UI, streaming, chat mode, best feature set
- **Author**: Same as a2a-server (chrishayuk)
- **Fix**: Simple one-line fix needed in cli.py

### 2. ALI-A2A-CLI
- **Status**: Repository appears private/deleted (404 error)
- **Features**: Unknown - cannot access
- **Verdict**: Not viable

### 3. Custom Python Client
- **Status**: Possible but unnecessary overhead
- **Features**: Would need to build from scratch
- **Verdict**: Too much work for little benefit

### 4. Direct curl/httpx
- **Status**: Working (our test scripts prove this)
- **Features**: Basic but reliable
- **Verdict**: Good for testing, not for daily use

## Workaround Solution

Use the provided `a2a_cli_wrapper.py` script which implements correct server handling:

```bash
# Get agent info
uv run python a2a_cli_wrapper.py info --server https://adcp-sales-agent.fly.dev/a2a

# Send a query
uv run python a2a_cli_wrapper.py send --server https://adcp-sales-agent.fly.dev/a2a "What products are available?" --wait

# Interactive chat
uv run python a2a_cli_wrapper.py chat --server https://adcp-sales-agent.fly.dev/a2a

# Run test suite
uv run python a2a_cli_wrapper.py test --server https://adcp-sales-agent.fly.dev/a2a
```

## The a2a-cli Bug

The bug is in `/path/to/a2a_cli/cli.py` line ~179:

```python
# BROKEN CODE (missing context)
@app.command()
def send(
    text: str = typer.Argument(...),
    prefix: str | None = typer.Option(None),
    wait: bool = typer.Option(False),
    color: bool = typer.Option(True),
):
    base = _resolve_base(prefix)  # Ignores --server flag!

# FIXED CODE
@app.command()
def send(
    ctx: typer.Context,  # ADD THIS
    text: str = typer.Argument(...),
    prefix: str | None = typer.Option(None),
    wait: bool = typer.Option(False),
    color: bool = typer.Option(True),
):
    base = ctx.obj["base"] or _resolve_base(prefix)  # Use server flag!
```

## Long-term Actions

1. **Report bug** to https://github.com/chrishayuk/a2a-cli/issues
2. **Consider forking** a2a-cli and fixing the bug if not addressed
3. **Continue using wrapper** until official fix is released

## Architecture Notes

### Official a2a-server Setup
- Uses `ChukAgent` base class from `a2a_server.tasks.handlers.chuk.chuk_agent`
- Configuration in `.a2a_config.json`
- Agent implementation in `src/a2a/adcp_agent.py`
- Started via `python -m a2a_server --config .a2a_config.json`

### Local Development
- Docker Compose runs MCP (8080) and Admin UI (8001)
- A2A server NOT included in local Docker setup
- Use production server for A2A testing

### Production (Fly.io)
- All services run via `scripts/deploy/run_all_services.py`
- Nginx proxy routes: `/mcp`, `/admin`, `/a2a`
- Needs deployment to switch from custom to official a2a-server

## Conclusion

The `a2a-cli` remains the best choice despite its current bug. The wrapper script provides a working solution, and the underlying `a2a-server` with ChukAgent is properly implemented. Once the production server is updated to use the official a2a-server code, the full A2A protocol stack will be operational.
