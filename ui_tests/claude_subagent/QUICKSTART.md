# Quick Start: Claude UI Testing Subagent

## 1. For Claude Desktop Users

### Add to Claude Desktop Config

1. Open Claude Desktop settings
2. Go to Developer → Edit Config
3. Add this configuration:

```json
{
  "mcpServers": {
    "ui-test-assistant": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "ui_test_server.py"
      ],
      "cwd": "ui_tests/claude_subagent",
      "env": {
        "PYTHONPATH": ".",
        "BASE_URL": "${BASE_URL:-http://localhost:8001}",
        "HEADLESS": "true"
      }
    }
  }
}
```

4. Restart Claude Desktop
5. Look for "ui-test-assistant" in the tools menu

### Test It Out

Ask Claude:
```
Using the ui-test-assistant tools, check the auth status and list available tests
```

## 2. For Command Line Users

### Start the Server

```bash
cd ui_tests/claude_subagent
./run_subagent.sh
```

### Use with Claude CLI

```bash
# Install Claude CLI if needed
pip install claude-cli

# Use with the subagent
claude --mcp-server http://localhost:8090 "Run the authentication tests"
```

## 3. First Tasks to Try

### Task 1: Check Environment
```
Check if the test environment is ready:
1. Check auth status
2. List available tests
3. Tell me what's configured
```

### Task 2: Run Basic Tests
```
Run the basic setup tests and show me the results
```

### Task 3: Create a Test
```
Create a simple test that verifies the admin dashboard loads correctly
```

### Task 4: Debug a Test
```
Run the login test with a visible browser and tell me what happens
```

## 4. Common Issues

### "No MCP server found"
- Make sure you restarted Claude Desktop after adding config
- Check the path in the config matches your setup

### "Cannot connect to localhost:8001"
- Ensure the Admin UI is running:
  ```bash
  docker ps | grep admin-ui
  ```

### "Authentication required"
- The test environment needs to be logged in
- Ask Claude to save the auth state first

## 5. Pro Tips

1. **Save Auth State First**
   ```
   Save the current auth state so tests run faster
   ```

2. **Use Visible Browser for Debugging**
   ```
   Run the failing test with headed=true so I can see what's happening
   ```

3. **Generate Page Objects**
   ```
   Create page objects for any new pages before writing tests
   ```

4. **Batch Test Runs**
   ```
   Run all smoke tests, then run regression tests if they pass
   ```

## 6. Example Workflow

Here's a complete workflow to demonstrate capabilities:

```
Hi Claude! I need help testing the tenant management feature. Please:

1. First, check if we're logged in
2. List tests related to tenant management  
3. Run those tests
4. If any fail, debug with visible browser
5. Generate any missing tests for full coverage
6. Create a summary report

Use the ui-test-assistant tools for this.
```

## 7. Advanced Usage

### Continuous Testing
```
Set up a test that runs every hour and notifies me of failures
```

### Test Generation from Requirements
```
Here are the requirements for our new feature [paste requirements].
Generate comprehensive UI tests to cover all scenarios.
```

### Visual Testing
```
Analyze the screenshots from the last test run and identify any UI issues
```

## Need Help?

The subagent includes built-in help:
```
Show me all available tools and what they do
```

Or check the full documentation:
- [README.md](README.md) - Detailed documentation
- [example_prompts.md](example_prompts.md) - More example prompts