#!/usr/bin/env python3
"""Test inventory sync performance improvements."""
import os
import sys
from datetime import datetime

# Set up environment
os.environ.setdefault(
    "DATABASE_URL", "postgresql://adcp_user:secure_password_change_me@postgres:5432/adcp?sslmode=disable"
)
os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("SUPER_ADMIN_EMAILS", "test@example.com")
os.environ.setdefault("ENCRYPTION_KEY", "dummy")

sys.path.insert(0, "/app")

from googleads import ad_manager, oauth2
from sqlalchemy import select

from src.adapters.gam_inventory_discovery import GAMInventoryDiscovery
from src.core.database.database_session import get_db_session
from src.core.database.models import AdapterConfig, SyncJob
from src.services.gam_inventory_service import GAMInventoryService


def get_gam_client(tenant_id: str):
    """Create GAM client from database config."""
    with get_db_session() as session:
        stmt = select(AdapterConfig).where(AdapterConfig.tenant_id == tenant_id)
        config = session.scalars(stmt).first()

        if not config or not config.gam_refresh_token:
            print("❌ GAM credentials not configured")
            return None

        # Create OAuth2 client
        oauth2_client = oauth2.GoogleRefreshTokenClient(
            client_id=os.environ.get("GAM_OAUTH_CLIENT_ID"),
            client_secret=os.environ.get("GAM_OAUTH_CLIENT_SECRET"),
            refresh_token=config.gam_refresh_token,
        )

        # Create GAM client
        client = ad_manager.AdManagerClient(
            oauth2_client, "AdCP Sales Agent Test", network_code=config.gam_network_code
        )

        return client


def test_incremental_sync(tenant_id: str = "default"):
    """Test incremental sync performance."""
    print("=" * 60)
    print("🧪 Testing Incremental Sync Performance")
    print("=" * 60)

    # Get last successful sync time
    with get_db_session() as session:
        stmt = (
            select(SyncJob)
            .where(SyncJob.tenant_id == tenant_id, SyncJob.sync_type == "inventory", SyncJob.status == "completed")
            .order_by(SyncJob.completed_at.desc())
        )

        last_sync = session.scalars(stmt).first()
        last_sync_time = last_sync.completed_at if last_sync else None

        if last_sync_time:
            print(f"📅 Last successful sync: {last_sync_time}")
            print(f"   Testing incremental sync (changes since {last_sync_time})")
        else:
            print("📅 No previous sync found - will do full sync")

    # Get GAM client
    print("\n🔐 Authenticating with GAM...")
    client = get_gam_client(tenant_id)
    if not client:
        return False

    print("✅ GAM authentication successful")

    # Initialize discovery
    print("\n🔍 Starting inventory discovery...")
    discovery = GAMInventoryDiscovery(client=client, tenant_id=tenant_id)

    start_time = datetime.now()

    # Discover ad units
    print("\n📦 Phase 1: Discovering ad units...")
    phase_start = datetime.now()
    ad_units = discovery.discover_ad_units(since=last_sync_time)
    phase_duration = (datetime.now() - phase_start).total_seconds()
    print(f"   Found {len(ad_units)} ad units in {phase_duration:.2f}s")

    # Discover placements
    print("\n📦 Phase 2: Discovering placements...")
    phase_start = datetime.now()
    placements = discovery.discover_placements(since=last_sync_time)
    phase_duration = (datetime.now() - phase_start).total_seconds()
    print(f"   Found {len(placements)} placements in {phase_duration:.2f}s")

    # Discover labels
    print("\n📦 Phase 3: Discovering labels...")
    phase_start = datetime.now()
    labels = discovery.discover_labels(since=last_sync_time)
    phase_duration = (datetime.now() - phase_start).total_seconds()
    print(f"   Found {len(labels)} labels in {phase_duration:.2f}s")

    # Discover custom targeting
    print("\n📦 Phase 4: Discovering custom targeting...")
    phase_start = datetime.now()
    custom_targeting = discovery.discover_custom_targeting(fetch_values=False, since=last_sync_time)
    phase_duration = (datetime.now() - phase_start).total_seconds()
    total_keys = custom_targeting.get("total_keys", 0)
    print(f"   Found {total_keys} targeting keys in {phase_duration:.2f}s")

    # Discover audience segments
    print("\n📦 Phase 5: Discovering audience segments...")
    phase_start = datetime.now()
    audience_segments = discovery.discover_audience_segments(since=last_sync_time)
    phase_duration = (datetime.now() - phase_start).total_seconds()
    print(f"   Found {len(audience_segments)} audience segments in {phase_duration:.2f}s")

    discovery_duration = (datetime.now() - start_time).total_seconds()
    print(f"\n✅ Discovery completed in {discovery_duration:.2f}s")

    # Save to database
    print("\n💾 Phase 6: Saving to database (bulk operations)...")
    save_start = datetime.now()

    with get_db_session() as session:
        inventory_service = GAMInventoryService(session)
        inventory_service._save_inventory_to_db(tenant_id, discovery)

    save_duration = (datetime.now() - save_start).total_seconds()
    print(f"✅ Database save completed in {save_duration:.2f}s")

    total_duration = (datetime.now() - start_time).total_seconds()

    # Print summary
    print("\n" + "=" * 60)
    print("📊 Performance Summary")
    print("=" * 60)
    print(f"Discovery:     {discovery_duration:6.2f}s ({discovery_duration/total_duration*100:.1f}%)")
    print(f"Database Save: {save_duration:6.2f}s ({save_duration/total_duration*100:.1f}%)")
    print("-" * 60)
    print(f"Total Time:    {total_duration:6.2f}s")
    print(f"\nItems discovered: {len(ad_units)} ad units, {len(placements)} placements, {len(labels)} labels")
    print("=" * 60)

    return True


if __name__ == "__main__":
    try:
        success = test_incremental_sync()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
