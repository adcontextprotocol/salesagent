#!/usr/bin/env python3
"""
Simple A2A server startup script that bypasses migration issues.
"""

import uvicorn
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from a2a_facade import create_a2a_facade

def start_a2a_server(host: str = "0.0.0.0", port: int = 8090):
    """Start just the A2A server."""
    
    print(f"Starting A2A server at http://{host}:{port}/")
    print(f"  - Agent Card: http://{host}:{port}/.well-known/agent-card.json")
    print(f"  - RPC endpoint: http://{host}:{port}/rpc")
    
    # Initialize database (simple version without migrations)
    try:
        # Try to init DB without migrations
        from db_config import get_db_connection
        from datetime import datetime
        import json
        
        db_conn = get_db_connection()
        conn = db_conn.connection
        
        # Quick check if test data exists
        cursor = conn.execute("SELECT 1 FROM tenants WHERE tenant_id = 'test' LIMIT 1")
        if not cursor.fetchone():
            # Create minimal test data
            now = datetime.utcnow().isoformat()
            
            # Insert test tenant with all required fields (no config column anymore)
            conn.execute("""
                INSERT OR IGNORE INTO tenants (
                    tenant_id, name, subdomain, ad_server, 
                    max_daily_budget, enable_aee_signals,
                    authorized_emails, authorized_domains,
                    admin_token, auto_approve_formats,
                    human_review_required, is_active,
                    slack_webhook_url, slack_audit_webhook_url, hitl_webhook_url,
                    policy_settings,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "test", "Test Publisher", "test", "mock",
                10000, True,
                '["test@example.com"]', '["example.com"]',
                "admin_token_123", '["display_300x250"]',
                False, True,
                None, None, None,  # webhook URLs
                None,  # policy_settings
                now, now
            ))
            
            # Insert test principal
            conn.execute("""
                INSERT OR IGNORE INTO principals (
                    tenant_id, principal_id, name, access_token, platform_mappings
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                "test", "test_principal", "Test Advertiser",
                "test_token_123", '{}'
            ))
            
            # Insert test product with proper schema
            conn.execute("""
                INSERT OR IGNORE INTO products (
                    tenant_id, product_id, name, description,
                    formats, targeting_template, delivery_type,
                    is_fixed_price, cpm, price_guidance,
                    is_custom
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "test", "prod_001", "Display Banner",
                "Standard display banner ad",
                '[{"format_id": "display_300x250", "creative_type": "display"}, {"format_id": "display_728x90", "creative_type": "display"}]',
                '{}', "guaranteed",  # Changed from "standard" to "guaranteed"
                True, 5.0, '{"floor": 3.0, "ceiling": 10.0}',  # Changed from min/max to floor/ceiling
                False
            ))
            
            conn.commit()
            print("✓ Created test data")
        
        db_conn.close()
        
    except Exception as e:
        print(f"Database init warning (non-critical): {e}")
    
    # Create A2A facade
    a2a_facade = create_a2a_facade()
    
    # Get the Starlette app
    app = a2a_facade.get_app()
    
    # Run with uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    start_a2a_server()