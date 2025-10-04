#!/usr/bin/env python3
"""Check Wonderstruck tenant GAM configuration"""

from src.core.database.database_session import get_db_session
from src.core.database.models import AdapterConfig, Principal, Tenant

with get_db_session() as session:
    # Get tenant
    tenant = session.query(Tenant).filter_by(tenant_id="tenant_wonderstruck").first()
    if not tenant:
        print("❌ Wonderstruck tenant not found")
        exit(1)

    print(f"✅ Tenant: {tenant.name}")
    print(f"   Ad Server: {tenant.ad_server}")

    # Get adapter config
    adapter_config = session.query(AdapterConfig).filter_by(tenant_id="tenant_wonderstruck").first()
    if adapter_config:
        print("\n📋 Adapter Configuration:")
        print(f"   Adapter Type: {adapter_config.adapter_type}")
        print(f"   GAM Network Code: {adapter_config.gam_network_code or 'NOT SET'}")
        print(f"   GAM Company ID: {adapter_config.gam_company_id or 'NOT SET'}")
        print(f"   GAM Refresh Token: {'SET' if adapter_config.gam_refresh_token else 'NOT SET'}")
    else:
        print("\n❌ No adapter configuration found")

    # Get principal
    principal = session.query(Principal).filter_by(tenant_id="tenant_wonderstruck").first()
    if not principal:
        print("❌ No principal found for Wonderstruck")
        exit(1)

    print(f"\n✅ Principal: {principal.name}")
    print(f"   Principal ID: {principal.principal_id}")
    print(f"   Platform mappings: {principal.platform_mappings}")

    # Check GAM config in platform mappings
    gam_mappings = principal.platform_mappings.get("google_ad_manager", {}) if principal.platform_mappings else {}
    if gam_mappings:
        print("\n📋 Principal GAM Mappings:")
        print(f"   Network Code: {gam_mappings.get('network_code', 'NOT SET')}")
        print(f"   Advertiser ID: {gam_mappings.get('advertiser_id', 'NOT SET')}")
        print(f"   Trafficker ID: {gam_mappings.get('trafficker_id', 'NOT SET')}")
        print(f"   Refresh Token: {'SET' if gam_mappings.get('refresh_token') else 'NOT SET'}")
    else:
        print("\n⚠️  No GAM platform mappings in principal")
