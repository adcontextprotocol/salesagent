# Claude UI Testing Subagent

This subagent provides Claude with tools to write, run, and analyze UI tests for the AdCP Admin interface.

## Setup

### 1. Install Dependencies

```bash
cd /Users/brianokelley/Developer/salesagent/.conductor/phuket
uv sync --extra ui-tests
```

### 2. Configure Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

### 3. Start the MCP Server (Alternative)

If not using Claude Desktop, run the server directly:

```bash
cd ui_tests/claude_subagent
uv run python ui_test_server.py
```

## Available Tools

### 1. `list_ui_tests`
List all available UI tests in the test suite.

**Example:**
```
List all UI tests available
```

### 2. `run_ui_test`
Run specific UI tests and get results.

**Parameters:**
- `test_path`: Path to test (e.g., "tests/test_login.py")
- `headed`: Run with visible browser
- `verbose`: Verbose output
- `timeout`: Timeout in seconds

**Example:**
```
Run the login test with visible browser
```

### 3. `generate_ui_test`
Generate UI test code based on requirements.

**Parameters:**
- `feature_description`: What to test
- `test_type`: Type of test (functional, smoke, regression)
- `page_objects`: Page objects to use

**Example:**
```
Generate a test for creating a new tenant with admin privileges
```

### 4. `check_auth_status`
Check current authentication status.

**Example:**
```
Check if the test environment is logged in
```

### 5. `save_auth_state`
Save authentication state for test reuse.

**Example:**
```
Save the current authentication state
```

### 6. `analyze_screenshot`
Analyze screenshots from test failures.

**Parameters:**
- `screenshot_path`: Path to screenshot
- `description`: What to look for

**Example:**
```
Analyze the screenshot from the failed login test
```

### 7. `create_page_object`
Generate page object classes.

**Parameters:**
- `page_name`: Name of the page
- `elements`: Dictionary of element selectors
- `methods`: Methods to generate

**Example:**
```
Create a page object for the Products page with add, edit, and delete methods
```

### 8. `get_test_report`
Get the latest test execution report.

**Example:**
```
Show me the latest test report
```

## Example Prompts for Claude

### Basic Test Execution
```
Run all the authentication tests and tell me if they pass
```

### Test Creation
```
Create a comprehensive test suite for the tenant management feature. It should test:
1. Creating a new tenant
2. Editing tenant details
3. Deleting a tenant
4. Permission checks for non-admin users
```

### Debugging Failed Tests
```
The tenant creation test is failing. Run it with visible browser, analyze any screenshots, and suggest fixes.
```

### Page Object Creation
```
Create page objects for the Operations Dashboard with methods for filtering, exporting data, and checking metrics.
```

### Test Analysis
```
Check the current auth status, then run the smoke tests and give me a summary of what passes and fails.
```

## Best Practices

1. **Always check auth status first** - Many tests require authentication
2. **Use headed mode for debugging** - Helps see what's happening
3. **Save auth state** - Speeds up subsequent test runs
4. **Generate page objects** - Maintain clean test architecture
5. **Analyze screenshots** - Understand test failures

## Troubleshooting

### Authentication Issues
```
Check auth status and save the state if logged in
```

### Test Timeouts
```
Run the test with a longer timeout and headed mode
```

### Missing Elements
```
Generate a new page object with updated selectors
```

## Integration with CI/CD

The subagent can help set up CI/CD:

```
Generate a GitHub Actions workflow that runs the smoke tests on every PR
```

## Advanced Usage

### Custom Test Scenarios
```
Create a test that simulates a complete user journey:
1. Login as admin
2. Create a tenant
3. Add products
4. Configure targeting
5. Verify in operations dashboard
```

### Performance Testing
```
Create tests that measure page load times and generate a performance report
```

### Visual Regression
```
Set up visual regression tests that compare screenshots between test runs
```