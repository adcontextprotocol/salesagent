"""
Background sync service for long-running inventory syncs.

This service runs syncs in background threads to prevent blocking the web server
and losing progress on container restarts.
"""

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import SyncJob

logger = logging.getLogger(__name__)

# Global registry of running sync threads
_active_syncs: dict[str, threading.Thread] = {}
_sync_lock = threading.Lock()


def start_inventory_sync_background(
    tenant_id: str,
    sync_mode: str = "incremental",
    sync_types: list[str] | None = None,
    custom_targeting_limit: int | None = None,
    audience_segment_limit: int | None = None,
) -> str:
    """
    Start an inventory sync in the background.

    Args:
        tenant_id: Tenant ID to sync
        sync_mode: "full" (delete all and resync) or "incremental" (only sync changed items since last successful sync)
        sync_types: Optional list of inventory types to sync
        custom_targeting_limit: Optional limit on custom targeting values
        audience_segment_limit: Optional limit on audience segments

    Returns:
        sync_id: The sync job ID for tracking progress

    Raises:
        ValueError: If a sync is already running for this tenant
    """

    # Create sync job record
    with get_db_session() as db:
        # Check if sync already running
        stmt = select(SyncJob).where(
            SyncJob.tenant_id == tenant_id, SyncJob.status == "running", SyncJob.sync_type == "inventory"
        )
        existing_sync = db.scalars(stmt).first()

        if existing_sync:
            # Check if sync is stale (running for >1 hour with no progress updates)
            from datetime import timedelta

            # Make started_at timezone-aware if it's naive (from database)
            started_at = existing_sync.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)

            time_running = datetime.now(UTC) - started_at
            is_stale = time_running > timedelta(hours=1) and not existing_sync.progress_data

            if is_stale:
                # Mark stale sync as failed and allow new sync to start
                existing_sync.status = "failed"
                existing_sync.completed_at = datetime.now(UTC)
                existing_sync.error_message = (
                    "Sync thread died (stale after 1+ hour with no progress) - marked as failed to allow fresh sync"
                )
                db.commit()
                logger.warning(
                    f"Marked stale sync {existing_sync.sync_id} as failed (running since {existing_sync.started_at}, no progress)"
                )
            else:
                # Sync is actually running, raise error
                raise ValueError(
                    f"Sync already running for tenant {tenant_id}: {existing_sync.sync_id} (started {started_at})"
                )

        # Create new sync job
        sync_id = f"sync_{tenant_id}_{int(datetime.now(UTC).timestamp())}"

        sync_job = SyncJob(
            sync_id=sync_id,
            tenant_id=tenant_id,
            sync_type="inventory",
            status="running",
            started_at=datetime.now(UTC),
            triggered_by="admin_ui",
            triggered_by_id="system",
            progress=0,
            progress_data={
                "phase": "Starting",
                "sync_types": sync_types,
                "custom_targeting_limit": custom_targeting_limit,
                "audience_segment_limit": audience_segment_limit,
            },
        )
        db.add(sync_job)
        db.commit()

    # Start background thread
    thread = threading.Thread(
        target=_run_sync_thread,
        args=(tenant_id, sync_id, sync_mode, sync_types, custom_targeting_limit, audience_segment_limit),
        daemon=True,
        name=f"sync-{sync_id}",
    )

    with _sync_lock:
        _active_syncs[sync_id] = thread

    thread.start()
    logger.info(f"Started background sync thread: {sync_id}")

    return sync_id


