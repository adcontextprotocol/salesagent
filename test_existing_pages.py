#!/usr/bin/env python3
"""Test all EXISTING Admin UI pages to ensure no 500 errors."""

import requests
import sys
from urllib.parse import urljoin

BASE_URL = "http://localhost:8004"
TENANT_ID = "default"

# Track results
errors_found = []
pages_tested = 0
pages_ok = 0

def test_page(session, path, description):
    """Test a single page for 500 errors."""
    global pages_tested, pages_ok
    
    url = urljoin(BASE_URL, path)
    print(f"Testing: {description:<50}", end=" ")
    pages_tested += 1
    
    try:
        response = session.get(url, timeout=10)
        
        if response.status_code == 500:
            print(f"❌ 500 ERROR!")
            errors_found.append({
                "page": description,
                "path": path,
                "error": extract_error(response.text)
            })
            return False
            
        elif response.status_code == 200:
            # Check for error text in HTML
            error_indicators = [
                "UndefinedColumn", "UndefinedTable", "Internal Server Error",
                "AttributeError", "KeyError", "TypeError", "ValueError",
                "psycopg2.errors", "sqlalchemy.exc"
            ]
            
            for indicator in error_indicators:
                if indicator in response.text:
                    print(f"❌ Error in HTML: {indicator}")
                    errors_found.append({
                        "page": description,
                        "path": path,
                        "error": f"Error indicator in HTML: {indicator}"
                    })
                    return False
            
            print(f"✅ OK")
            pages_ok += 1
            return True
            
        else:
            # Non-500 status is OK for this test
            print(f"✔️  {response.status_code}")
            pages_ok += 1
            return True
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        errors_found.append({
            "page": description,
            "path": path,
            "error": str(e)
        })
        return False

def extract_error(html):
    """Extract error message from HTML."""
    import re
    
    # Try to find specific database errors
    patterns = [
        r'column "([^"]+)" does not exist',
        r'relation "([^"]+)" does not exist',
        r'(psycopg2\.errors\.\w+:[^<]+)',
        r'(AttributeError:[^<]+)',
        r'(KeyError:[^<]+)',
        r'(TypeError:[^<]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(0)
    
    return "Unknown error"

def main():
    """Test all existing pages."""
    
    print(f"\n{'='*70}")
    print("TESTING EXISTING ADMIN UI PAGES FOR 500 ERRORS")
    print(f"{'='*70}\n")
    
    # Create session
    session = requests.Session()
    
    # Authenticate
    print("Authenticating...", end=" ")
    auth_data = {
        "email": "test_super_admin@example.com",
        "password": "test123",
        "tenant_id": ""
    }
    
    response = session.post(f"{BASE_URL}/test/auth", json=auth_data)
    if response.status_code in [200, 302]:
        print("✅\n")
    else:
        print(f"❌ Failed: {response.status_code}")
        sys.exit(1)
    
    # Test existing pages based on grep results
    print("TESTING PAGES:")
    print("-" * 70)
    
    pages_to_test = [
        # Main pages
        ("/", "Root"),
        ("/health", "Health Check"),
        ("/login", "Login"),
        (f"/tenant/{TENANT_ID}/login", "Tenant Login"),
        (f"/tenant/{TENANT_ID}", "Dashboard"),
        (f"/tenant/{TENANT_ID}/settings", "Settings Main"),
        
        # Settings sections
        (f"/tenant/{TENANT_ID}/settings/general", "Settings: General"),
        (f"/tenant/{TENANT_ID}/settings/ad_server", "Settings: Ad Server"),
        (f"/tenant/{TENANT_ID}/settings/products", "Settings: Products"),
        (f"/tenant/{TENANT_ID}/settings/formats", "Settings: Formats"),
        (f"/tenant/{TENANT_ID}/settings/advertisers", "Settings: Advertisers"),
        (f"/tenant/{TENANT_ID}/settings/integrations", "Settings: Integrations"),
        (f"/tenant/{TENANT_ID}/settings/tokens", "Settings: Tokens"),
        (f"/tenant/{TENANT_ID}/settings/users", "Settings: Users"),
        (f"/tenant/{TENANT_ID}/settings/advanced", "Settings: Advanced"),
        
        # Products
        (f"/tenant/{TENANT_ID}/products", "Products List"),
        (f"/tenant/{TENANT_ID}/products/add", "Add Product"),
        (f"/tenant/{TENANT_ID}/products/add/ai", "Add Product with AI"),
        (f"/tenant/{TENANT_ID}/products/bulk", "Bulk Upload"),
        (f"/tenant/{TENANT_ID}/products/templates", "Product Templates"),
        (f"/tenant/{TENANT_ID}/products/templates/browse", "Browse Templates"),
        (f"/tenant/{TENANT_ID}/products/setup-wizard", "Setup Wizard"),
        
        # Users
        (f"/tenant/{TENANT_ID}/users", "Users Management"),
        
        # Other tenant pages
        (f"/tenant/{TENANT_ID}/targeting", "Targeting"),
        (f"/tenant/{TENANT_ID}/inventory", "Inventory"),
        (f"/tenant/{TENANT_ID}/orders", "Orders"),
        (f"/tenant/{TENANT_ID}/reporting", "Reporting"),
        (f"/tenant/{TENANT_ID}/workflows", "Workflows"),
        (f"/tenant/{TENANT_ID}/policy", "Policy"),
        (f"/tenant/{TENANT_ID}/creative-formats", "Creative Formats"),
        (f"/tenant/{TENANT_ID}/analyze-ad-server", "Analyze Ad Server"),
        
        # API endpoints
        (f"/api/tenant/{TENANT_ID}/products/suggestions", "API: Product Suggestions"),
        (f"/api/tenant/{TENANT_ID}/revenue-chart", "API: Revenue Chart"),
        (f"/api/tenant/{TENANT_ID}/sync/status", "API: Sync Status"),
        (f"/api/tenant/{TENANT_ID}/orders", "API: Orders"),
        (f"/api/tenant/{TENANT_ID}/gam/custom-targeting-keys", "API: GAM Targeting Keys"),
        
        # Test pages
        ("/test/login", "Test Login"),
        
        # Admin pages
        ("/settings", "Admin Settings"),
    ]
    
    for path, description in pages_to_test:
        test_page(session, path, description)
    
    # Print summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}\n")
    
    print(f"Pages tested: {pages_tested}")
    print(f"Pages OK: {pages_ok}")
    print(f"Errors found: {len(errors_found)}")
    
    if errors_found:
        print(f"\n❌ ERRORS DETECTED:\n")
        for error in errors_found:
            print(f"Page: {error['page']}")
            print(f"Path: {error['path']}")
            print(f"Error: {error['error']}")
            print("-" * 40)
        
        print(f"\n❌ {len(errors_found)} pages have 500 errors!")
        sys.exit(1)
    else:
        print("\n✅ NO 500 ERRORS FOUND - All existing pages work!")
        sys.exit(0)

if __name__ == "__main__":
    main()