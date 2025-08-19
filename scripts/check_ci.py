#!/usr/bin/env python3
"""Test CI database initialization locally with PostgreSQL."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def test_with_postgresql():
    """Test the CI database initialization with PostgreSQL using Docker."""
    print("🐘 Testing with PostgreSQL...")

    # Start a temporary PostgreSQL container
    container_name = "test-postgres-ci"

    # Check if container already exists
    check_cmd = f"docker ps -aq -f name={container_name}"
    existing = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)

    if existing.stdout.strip():
        print(f"Removing existing container {container_name}...")
        subprocess.run(f"docker rm -f {container_name}", shell=True)

    print("Starting PostgreSQL container...")
    docker_cmd = (
        f"docker run -d --name {container_name} "
        f"-e POSTGRES_USER=test_user "
        f"-e POSTGRES_PASSWORD=test_pass "
        f"-e POSTGRES_DB=test_db "
        f"-p 5433:5432 "  # Use 5433 to avoid conflicts
        f"postgres:15"
    )
    subprocess.run(docker_cmd, shell=True, check=True)

    # Wait for PostgreSQL to be ready
    print("Waiting for PostgreSQL to start...")
    time.sleep(5)

    # Set environment variables for PostgreSQL
    env = os.environ.copy()
    env.update({"DATABASE_URL": "postgresql://test_user:test_pass@localhost:5433/test_db", "DB_TYPE": "postgresql"})

    try:
        # Run the CI initialization script
        print("\nRunning init_database_ci.py with PostgreSQL...")
        result = subprocess.run([sys.executable, "init_database_ci.py"], env=env, capture_output=True, text=True)

        print("STDOUT:")
        print(result.stdout)
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        if result.returncode == 0:
            print("\n✅ PostgreSQL test passed!")
        else:
            print(f"\n❌ PostgreSQL test failed with exit code {result.returncode}")

    finally:
        # Clean up
        print(f"\nCleaning up container {container_name}...")
        subprocess.run(f"docker stop {container_name} && docker rm {container_name}", shell=True)


def test_with_sqlite():
    """Test the CI database initialization with SQLite."""
    print("📦 Testing with SQLite...")

    # Create a temporary directory for SQLite
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")

        # Set environment variables for SQLite
        env = os.environ.copy()
        env.update({"DATABASE_URL": f"sqlite:///{db_path}", "DB_TYPE": "sqlite"})

        # Run the CI initialization script
        print(f"\nRunning init_database_ci.py with SQLite at {db_path}...")
        result = subprocess.run([sys.executable, "init_database_ci.py"], env=env, capture_output=True, text=True)

        print("STDOUT:")
        print(result.stdout)
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        if result.returncode == 0:
            print("\n✅ SQLite test passed!")
        else:
            print(f"\n❌ SQLite test failed with exit code {result.returncode}")


def main():
    """Main test runner."""
    if not Path("init_database_ci.py").exists():
        print("❌ Error: init_database_ci.py not found in current directory")
        sys.exit(1)

    print("🧪 Testing CI database initialization locally...\n")

    # Test with SQLite first (simpler, no Docker required)
    test_with_sqlite()

    print("\n" + "=" * 60 + "\n")

    # Test with PostgreSQL if Docker is available
    docker_check = subprocess.run("docker --version", shell=True, capture_output=True)
    if docker_check.returncode == 0:
        test_with_postgresql()
    else:
        print("⚠️  Docker not available, skipping PostgreSQL test")
        print("   To test PostgreSQL, install Docker or manually set DATABASE_URL")


if __name__ == "__main__":
    main()
