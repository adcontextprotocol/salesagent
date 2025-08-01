#!/usr/bin/env python3
"""
UI Test Runner for AdCP Sales Agent Admin UI
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path

def install_playwright_browsers():
    """Install Playwright browsers if not already installed."""
    print("Installing Playwright browsers...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("Playwright browsers installed successfully.")

def run_tests(args):
    """Run UI tests with specified options."""
    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]
    
    # Add test directory or specific test file
    if args.test:
        cmd.append(args.test)
    else:
        cmd.append("tests/")
    
    # Add verbosity
    if args.verbose:
        cmd.append("-v")
    
    # Add specific test pattern
    if args.pattern:
        cmd.extend(["-k", args.pattern])
    
    # Add markers
    if args.marker:
        cmd.extend(["-m", args.marker])
    
    # Add parallel execution
    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])
    
    # Add report generation
    if args.report:
        cmd.extend(["--html=reports/test_report.html", "--self-contained-html"])
    
    # Add allure report
    if args.allure:
        cmd.extend(["--alluredir=reports/allure"])
    
    # Add screenshot on failure
    cmd.append("--screenshot=on")
    
    # Set environment variables
    env = os.environ.copy()
    env["HEADLESS"] = "true" if args.headless else "false"
    env["BASE_URL"] = args.base_url
    env["DEBUG"] = "true" if args.debug else "false"
    
    # Run tests
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)
    
    # Generate Allure report if requested
    if args.allure and result.returncode == 0:
        print("\nGenerating Allure report...")
        subprocess.run(["allure", "generate", "reports/allure", "-o", "reports/allure-report", "--clean"])
        print("Allure report generated at: reports/allure-report/index.html")
    
    return result.returncode

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run UI tests for AdCP Sales Agent Admin UI")
    
    parser.add_argument(
        "test",
        nargs="?",
        help="Specific test file or directory to run"
    )
    
    parser.add_argument(
        "-k", "--pattern",
        help="Run tests matching the given pattern"
    )
    
    parser.add_argument(
        "-m", "--marker",
        help="Run tests with specific marker"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run tests in headless mode (default: True)"
    )
    
    parser.add_argument(
        "--headed",
        action="store_false",
        dest="headless",
        help="Run tests with browser UI visible"
    )
    
    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Base URL for the application (default: http://localhost:8001)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with request/response logging"
    )
    
    parser.add_argument(
        "-n", "--parallel",
        type=int,
        help="Number of parallel workers"
    )
    
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate HTML test report"
    )
    
    parser.add_argument(
        "--allure",
        action="store_true",
        help="Generate Allure test report"
    )
    
    parser.add_argument(
        "--install-browsers",
        action="store_true",
        help="Install Playwright browsers"
    )
    
    args = parser.parse_args()
    
    # Create reports directory
    Path("reports").mkdir(exist_ok=True)
    Path("screenshots").mkdir(exist_ok=True)
    
    # Install browsers if requested
    if args.install_browsers:
        install_playwright_browsers()
        return 0
    
    # Run tests
    return run_tests(args)

if __name__ == "__main__":
    sys.exit(main())