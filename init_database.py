import json
import os
import secrets
from datetime import datetime
from db_config import get_db_connection
from migrate import run_migrations

def init_db(exit_on_error=False):
    """Initialize database with migrations and populate default data.
    
    Args:
        exit_on_error: If True, exit process on migration error. If False, raise exception.
                      Default False for test compatibility.
    """
    # Run migrations first
    print("Applying database migrations...")
    run_migrations(exit_on_error=exit_on_error)
    
    # Now populate default data if needed
    conn = get_db_connection()
    
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
                tenant_id, name, subdomain,
                created_at, updated_at, is_active, billing_plan,
                ad_server, max_daily_budget, enable_aee_signals,
                admin_token, human_review_required, auto_approve_formats
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "default",
            "Default Publisher",
            "localhost",  # Works with localhost:8080
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            True,  # Boolean works for both SQLite and PostgreSQL
            "standard",
            "mock",  # ad_server
            10000,  # max_daily_budget
            True,  # enable_aee_signals
            admin_token,  # admin_token
            True,  # human_review_required
            json.dumps(["display_300x250", "display_728x90", "display_320x50"])  # auto_approve_formats
        ))
        
        # Create adapter config for mock adapter
        conn.execute("""
            INSERT INTO adapter_config (
                tenant_id, adapter_type, mock_dry_run
            ) VALUES (?, ?, ?)
        """, (
            "default",
            "mock",
            False
        ))
        
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
                },
                "implementation_config": {
                    "placement_ids": ["news_300x250_atf", "news_300x250_btf"],
                    "ad_unit_path": "/1234/news/display",
                    "key_values": {"section": "news", "tier": "premium"},
                    "targeting": {
                        "content_cat_any_of": ["news", "politics"],
                        "geo_country_any_of": ["US"]
                    }
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
                "price_guidance": None,
                "implementation_config": {
                    "placement_ids": ["ros_728x90_all"],
                    "ad_unit_path": "/1234/run_of_site/leaderboard",
                    "key_values": {"tier": "standard"},
                    "targeting": {
                        "geo_country_any_of": ["US", "CA"]
                    }
                }
            }
            ]
            
            for p in products_data:
                conn.execute("""
                    INSERT INTO products (
                        tenant_id, product_id, name, description,
                        formats, targeting_template, delivery_type,
                        is_fixed_price, cpm, price_guidance, implementation_config
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(p["price_guidance"]) if p.get("price_guidance") else None,
                    json.dumps(p.get("implementation_config")) if p.get("implementation_config") else None
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
    init_db(exit_on_error=True)