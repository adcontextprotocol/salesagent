#!/usr/bin/env python3
"""Comprehensive test runner for AdCP Sales Agent.

This script runs all tests in the correct order with proper setup.
Tests are grouped by category and dependencies are handled.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

# Test categories
TEST_CATEGORIES = {
    'unit': {
        'description': 'Unit tests with minimal dependencies',
        'tests': [
            'test_adapters.py',
            'test_adapter_targeting.py',
            'test_creative_format_parsing.py',
            'test_ai_parsing_improvements.py',
            'tests/unit/test_admin_ui_oauth.py',
        ]
    },
    'integration': {
        'description': 'Integration tests requiring database',
        'tests': [
            'test_main.py',
            'test_admin_creative_approval.py',
            'test_creative_auto_approval.py',
            'test_human_task_queue.py',
            'test_manual_approval.py',
            'test_task_verification.py',
            'test_auth.py',
        ]
    },
    'ai': {
        'description': 'AI-related tests (requires GEMINI_API_KEY for full tests)',
        'tests': [
            'test_ai_product_features.py',
            'test_product_catalog_providers.py',
        ]
    },
    'parsing': {
        'description': 'Creative parsing tests',
        'tests': [
            'simple_parsing_test.py',
            'test_nytimes_parsing.py',
        ]
    }
}

def run_command(cmd, env=None, check=True):
    """Run a command and return success status."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True)
    
    if result.returncode != 0 and check:
        print(f"Error: {result.stderr}")
        return False
    
    print(result.stdout)
    if result.stderr and result.returncode != 0:
        print(f"Errors: {result.stderr}")
    
    return result.returncode == 0

def setup_test_environment():
    """Set up test environment variables."""
    env = os.environ.copy()
    
    # Default test database
    if 'DATABASE_URL' not in env:
        env['DATABASE_URL'] = 'sqlite:///test_adcp.db'
    
    # Set testing mode
    env['TESTING'] = 'true'
    env['CI'] = 'true'
    
    # Dummy values for required env vars
    if 'GEMINI_API_KEY' not in env:
        print("⚠️  Warning: GEMINI_API_KEY not set - AI tests will be limited")
        env['GEMINI_API_KEY'] = 'test_key_for_mocking'
    
    # OAuth test credentials
    env['GOOGLE_CLIENT_ID'] = 'test_client_id'
    env['GOOGLE_CLIENT_SECRET'] = 'test_client_secret'
    env['SUPER_ADMIN_EMAILS'] = 'test@example.com'
    
    return env

def run_tests(categories, verbose=False, failfast=False):
    """Run tests for specified categories."""
    env = setup_test_environment()
    
    # Clean up any existing test database
    if 'sqlite' in env['DATABASE_URL']:
        db_file = env['DATABASE_URL'].replace('sqlite:///', '')
        if os.path.exists(db_file):
            os.remove(db_file)
    
    failed_tests = []
    passed_tests = []
    
    # Build pytest command
    pytest_opts = ['-v'] if verbose else []
    if failfast:
        pytest_opts.append('-x')
    
    # Add coverage options
    pytest_opts.extend(['--cov=.', '--cov-report=html', '--cov-report=term'])
    
    for category in categories:
        if category not in TEST_CATEGORIES:
            print(f"❌ Unknown test category: {category}")
            continue
        
        print(f"\n{'='*60}")
        print(f"Running {category} tests: {TEST_CATEGORIES[category]['description']}")
        print('='*60)
        
        for test_file in TEST_CATEGORIES[category]['tests']:
            if not os.path.exists(test_file):
                print(f"⚠️  Test file not found: {test_file}")
                continue
            
            # Special handling for AI tests without API key
            if category == 'ai' and 'GEMINI_API_KEY' not in os.environ:
                cmd = f"pytest {test_file} {' '.join(pytest_opts)} -k 'not test_ai_integration'"
            else:
                cmd = f"pytest {test_file} {' '.join(pytest_opts)}"
            
            if run_command(cmd, env=env, check=False):
                passed_tests.append(test_file)
            else:
                failed_tests.append(test_file)
                if failfast:
                    break
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)
    print(f"✅ Passed: {len(passed_tests)} tests")
    print(f"❌ Failed: {len(failed_tests)} tests")
    
    if failed_tests:
        print("\nFailed tests:")
        for test in failed_tests:
            print(f"  - {test}")
    
    return len(failed_tests) == 0

def main():
    parser = argparse.ArgumentParser(description='Run AdCP test suite')
    parser.add_argument(
        'categories', 
        nargs='*', 
        default=['unit', 'integration', 'ai', 'parsing'],
        help='Test categories to run (default: all)'
    )
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-x', '--failfast', action='store_true', help='Stop on first failure')
    parser.add_argument('--list', action='store_true', help='List available test categories')
    
    args = parser.parse_args()
    
    if args.list:
        print("Available test categories:")
        for cat, info in TEST_CATEGORIES.items():
            print(f"  {cat}: {info['description']}")
            for test in info['tests']:
                print(f"    - {test}")
        return
    
    # Install test dependencies if needed
    print("Checking test dependencies...")
    deps = ['pytest', 'pytest-cov', 'pytest-mock', 'pytest-asyncio']
    for dep in deps:
        result = subprocess.run(f"python3 -c 'import {dep.replace('-', '_')}'", 
                              shell=True, capture_output=True)
        if result.returncode != 0:
            print(f"Installing {dep}...")
            run_command(f"pip install {dep}")
    
    # Run tests
    success = run_tests(args.categories, args.verbose, args.failfast)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()