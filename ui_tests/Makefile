.PHONY: install test test-auth test-tenant test-ops test-all clean report

# Install dependencies
install:
	pip install -r requirements.txt
	python run_tests.py --install-browsers

# Run all tests
test:
	python run_tests.py --headless

# Run specific test suites
test-auth:
	python run_tests.py tests/test_authentication.py --headless

test-tenant:
	python run_tests.py tests/test_tenant_management.py --headless

test-ops:
	python run_tests.py tests/test_operations_dashboard.py --headless

# Run tests with UI visible
test-headed:
	python run_tests.py --headed

# Run tests in parallel
test-parallel:
	python run_tests.py --headless -n 4

# Run tests with HTML report
test-report:
	python run_tests.py --headless --report
	@echo "Report generated at: reports/test_report.html"

# Run tests with Allure report
test-allure:
	python run_tests.py --headless --allure
	@echo "Allure report generated at: reports/allure-report/index.html"

# Run specific test by pattern
test-pattern:
	python run_tests.py -k "$(PATTERN)" --headless

# Debug mode with visible browser
debug:
	python run_tests.py --headed --debug -v

# Clean up test artifacts
clean:
	rm -rf reports/
	rm -rf screenshots/
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Run tests in CI environment
ci:
	python run_tests.py --headless --report --parallel 4

# Help
help:
	@echo "Available targets:"
	@echo "  install       - Install dependencies and Playwright browsers"
	@echo "  test          - Run all tests in headless mode"
	@echo "  test-auth     - Run authentication tests only"
	@echo "  test-tenant   - Run tenant management tests only"
	@echo "  test-ops      - Run operations dashboard tests only"
	@echo "  test-headed   - Run tests with browser UI visible"
	@echo "  test-parallel - Run tests in parallel (4 workers)"
	@echo "  test-report   - Run tests and generate HTML report"
	@echo "  test-allure   - Run tests and generate Allure report"
	@echo "  test-pattern  - Run tests matching pattern (use PATTERN=...)"
	@echo "  debug         - Run tests in debug mode with visible browser"
	@echo "  clean         - Remove test artifacts"
	@echo "  ci            - Run tests in CI mode"