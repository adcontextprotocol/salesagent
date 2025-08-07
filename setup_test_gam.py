#!/usr/bin/env python3
"""
Setup script for GAM testing environment.

This script creates:
1. Test tenant with GAM adapter configured
2. Test principal with advertiser mapping
3. Simple display product with proper GAM configuration
4. Validates all settings

Run with: python setup_test_gam.py --network-code YOUR_NETWORK --key-file PATH_TO_KEY
"""

import argparse
import json
import sys
import uuid
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from database import db_session, init_db
from models import Tenant, Principal, Product

console = Console()


def create_test_tenant(network_code: str, key_file: str, company_id: str, trafficker_id: str) -> Tenant:
    """Create or update test tenant for GAM."""
    console.print("\n[bold]Creating Test Tenant[/bold]")
    
    # Check if tenant exists
    tenant = db_session.query(Tenant).filter_by(name="GAM Test Publisher").first()
    
    if tenant:
        console.print("[yellow]Test tenant already exists, updating configuration...[/yellow]")
    else:
        tenant = Tenant(
            tenant_id=f"gam_test_{uuid.uuid4().hex[:8]}",
            name="GAM Test Publisher",
            subdomain="gamtest"
        )
    
    # Update configuration
    tenant.config = {
        "adapters": {
            "google_ad_manager": {
                "enabled": True,
                "network_code": network_code,
                "service_account_key_file": str(key_file),
                "company_id": company_id,
                "trafficker_id": trafficker_id,
                "manual_approval_required": False
            }
        },
        "creative_engine": {
            "auto_approve_formats": ["display_300x250", "display_728x90"],
            "human_review_required": False
        },
        "features": {
            "max_daily_budget": 10000,
            "enable_aee_signals": True
        }
    }
    
    if not tenant.billing_plan:
        tenant.billing_plan = {
            "type": "test",
            "commission_rate": 0.15
        }
    
    db_session.add(tenant)
    db_session.commit()
    
    console.print(f"✅ Tenant created/updated: {tenant.tenant_id}")
    return tenant


def create_test_principal(tenant_id: str, advertiser_id: str) -> Principal:
    """Create test principal with GAM mapping."""
    console.print("\n[bold]Creating Test Principal[/bold]")
    
    # Check if principal exists
    principal = db_session.query(Principal).filter_by(
        tenant_id=tenant_id,
        name="Test Advertiser"
    ).first()
    
    if principal:
        console.print("[yellow]Test principal already exists, updating mapping...[/yellow]")
    else:
        principal = Principal(
            tenant_id=tenant_id,
            principal_id=f"test_principal_{uuid.uuid4().hex[:8]}",
            name="Test Advertiser",
            access_token=f"test_token_{uuid.uuid4().hex}"
        )
    
    # Update platform mapping
    principal.platform_mappings = {
        "gam": {
            "advertiser_id": advertiser_id
        }
    }
    
    db_session.add(principal)
    db_session.commit()
    
    console.print(f"✅ Principal created/updated: {principal.principal_id}")
    console.print(f"   Access token: {principal.access_token}")
    return principal


def create_test_product(tenant_id: str, ad_unit_ids: list, placement_ids: list = None) -> Product:
    """Create simple display test product."""
    console.print("\n[bold]Creating Test Product[/bold]")
    
    # Check if product exists
    product = db_session.query(Product).filter_by(
        tenant_id=tenant_id,
        name="Simple Display Test"
    ).first()
    
    if product:
        console.print("[yellow]Test product already exists, updating configuration...[/yellow]")
    else:
        product = Product(
            tenant_id=tenant_id,
            product_id=f"display_test_{uuid.uuid4().hex[:8]}",
            name="Simple Display Test",
            description="Test product for simple display campaigns"
        )
    
    # Update product configuration
    product.formats = ["display_300x250", "display_728x90"]
    product.targeting_template = {
        "geo_country_allow": ["US", "CA"],
        "device_type_allow": ["desktop", "mobile", "tablet"],
        "media_type_allow": ["display"]
    }
    product.pricing = {
        "model": "cpm",
        "value": 5.0,  # $5 CPM for testing
        "currency": "USD"
    }
    product.delivery_type = "non_guaranteed"
    product.is_pmp = False
    product.countries = ["US", "CA"]
    
    # GAM-specific implementation config
    product.implementation_config = {
        "order_name_template": "TEST-{po_number}-{timestamp}",
        "line_item_type": "STANDARD",
        "priority": 8,
        "cost_type": "CPM",
        "creative_rotation_type": "EVEN",
        "delivery_rate_type": "EVENLY",
        "primary_goal_type": "LIFETIME",
        "primary_goal_unit_type": "IMPRESSIONS",
        "creative_placeholders": [
            {
                "width": 300,
                "height": 250,
                "expected_creative_count": 1,
                "is_native": False
            },
            {
                "width": 728,
                "height": 90,
                "expected_creative_count": 1,
                "is_native": False
            }
        ],
        "targeted_ad_unit_ids": ad_unit_ids,
        "targeted_placement_ids": placement_ids or [],
        "include_descendants": True,
        "frequency_caps": [
            {
                "max_impressions": 3,
                "time_unit": "DAY",
                "time_range": 1
            }
        ],
        "environment_type": "BROWSER",
        "allow_overbook": False,
        "skip_inventory_check": False
    }
    
    db_session.add(product)
    db_session.commit()
    
    console.print(f"✅ Product created/updated: {product.product_id}")
    return product


