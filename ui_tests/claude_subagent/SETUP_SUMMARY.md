# Claude UI Testing Subagent - Setup Summary

## What's Been Created

### 1. MCP Server (`ui_test_server.py`)
A FastMCP server that provides Claude with tools to:
- List available UI tests
- Run specific tests with options
- Generate test code
- Check authentication status
- Save/load auth state
- Analyze screenshots
- Create page objects
- Get test reports

### 2. Configuration Files
- `claude_mcp_config.json` - MCP configuration for Claude Desktop
- `run_subagent.sh` - Bash script to start the server

### 3. Documentation
- `README.md` - Comprehensive documentation
- `QUICKSTART.md` - Quick start guide
- `example_prompts.md` - Example prompts for Claude
- `SETUP_SUMMARY.md` - This file

### 4. Test Scripts
- `test_subagent.py` - Tests MCP tool functionality
- `test_direct.py` - Direct component testing

## Setup Instructions

### For Claude Desktop

1. **Add to Claude Desktop Config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ui-test-assistant": {
      "command": "uv",
      "args": ["run", "python", "ui_test_server.py"],
      "cwd": "/Users/brianokelley/Developer/salesagent/.conductor/phuket/ui_tests/claude_subagent",
      "env": {
        "PYTHONPATH": "/Users/brianokelley/Developer/salesagent/.conductor/phuket",
        "BASE_URL": "http://localhost:8001",
        "HEADLESS": "true"
      }
    }
  }
}
```

2. **Restart Claude Desktop**

3. **Test It Works**:
   - Open Claude Desktop
   - Look for "ui-test-assistant" in available tools
   - Try: "Using ui-test-assistant, check the auth status"

### For Command Line

1. **Start the Server**:
```bash
cd /Users/brianokelley/Developer/salesagent/.conductor/phuket/ui_tests/claude_subagent
./run_subagent.sh
```

2. **Server runs on port 8090**

## How Claude Can Use It

### Basic Usage
```
Hey Claude, using the ui-test-assistant tools:
1. Check if we're logged in
2. List all available tests
3. Run the basic setup tests
```

### Test Creation
```
Claude, please create a comprehensive test suite for the product management feature using the ui-test-assistant tools.
```

### Debugging
```
The tenant creation test is failing. Use ui-test-assistant to run it with visible browser and analyze what's wrong.
```

### Test Maintenance
```
Review all existing tests and suggest improvements using the ui-test-assistant tools.
```

## Key Features

1. **Authentication Handling**
   - Check current auth status
   - Save/load auth state
   - Work with existing sessions

2. **Test Execution**
   - Run tests headless or with visible browser
   - Capture screenshots
   - Get detailed results

3. **Code Generation**
   - Generate test code from descriptions
   - Create page objects
   - Follow best practices

4. **Analysis**
   - Analyze test failures
   - Review screenshots
   - Generate reports

## Important Notes

1. **The Admin UI must be running** at http://localhost:8001
2. **Authentication is required** for most tests (already logged in as dev@example.com)
3. **Tests use saved auth state** at test_auth_state.json
4. **Screenshots are saved** in ui_tests/screenshots/

## Troubleshooting

### "Tools not available"
- Make sure you restarted Claude Desktop
- Check the MCP server is in the config

### "Cannot connect to localhost:8001"
- Ensure Docker containers are running
- Check `docker ps | grep admin-ui`

### "Authentication failed"
- The session may have expired
- Manually login and save auth state again

## Next Steps

1. **Try Example Prompts** - See `example_prompts.md`
2. **Create Custom Tests** - Claude can generate tests for your features
3. **Set Up CI/CD** - Claude can create GitHub Actions workflows
4. **Extend Functionality** - Add more tools as needed

The subagent is ready to help Claude write, run, and maintain UI tests!