def _run_sync_thread(
    tenant_id: str,
    sync_id: str,
    sync_mode: str,
    sync_types: list[str] | None,
    custom_targeting_limit: int | None,
    audience_segment_limit: int | None,
):
    """
    Run the actual sync in a background thread with detailed phase-by-phase progress.

    This function runs in a separate thread and updates the SyncJob record
    as it progresses. If the thread is interrupted (container restart), the
    job will remain in 'running' state until cleaned up.

    Progress tracking:
    - Phase 0 (full mode only): Deleting existing inventory (1/7)
    - Phase 1: Discovering Ad Units (2/7 or 1/6)
    - Phase 2: Discovering Placements (3/7 or 2/6)
    - Phase 3: Discovering Labels (4/7 or 3/6)
    - Phase 4: Discovering Custom Targeting (5/7 or 4/6)
    - Phase 5: Discovering Audience Segments (6/7 or 5/6)
    - Phase 6: Marking Stale Inventory (7/7 or 6/6)
    """
    try:
        logger.info(f"[{sync_id}] Starting inventory sync for {tenant_id}")

        # Import here to avoid circular dependencies
        import os
        import tempfile

        import google.oauth2.service_account
        from googleads import ad_manager, oauth2

        from src.adapters.gam_inventory_discovery import GAMInventoryDiscovery
        from src.core.database.models import AdapterConfig, Tenant
        from src.services.gam_inventory_service import GAMInventoryService

        # Get tenant and adapter config (fresh session per thread)
        with get_db_session() as db:
            tenant = db.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
            if not tenant:
                _mark_sync_failed(sync_id, "Tenant not found")
                return

            adapter_config = db.scalars(
                select(AdapterConfig).filter_by(tenant_id=tenant_id, adapter_type="google_ad_manager")
            ).first()

            if not adapter_config or not adapter_config.gam_network_code:
                _mark_sync_failed(sync_id, "GAM not configured")
                return

            # Determine auth method
            auth_method = getattr(adapter_config, "gam_auth_method", None)
            if not auth_method:
                if adapter_config.gam_refresh_token:
                    auth_method = "oauth"
                elif hasattr(adapter_config, "gam_service_account_json") and adapter_config.gam_service_account_json:
                    auth_method = "service_account"
                else:
                    _mark_sync_failed(sync_id, "No GAM authentication configured")
                    return

            # Create GAM client based on auth method
            if auth_method == "service_account":
                service_account_json_str = adapter_config.gam_service_account_json
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                    f.write(service_account_json_str)
                    temp_keyfile = f.name

                try:
                    credentials = google.oauth2.service_account.Credentials.from_service_account_file(
                        temp_keyfile, scopes=["https://www.googleapis.com/auth/dfp"]
                    )
                    oauth2_client = oauth2.GoogleCredentialsClient(credentials)
                    client = ad_manager.AdManagerClient(
                        oauth2_client, "AdCP Sales Agent", network_code=adapter_config.gam_network_code
                    )
                finally:
                    try:
                        os.unlink(temp_keyfile)
                    except Exception:
                        pass
            else:  # OAuth
                oauth2_client = oauth2.GoogleRefreshTokenClient(
                    client_id=os.environ.get("GAM_OAUTH_CLIENT_ID"),
                    client_secret=os.environ.get("GAM_OAUTH_CLIENT_SECRET"),
                    refresh_token=adapter_config.gam_refresh_token,
                )
                client = ad_manager.AdManagerClient(
                    oauth2_client, "AdCP Sales Agent", network_code=adapter_config.gam_network_code
                )

        # Get last successful sync time for incremental mode
        last_sync_time = None
        if sync_mode == "incremental":
            with get_db_session() as db:
                from sqlalchemy import desc

                last_successful_sync = db.scalars(
                    select(SyncJob)
                    .where(
                        SyncJob.tenant_id == tenant_id,
                        SyncJob.sync_type == "inventory",
                        SyncJob.status == "completed",
                    )
                    .order_by(desc(SyncJob.completed_at))
                ).first()

                if last_successful_sync and last_successful_sync.completed_at:
                    last_sync_time = last_successful_sync.completed_at
                    logger.info(f"[{sync_id}] Incremental sync: using last successful sync time: {last_sync_time}")
                else:
                    logger.warning(
                        f"[{sync_id}] Incremental sync requested but no previous successful sync found - falling back to full sync"
                    )
                    sync_mode = "full"
                    last_sync_time = None

        # Calculate total phases
        total_phases = 7 if sync_mode == "full" else 6  # Add delete phase for full reset
        phase_offset = 1 if sync_mode == "full" else 0

        # Initialize discovery
        discovery = GAMInventoryDiscovery(client=client, tenant_id=tenant_id)
        start_time = datetime.now()

        # Helper function to update progress
        def update_progress(phase: str, phase_num: int, count: int = 0):
            _update_sync_progress(
                sync_id,
                {
                    "phase": phase,
                    "phase_num": phase_num,
                    "total_phases": total_phases,
                    "count": count,
                    "mode": sync_mode,
                },
            )

        # Phase 0: Full reset - delete all existing inventory (only for full sync)
        if sync_mode == "full":
            update_progress("Deleting Existing Inventory", 1)
            with get_db_session() as db:
                from sqlalchemy import delete

                from src.core.database.models import GAMInventory

                stmt = delete(GAMInventory).where(GAMInventory.tenant_id == tenant_id)
                db.execute(stmt)
                db.commit()
                logger.info(f"[{sync_id}] Full reset: deleted all existing inventory for tenant {tenant_id}")

        # Initialize inventory service for streaming writes
        with get_db_session() as db:
            inventory_service = GAMInventoryService(db)
            sync_time = datetime.now()

            # Phase 1: Ad Units (fetch → write → clear memory)
            update_progress("Discovering Ad Units", 1 + phase_offset)
            ad_units = discovery.discover_ad_units(since=last_sync_time)
            update_progress("Writing Ad Units to DB", 1 + phase_offset, len(ad_units))
            inventory_service._write_inventory_batch(tenant_id, "ad_unit", ad_units, sync_time)
            ad_units_count = len(ad_units)
            discovery.ad_units.clear()  # Clear from memory
            logger.info(f"[{sync_id}] Wrote {ad_units_count} ad units to database")

            # Phase 2: Placements (fetch → write → clear memory)
            update_progress("Discovering Placements", 2 + phase_offset)
            placements = discovery.discover_placements(since=last_sync_time)
            update_progress("Writing Placements to DB", 2 + phase_offset, len(placements))
            inventory_service._write_inventory_batch(tenant_id, "placement", placements, sync_time)
            placements_count = len(placements)
            discovery.placements.clear()  # Clear from memory
            logger.info(f"[{sync_id}] Wrote {placements_count} placements to database")

            # Phase 3: Labels (fetch → write → clear memory)
            update_progress("Discovering Labels", 3 + phase_offset)
            labels = discovery.discover_labels(since=last_sync_time)
            update_progress("Writing Labels to DB", 3 + phase_offset, len(labels))
            inventory_service._write_inventory_batch(tenant_id, "label", labels, sync_time)
            labels_count = len(labels)
            discovery.labels.clear()  # Clear from memory
            logger.info(f"[{sync_id}] Wrote {labels_count} labels to database")

            # Phase 4: Custom Targeting Keys (fetch → write → clear memory)
            update_progress("Discovering Targeting Keys", 4 + phase_offset)
            custom_targeting = discovery.discover_custom_targeting(fetch_values=False, since=last_sync_time)
            update_progress(
                "Writing Targeting Keys to DB",
                4 + phase_offset,
                custom_targeting.get("total_keys", 0),
            )
            inventory_service._write_custom_targeting_keys(
                tenant_id, list(discovery.custom_targeting_keys.values()), sync_time
            )
            targeting_count = len(discovery.custom_targeting_keys)
            discovery.custom_targeting_keys.clear()  # Clear from memory
            discovery.custom_targeting_values.clear()  # Clear from memory
            logger.info(f"[{sync_id}] Wrote {targeting_count} targeting keys to database")

            # Phase 5: Audience Segments (fetch → write → clear memory)
            update_progress("Discovering Audience Segments", 5 + phase_offset)
            audience_segments = discovery.discover_audience_segments(since=last_sync_time)
            update_progress("Writing Audience Segments to DB", 5 + phase_offset, len(audience_segments))
            inventory_service._write_inventory_batch(tenant_id, "audience_segment", audience_segments, sync_time)
            segments_count = len(audience_segments)
            discovery.audience_segments.clear()  # Clear from memory
            logger.info(f"[{sync_id}] Wrote {segments_count} audience segments to database")

            # Phase 6: Mark stale inventory
            update_progress("Marking Stale Inventory", 6 + phase_offset)
            inventory_service._mark_stale_inventory(tenant_id, sync_time)

        # Build result summary
        end_time = datetime.now()
        result = {
            "tenant_id": tenant_id,
            "sync_time": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "mode": sync_mode,
            "ad_units": {"total": ad_units_count},
            "placements": {"total": placements_count},
            "labels": {"total": labels_count},
            "custom_targeting": {
                "total_keys": targeting_count,
                "note": "Values lazy loaded on demand",
            },
            "audience_segments": {"total": segments_count},
            "streaming": True,
            "memory_optimized": True,
        }

        # Mark complete
        _mark_sync_complete(sync_id, result)
        logger.info(f"[{sync_id}] Sync completed successfully")

    except Exception as e:
        logger.error(f"[{sync_id}] Sync failed: {e}", exc_info=True)
        _mark_sync_failed(sync_id, str(e))

    finally:
        # Remove from active syncs
        with _sync_lock:
            _active_syncs.pop(sync_id, None)


