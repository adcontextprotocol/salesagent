"""Minimal database initialization for CI/CD testing."""
import os
import sys
from pathlib import Path

# Add the current directory to Python path to ensure imports work
sys.path.insert(0, str(Path(__file__).parent))

def init_db_ci():
    """Initialize database with migrations only for CI testing."""
    try:
        # Import here to ensure path is set up first
        from migrate import run_migrations
        
        print("Applying database migrations for CI...")
        run_migrations()
        print("Database initialized successfully")
    except ImportError as e:
        print(f"Import error: {e}")
        print(f"Python path: {sys.path}")
        print(f"Current directory: {os.getcwd()}")
        sys.exit(1)
    except Exception as e:
        print(f"Error during initialization: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_db_ci()