def validate_setup(tenant: Tenant, principal: Principal, product: Product, key_file: Path) -> bool:
    """Validate the test setup."""
    console.print("\n[bold]Validating Setup[/bold]")
    
    errors = []
    
    # Check key file exists
    if not key_file.exists():
        errors.append(f"Service account key file not found: {key_file}")
    else:
        console.print("✅ Service account key file exists")
    
    # Check tenant config
    gam_config = tenant.config.get("adapters", {}).get("google_ad_manager", {})
    if not gam_config.get("enabled"):
        errors.append("GAM adapter not enabled in tenant config")
    else:
        console.print("✅ GAM adapter enabled")
    
    # Check principal mapping
    if not principal.platform_mappings.get("gam", {}).get("advertiser_id"):
        errors.append("Principal missing GAM advertiser_id mapping")
    else:
        console.print("✅ Principal has GAM mapping")
    
    # Check product config
    if not product.implementation_config.get("targeted_ad_unit_ids"):
        errors.append("Product missing targeted ad unit IDs")
    else:
        console.print("✅ Product has ad unit targeting")
    
    if errors:
        console.print("\n[red]Validation errors:[/red]")
        for error in errors:
            console.print(f"  ❌ {error}")
        return False
    
    return True


def print_test_instructions(tenant: Tenant, principal: Principal, product: Product):
    """Print instructions for running tests."""
    console.print("\n" + "="*60)
    console.print(Panel(
        "[bold green]GAM Test Environment Setup Complete![/bold green]\n\n"
        "Test environment details:\n"
        f"  Tenant ID: {tenant.tenant_id}\n"
        f"  Principal ID: {principal.principal_id}\n"
        f"  Product ID: {product.product_id}\n"
        f"  Access Token: {principal.access_token}\n\n"
        "To run tests:\n"
        "1. Start the server: python run_server.py\n"
        "2. Run dry-run test: python test_gam_simple_display.py --dry-run\n"
        "3. Run live test: python test_gam_simple_display.py\n\n"
        "To test with curl:\n"
        f'curl -X POST {{"http://localhost:8080/mcp/"}} \\\n'
        f'  -H "x-adcp-auth: {principal.access_token}" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"method": "get_products", "params": {}}\''
    ))


def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(
        description="Setup GAM test environment for AdCP Sales Agent"
    )
    parser.add_argument(
        "--network-code",
        required=True,
        help="Google Ad Manager network code"
    )
    parser.add_argument(
        "--key-file",
        required=True,
        type=Path,
        help="Path to service account JSON key file"
    )
    parser.add_argument(
        "--company-id",
        required=True,
        help="GAM company ID for the test advertiser"
    )
    parser.add_argument(
        "--trafficker-id",
        required=True,
        help="GAM user ID for trafficking operations"
    )
    parser.add_argument(
        "--advertiser-id",
        required=True,
        help="GAM advertiser ID to map to test principal"
    )
    parser.add_argument(
        "--ad-unit-ids",
        required=True,
        nargs="+",
        help="GAM ad unit IDs to target (space-separated)"
    )
    parser.add_argument(
        "--placement-ids",
        nargs="*",
        help="Optional GAM placement IDs to target (space-separated)"
    )
    
    args = parser.parse_args()
    
    # Validate key file
    if not args.key_file.exists():
        console.print(f"[red]Error: Service account key file not found: {args.key_file}[/red]")
        sys.exit(1)
    
    console.print(Panel.fit(
        "[bold cyan]GAM Test Environment Setup[/bold cyan]\n"
        "This will create a test tenant, principal, and product for GAM testing",
        border_style="cyan"
    ))
    
    # Confirm setup
    console.print("\n[bold]Configuration Summary:[/bold]")
    console.print(f"  Network Code: {args.network_code}")
    console.print(f"  Key File: {args.key_file}")
    console.print(f"  Company ID: {args.company_id}")
    console.print(f"  Trafficker ID: {args.trafficker_id}")
    console.print(f"  Advertiser ID: {args.advertiser_id}")
    console.print(f"  Ad Unit IDs: {', '.join(args.ad_unit_ids)}")
    if args.placement_ids:
        console.print(f"  Placement IDs: {', '.join(args.placement_ids)}")
    
    if not Confirm.ask("\nProceed with setup?"):
        console.print("[yellow]Setup cancelled[/yellow]")
        sys.exit(0)
    
    try:
        # Initialize database
        init_db()
        
        # Create test entities
        tenant = create_test_tenant(
            args.network_code,
            args.key_file,
            args.company_id,
            args.trafficker_id
        )
        
        principal = create_test_principal(
            tenant.tenant_id,
            args.advertiser_id
        )
        
        product = create_test_product(
            tenant.tenant_id,
            args.ad_unit_ids,
            args.placement_ids
        )
        
        # Validate setup
        if validate_setup(tenant, principal, product, args.key_file):
            print_test_instructions(tenant, principal, product)
        else:
            console.print("\n[red]Setup completed with errors. Please fix the issues above.[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"\n[red]Setup failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()