def _update_sync_progress(sync_id: str, progress_data: dict[str, Any]):
    """Update sync job progress in database."""
    try:
        with get_db_session() as db:
            stmt = select(SyncJob).where(SyncJob.sync_id == sync_id)
            sync_job = db.scalars(stmt).first()
            if sync_job:
                sync_job.progress_data = progress_data
                db.commit()
    except Exception as e:
        logger.warning(f"Failed to update sync progress: {e}")


def _mark_sync_complete(sync_id: str, summary: dict[str, Any]):
    """Mark sync as completed with summary."""
    try:
        with get_db_session() as db:
            stmt = select(SyncJob).where(SyncJob.sync_id == sync_id)
            sync_job = db.scalars(stmt).first()
            if sync_job:
                sync_job.status = "completed"
                sync_job.completed_at = datetime.now(UTC)
                sync_job.duration_seconds = (sync_job.completed_at - sync_job.started_at).total_seconds()
                sync_job.summary = summary
                db.commit()
    except Exception as e:
        logger.error(f"Failed to mark sync complete: {e}")


def _mark_sync_failed(sync_id: str, error_message: str):
    """Mark sync as failed with error message."""
    try:
        with get_db_session() as db:
            stmt = select(SyncJob).where(SyncJob.sync_id == sync_id)
            sync_job = db.scalars(stmt).first()
            if sync_job:
                sync_job.status = "failed"
                sync_job.completed_at = datetime.now(UTC)
                sync_job.error_message = error_message
                if sync_job.started_at:
                    sync_job.duration_seconds = (sync_job.completed_at - sync_job.started_at).total_seconds()
                db.commit()
    except Exception as e:
        logger.error(f"Failed to mark sync failed: {e}")


def get_active_syncs() -> list[str]:
    """Get list of sync IDs currently running in background threads."""
    with _sync_lock:
        return list(_active_syncs.keys())


def is_sync_running(sync_id: str) -> bool:
    """Check if a sync is currently running in a background thread."""
    with _sync_lock:
        return sync_id in _active_syncs
