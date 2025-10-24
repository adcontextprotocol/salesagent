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
    sync_types: list[str] | None = None,
    custom_targeting_limit: int | None = None,
    audience_segment_limit: int | None = None,
) -> str:
    """
    Start an inventory sync in the background.

    Args:
        tenant_id: Tenant ID to sync
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
        stmt = select(SyncJob).where(SyncJob.tenant_id == tenant_id, SyncJob.status == "running")
        existing_sync = db.scalars(stmt).first()

        if existing_sync:
            raise ValueError(f"Sync already running for tenant {tenant_id}: {existing_sync.sync_id}")

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
        args=(tenant_id, sync_id, sync_types, custom_targeting_limit, audience_segment_limit),
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
    sync_types: list[str] | None,
    custom_targeting_limit: int | None,
    audience_segment_limit: int | None,
):
    """
    Run the actual sync in a background thread.

    This function runs in a separate thread and updates the SyncJob record
    as it progresses. If the thread is interrupted (container restart), the
    job will remain in 'running' state until cleaned up.
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

        # Update progress: Starting discovery
        _update_sync_progress(sync_id, {"phase": "Discovering inventory from GAM", "phase_num": 1, "total_phases": 2})

        # Initialize discovery
        discovery = GAMInventoryDiscovery(client=client, tenant_id=tenant_id)

        # Perform sync
        if sync_types:
            result = discovery.sync_selective(
                sync_types=sync_types,
                custom_targeting_limit=custom_targeting_limit,
                audience_segment_limit=audience_segment_limit,
            )
        else:
            result = discovery.sync_all()

        # Update progress: Saving to database
        _update_sync_progress(sync_id, {"phase": "Saving to database", "phase_num": 2, "total_phases": 2})

        # Save to database (fresh session)
        with get_db_session() as db:
            inventory_service = GAMInventoryService(db)
            inventory_service._save_inventory_to_db(tenant_id, discovery)

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
