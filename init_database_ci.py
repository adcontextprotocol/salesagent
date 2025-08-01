"""Minimal database initialization for CI/CD testing."""
import os
from migrate import run_migrations

def init_db_ci():
    """Initialize database with migrations only for CI testing."""
    print("Applying database migrations for CI...")
    run_migrations()
    print("Database initialized successfully")

if __name__ == "__main__":
    init_db_ci()