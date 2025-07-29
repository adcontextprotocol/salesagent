import json
import os
import secrets
from datetime import datetime
from db_config import get_db_connection, DatabaseConfig
from database_schema import get_schema

def init_db():
    """Initialize database with multi-tenant support."""
    db_config = DatabaseConfig.get_db_config()
    conn = get_db_connection()
    
    # Get the appropriate schema for this database type
    schema = get_schema(db_config['type'])
    
    # For PostgreSQL/MySQL, we need to execute statements one at a time
    if db_config['type'] in ['postgresql', 'mysql']:
        statements = [s.strip() for s in schema.split(';') if s.strip()]
        for statement in statements:
            try:
                conn.execute(statement)
            except Exception as e:
                # Ignore errors for indexes that already exist
                if 'already exists' not in str(e).lower():
                    print(f"Warning executing statement: {e}")
    else:
        # SQLite can handle multiple statements
        conn.connection.executescript(schema)
    
    # Check if we need to create a default tenant
    cursor = conn.execute("SELECT COUNT(*) FROM tenants")
    tenant_count = cursor.fetchone()[0]
    
    if tenant_count == 0:
        # No tenants exist - create a default one for simple use case
        admin_token = secrets.token_urlsafe(32)
        api_token = secrets.token_urlsafe(32)
        
        default_config = {
            "adapters": {
                "mock": {
                    "enabled": True,
                    "dry_run": False
                }
            },
            "creative_engine": {
                "auto_approve_formats": ["display_300x250", "display_728x90", "video_30s"],
                "human_review_required": False
            },
            "features": {
                "max_daily_budget": 10000,
                "enable_aee_signals": True
            },
            "admin_token": admin_token
        }
        
        # Create default tenant
        conn.execute("""
            INSERT INTO tenants (
                tenant_id, name, subdomain, config,
                created_at, updated_at, is_active, billing_plan
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "default",
            "Default Publisher",
            "localhost",  # Works with localhost:8080
            json.dumps(default_config),
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            True,  # Boolean works for both SQLite and PostgreSQL
            "standard"
        ))
        
        # Don't create any principals by default - tenants should create them after setting up their ad server
        
        # Only create sample advertisers if this is a development environment
        if os.environ.get('CREATE_SAMPLE_DATA', 'false').lower() == 'true':
            principals_data = [
            {
                "principal_id": "acme_corp",
                "name": "Acme Corporation",
                "platform_mappings": {
                    "gam_advertiser_id": 67890,
                    "kevel_advertiser_id": "acme-corporation",
                    "triton_advertiser_id": "ADV-ACM-002",
                    "mock_advertiser_id": "mock-acme"
                },
                "access_token": "acme_corp_token"
            },
            {
                "principal_id": "purina",
                "name": "Purina Pet Foods",
                "platform_mappings": {
                    "gam_advertiser_id": 12345,
                    "kevel_advertiser_id": "purina-pet-foods",
                    "triton_advertiser_id": "ADV-PUR-001",
                    "mock_advertiser_id": "mock-purina"
                },
                "access_token": "purina_token"
            }
        ]
        
        for p in principals_data:
            conn.execute("""
                INSERT INTO principals (
                    tenant_id, principal_id, name,
                    platform_mappings, access_token
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                "default",
                p["principal_id"],
                p["name"],
                json.dumps(p["platform_mappings"]),
                p["access_token"]
            ))
        
            # Create sample products
            products_data = [
            {
                "product_id": "prod_1",
                "name": "Premium Display - News",
                "description": "Premium news site display inventory",
                "formats": [{
                    "format_id": "display_300x250",
                    "name": "Medium Rectangle",
                    "type": "display",
                    "description": "Standard medium rectangle display ad",
                    "specs": {"width": 300, "height": 250},
                    "delivery_options": {"hosted": {}}
                }],
                "targeting_template": {
                    "content_cat_any_of": ["news", "politics"],
                    "geo_country_any_of": ["US"]
                },
                "delivery_type": "guaranteed",
                "is_fixed_price": False,
                "cpm": None,
                "price_guidance": {
                    "floor": 5.0,
                    "p50": 8.0,
                    "p75": 10.0
                }
            },
            {
                "product_id": "prod_2",
                "name": "Run of Site Display",
                "description": "Run of site display inventory",
                "formats": [{
                    "format_id": "display_728x90",
                    "name": "Leaderboard",
                    "type": "display",
                    "description": "Standard leaderboard display ad",
                    "specs": {"width": 728, "height": 90},
                    "delivery_options": {"hosted": {}}
                }],
                "targeting_template": {
                    "geo_country_any_of": ["US", "CA"]
                },
                "delivery_type": "non_guaranteed",
                "is_fixed_price": True,
                "cpm": 2.5,
                "price_guidance": None
            }
        ]
        
        for p in products_data:
            conn.execute("""
                INSERT INTO products (
                    tenant_id, product_id, name, description,
                    formats, targeting_template, delivery_type,
                    is_fixed_price, cpm, price_guidance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "default",
                p["product_id"],
                p["name"],
                p["description"],
                json.dumps(p["formats"]),
                json.dumps(p["targeting_template"]),
                p["delivery_type"],
                p["is_fixed_price"],  # Boolean works for both
                p.get("cpm"),
                json.dumps(p["price_guidance"]) if p.get("price_guidance") else None
            ))
        
        # Update the print statement based on whether sample data was created
        if os.environ.get('CREATE_SAMPLE_DATA', 'false').lower() == 'true':
            print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                 🚀 ADCP SALES AGENT INITIALIZED                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  A default tenant has been created for quick start:              ║
║                                                                  ║
║  🏢 Tenant: Default Publisher                                    ║
║  🌐 URL: http://localhost:8080                                   ║
║                                                                  ║
║  🔑 Admin Token (x-adcp-auth header):                            ║
║     {admin_token}  ║
║                                                                  ║
║  👤 Sample Advertiser Tokens:                                    ║
║     • Acme Corp: acme_corp_token                                 ║
║     • Purina: purina_token                                       ║
║                                                                  ║
║  💡 To create additional tenants:                                ║
║     python setup_tenant.py "Publisher Name"                      ║
║                                                                  ║
║  📚 To use with a different tenant:                              ║
║     http://[subdomain].localhost:8080                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
            """)
        else:
            print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                 🚀 ADCP SALES AGENT INITIALIZED                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  A default tenant has been created for quick start:              ║
║                                                                  ║
║  🏢 Tenant: Default Publisher                                    ║
║  🌐 Admin UI: http://localhost:8001/tenant/default/login         ║
║                                                                  ║
║  🔑 Admin Token (for legacy API access):                         ║
║     {admin_token}  ║
║                                                                  ║
║  ⚡ Next Steps:                                                  ║
║     1. Log in to the Admin UI                                    ║
║     2. Set up your ad server (Ad Server Setup tab)              ║
║     3. Create principals for your advertisers                    ║
║                                                                  ║
║  💡 To create additional tenants:                                ║
║     python setup_tenant.py "Publisher Name"                      ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
            """)
    else:
        print(f"Database ready ({tenant_count} tenant(s) configured)")
    
    conn.connection.commit()
    conn.close()

if __name__ == "__main__":
    init_db()