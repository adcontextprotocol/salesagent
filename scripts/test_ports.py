#!/usr/bin/env python3
"""
Centralized port configuration for all test modes.

This module provides a single source of truth for port assignments across:
- Local development (docker-compose)
- Integration tests (PostgreSQL container)
- E2E tests (full stack)
- CI/GitHub Actions

Port allocation strategy:
1. CI/GitHub Actions: Fixed ports (predictable, no .env file)
2. Local/Conductor: Read from .env (workspace isolation)
3. Tests: Use this module's get_ports() function

Usage:
    from scripts.test_ports import get_ports

    ports = get_ports()
    postgres_port = ports["postgres"]
    mcp_port = ports["mcp"]
"""

import os
import socket
from typing import TypedDict


class TestPorts(TypedDict):
    """Type definition for test port configuration."""

    postgres: int
    mcp: int
    a2a: int
    admin: int


# CI Mode: Fixed ports (used by GitHub Actions, no .env file)
CI_PORTS: TestPorts = {
    "postgres": 5433,  # Integration tests PostgreSQL container
    "mcp": 8092,  # E2E MCP server
    "a2a": 8094,  # E2E A2A server
    "admin": 8093,  # E2E Admin UI
}

# E2E Docker Compose: Separate ports to avoid conflicts with integration tests
E2E_DOCKER_PORTS: TestPorts = {
    "postgres": 5435,  # E2E PostgreSQL (inside docker-compose)
    "mcp": 8092,  # E2E MCP server (maps to container 8080)
    "a2a": 8094,  # E2E A2A server (maps to container 8091)
    "admin": 8093,  # E2E Admin UI (maps to container 8001)
}


def is_ci_mode() -> bool:
    """
    Detect if we're running in CI mode.

    CI mode indicators:
    - GITHUB_ACTIONS=true (GitHub Actions)
    - CI=true (generic CI environment)
    - No .env file present (CI doesn't use .env)

    Returns:
        True if running in CI environment, False otherwise
    """
    return os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check
        host: Host address to check (default: localhost)

    Returns:
        True if port is available, False if in use
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def get_ports(mode: str = "auto") -> TestPorts:
    """
    Get port configuration for tests.

    Port selection priority:
    1. Explicit environment variables (TEST_POSTGRES_PORT, etc.)
    2. CI mode detection → use CI_PORTS
    3. Conductor workspace → use .env ports (CONDUCTOR_* variables)
    4. Fallback → use CI_PORTS (safe defaults)

    Args:
        mode: Port mode to use:
            - "auto": Auto-detect based on environment (default)
            - "ci": Force CI ports (for run_all_tests.sh ci)
            - "e2e": Force E2E Docker Compose ports
            - "local": Force .env ports (Conductor workspace)

    Returns:
        TestPorts dict with postgres, mcp, a2a, admin ports

    Examples:
        # Auto-detect (recommended)
        ports = get_ports()

        # Force CI mode
        ports = get_ports(mode="ci")

        # Force E2E mode
        ports = get_ports(mode="e2e")
    """
    # Mode: ci - Use fixed CI ports
    if mode == "ci":
        return CI_PORTS.copy()

    # Mode: e2e - Use E2E Docker Compose ports
    if mode == "e2e":
        return E2E_DOCKER_PORTS.copy()

    # Mode: local - Force .env ports (Conductor workspace)
    if mode == "local":
        return _get_conductor_ports()

    # Mode: auto - Detect environment
    # 1. Check explicit test port environment variables
    if os.getenv("TEST_POSTGRES_PORT"):
        return {
            "postgres": int(os.getenv("TEST_POSTGRES_PORT", CI_PORTS["postgres"])),
            "mcp": int(os.getenv("TEST_MCP_PORT", CI_PORTS["mcp"])),
            "a2a": int(os.getenv("TEST_A2A_PORT", CI_PORTS["a2a"])),
            "admin": int(os.getenv("TEST_ADMIN_PORT", CI_PORTS["admin"])),
        }

    # 2. CI mode → use CI ports
    if is_ci_mode():
        return CI_PORTS.copy()

    # 3. Conductor workspace → use .env ports
    if os.getenv("CONDUCTOR_POSTGRES_PORT"):
        return _get_conductor_ports()

    # 4. Fallback → use CI ports (safe defaults)
    return CI_PORTS.copy()


def _get_conductor_ports() -> TestPorts:
    """
    Get ports from Conductor workspace .env file.

    Returns:
        TestPorts dict using CONDUCTOR_* environment variables
    """
    return {
        "postgres": int(os.getenv("CONDUCTOR_POSTGRES_PORT", os.getenv("POSTGRES_PORT", CI_PORTS["postgres"]))),
        "mcp": int(os.getenv("CONDUCTOR_MCP_PORT", os.getenv("ADCP_SALES_PORT", CI_PORTS["mcp"]))),
        "a2a": int(os.getenv("CONDUCTOR_A2A_PORT", os.getenv("A2A_PORT", CI_PORTS["a2a"]))),
        "admin": int(os.getenv("CONDUCTOR_ADMIN_PORT", os.getenv("ADMIN_UI_PORT", CI_PORTS["admin"]))),
    }


def get_database_url(mode: str = "auto", db_name: str = "adcp_test") -> str:
    """
    Get PostgreSQL database URL for tests.

    Args:
        mode: Port mode ("auto", "ci", "e2e", "local")
        db_name: Database name (default: adcp_test)

    Returns:
        PostgreSQL connection URL string

    Examples:
        # CI mode
        url = get_database_url(mode="ci")
        # postgresql://adcp_user:test_password@localhost:5433/adcp_test

        # Conductor workspace
        url = get_database_url(mode="local")
        # postgresql://adcp_user:test_password@localhost:5496/adcp_test
    """
    ports = get_ports(mode=mode)
    return f"postgresql://adcp_user:test_password@localhost:{ports['postgres']}/{db_name}"


def validate_ports(ports: TestPorts, check_availability: bool = False) -> list[str]:
    """
    Validate port configuration.

    Args:
        ports: TestPorts dict to validate
        check_availability: If True, check if ports are actually available

    Returns:
        List of validation error messages (empty if valid)

    Examples:
        ports = get_ports()
        errors = validate_ports(ports, check_availability=True)
        if errors:
            print("Port validation failed:", errors)
    """
    errors = []

    # Check for port conflicts (same port used for multiple services)
    port_values = list(ports.values())
    if len(port_values) != len(set(port_values)):
        errors.append("Port conflict detected: Multiple services assigned to same port")

    # Check port range (1024-65535 for non-root)
    for service, port in ports.items():
        if not (1024 <= port <= 65535):
            errors.append(f"{service} port {port} outside valid range (1024-65535)")

    # Check availability if requested
    if check_availability:
        for service, port in ports.items():
            if not is_port_available(port):
                errors.append(f"{service} port {port} is already in use")

    return errors


if __name__ == "__main__":
    import sys

    # CLI usage: python scripts/test_ports.py [mode]
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"

    print(f"Port Configuration (mode={mode}):")
    print()

    ports = get_ports(mode=mode)
    for service, port in ports.items():
        available = "✓" if is_port_available(port) else "✗ (in use)"
        print(f"  {service:10} {port:5}  {available}")

    print()
    print(f"Database URL: {get_database_url(mode=mode)}")
    print()

    # Validate ports
    errors = validate_ports(ports)
    if errors:
        print("❌ Validation errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print("✅ Port configuration valid")
