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
        from db_config import get_db_connection
        import uuid
        
        print("Applying database migrations for CI...")
        run_migrations()
        print("Database migrations applied successfully")
        
        # Create a default tenant for CI tests
        print("Creating default tenant for CI...")
        conn = get_db_connection()
        try:
            tenant_id = str(uuid.uuid4())
            
            # Use database-appropriate timestamp function
            if conn.config['type'] == 'sqlite':
                timestamp_func = "datetime('now')"
            else:  # PostgreSQL
                timestamp_func = "CURRENT_TIMESTAMP"
            
            # Build query with proper timestamp function
            tenant_query = f"""
                INSERT INTO tenants (tenant_id, name, subdomain, config, billing_plan, created_at)
                VALUES (?, ?, ?, ?, ?, {timestamp_func})
            """
            conn.execute(tenant_query, (
                tenant_id,
                "CI Test Tenant",
                "ci-test",
                '{"adapters": {"mock": {"enabled": true}}, "features": {"max_daily_budget": 10000}, "creative_engine": {"auto_approve_formats": ["display_300x250", "display_728x90"]}}',
                "test"
            ))
            
            # Create a default principal for the tenant
            principal_id = str(uuid.uuid4())
            principal_query = f"""
                INSERT INTO principals (principal_id, tenant_id, name, access_token, platform_mappings, created_at)
                VALUES (?, ?, ?, ?, ?, {timestamp_func})
            """
            conn.execute(principal_query, (
                principal_id,
                tenant_id,
                "CI Test Principal",
                "ci-test-token",
                '{"mock": {"advertiser_id": "test-advertiser"}}'
            ))
            
            conn.connection.commit()
            print(f"Created default tenant (ID: {tenant_id}) and principal (ID: {principal_id})")
        finally:
            conn.close()
        
        print("Database initialized successfully")
    except ImportError as e:
        print(f"Import error: {e}")
        print(f"Python path: {sys.path}")
        print(f"Current directory: {os.getcwd()}")
        sys.exit(1)
    except Exception as e:
        print(f"Error during initialization: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    init_db_ci()