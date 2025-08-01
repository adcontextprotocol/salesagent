# Example Prompts for Claude UI Testing Subagent

## Getting Started

### 1. Check Test Environment
```
Check the authentication status of the test environment and list all available tests.
```

### 2. Run Basic Tests
```
Run the basic setup tests to verify the UI testing framework is working properly.
```

## Test Execution

### Run Specific Tests
```
Run the tenant management tests and show me any failures with screenshots.
```

### Debug Failed Tests
```
The login test is failing. Run it with a visible browser and analyze what's happening.
```

### Run Test Suites
```
Run all authentication tests first, then if they pass, run the tenant management tests.
```

## Test Creation

### Simple Test Generation
```
Create a test that verifies the logout functionality works correctly.
```

### Complex Test Scenarios
```
Create a comprehensive test for the product management feature that:
1. Logs in as admin
2. Creates a new product with specific targeting
3. Edits the product pricing
4. Verifies the changes in the operations dashboard
5. Deletes the product
```

### Page Object Generation
```
Create page objects for:
1. Products page with CRUD operations
2. Operations dashboard with filtering and export
3. Creative management with upload and approval methods
```

## Test Maintenance

### Update Selectors
```
The tenant creation test is failing because selectors changed. Analyze the current page and update the test.
```

### Refactor Tests
```
Refactor the authentication tests to use the saved auth state for faster execution.
```

## Analysis and Reporting

### Test Results Analysis
```
Run all smoke tests and give me a summary report with:
- Pass/fail rate
- Failed test details
- Screenshots of failures
- Recommendations for fixes
```

### Coverage Analysis
```
Analyze which features have test coverage and which need tests written.
```

## CI/CD Integration

### GitHub Actions
```
Create a GitHub Actions workflow that:
1. Runs on every PR
2. Executes smoke tests first
3. If smoke tests pass, runs full regression suite
4. Posts results as PR comment
```

### Test Environment Setup
```
Create a script that sets up the test environment including:
1. Checking if services are running
2. Ensuring test data exists
3. Saving auth state
4. Running smoke tests to verify
```

## Advanced Scenarios

### Data-Driven Testing
```
Create parameterized tests for tenant creation that test:
- Different billing plans
- Various adapter configurations  
- Permission levels
- Invalid inputs for error handling
```

### Performance Testing
```
Create tests that measure and track:
1. Page load times
2. Time to complete common workflows
3. Resource usage during operations
```

### Accessibility Testing
```
Add accessibility checks to the existing tests to verify:
- Keyboard navigation
- Screen reader compatibility
- Color contrast
- Focus indicators
```

## Troubleshooting

### Environment Issues
```
The tests won't run. Check:
1. If the application is running
2. Authentication status
3. Port availability
4. Any error messages
Then provide steps to fix the issues.
```

### Flaky Tests
```
The operations dashboard test passes sometimes but fails others. 
Analyze the test, add proper waits, and make it more stable.
```

### Cross-Browser Testing
```
Modify the tenant creation test to run on Chrome, Firefox, and Safari, 
then compare the results.
```

## Best Practices Implementation

### Test Organization
```
Review the current test structure and suggest improvements for:
- Better test organization
- Shared fixtures
- Utility functions
- Test data management
```

### Error Handling
```
Add comprehensive error handling to all tests including:
- Screenshot on failure
- Detailed error messages
- Cleanup after failures
- Retry logic for flaky operations
```

## Reporting and Documentation

### Test Documentation
```
Generate documentation for all existing tests including:
- What each test covers
- Prerequisites
- Expected results
- Common failure reasons
```

### Executive Summary
```
Run the full test suite and create an executive summary with:
- Overall health score
- Critical issues found
- Recommended improvements
- Test execution trends
```