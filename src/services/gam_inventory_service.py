"""
Service layer for GAM inventory management.

This service:
- Syncs inventory from GAM to database
- Provides inventory browsing and search
- Manages product-inventory mappings
- Handles inventory updates and caching
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import String, and_, create_engine, delete, func, or_, select, text
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from src.adapters.gam_inventory_discovery import (
    GAMInventoryDiscovery,
)
from src.core.database.db_config import DatabaseConfig
from src.core.database.models import GAMInventory, Product, ProductInventoryMapping

# Create database session factory
engine = create_engine(DatabaseConfig.get_connection_string())
SessionLocal = sessionmaker(bind=engine)
# Use scoped_session for thread-local sessions
db_session = scoped_session(SessionLocal)

logger = logging.getLogger(__name__)


class GAMInventoryService:
    """Service for managing GAM inventory data."""

    def __init__(self, db_session: Session):
        self.db = db_session

    def sync_tenant_inventory(self, tenant_id: str, gam_client) -> dict[str, Any]:
        """
        Sync all inventory for a tenant from GAM to database using streaming approach.

        This method processes inventory in chunks to minimize memory usage:
        - Fetches data from GAM API in paginated batches
        - Writes each batch to database immediately
        - Clears batch from memory before fetching next batch

        This prevents OOM errors with large inventories (10k+ items).

        Args:
            tenant_id: Tenant ID
            gam_client: Initialized GAM client

        Returns:
            Sync summary with counts and timing
        """
        logger.info(f"Starting streaming inventory sync for tenant {tenant_id}")

        # Create discovery instance for streaming sync
        from src.adapters.gam_inventory_discovery import GAMInventoryDiscovery

        discovery = GAMInventoryDiscovery(gam_client, tenant_id)

        # Use streaming sync: each inventory type is synced separately and written to DB immediately
        sync_summary = self._streaming_sync_all_inventory(tenant_id, discovery)

        return sync_summary

    def _save_inventory_to_db(self, tenant_id: str, discovery: GAMInventoryDiscovery):
        """Save discovered inventory to database using batched operations to prevent memory issues.

        Writes to database incrementally in batches rather than loading everything into memory.
        This prevents OOM errors with large inventories (10k+ items).
        """
        sync_time = datetime.now()
        BATCH_SIZE = 500  # Write every 500 items to keep memory usage low

        # Load ALL existing inventory IDs once (1 query instead of N)
        stmt = select(GAMInventory.inventory_type, GAMInventory.inventory_id, GAMInventory.id).where(
            GAMInventory.tenant_id == tenant_id
        )
        existing_inventory = self.db.execute(stmt).all()
        existing_ids = {(row.inventory_type, row.inventory_id): row.id for row in existing_inventory}

        # Track totals for logging
        total_inserted = 0
        total_updated = 0

        # Prepare batch insert and update lists
        to_insert = []
        to_update = []

        def flush_batch():
            """Flush current batch to database with error handling."""
            nonlocal total_inserted, total_updated
            try:
                if to_insert:
                    self.db.bulk_insert_mappings(GAMInventory, to_insert)
                    batch_inserted = len(to_insert)
                    total_inserted += batch_inserted
                    logger.info(f"Batch inserted {batch_inserted} inventory items")
                    to_insert.clear()
                if to_update:
                    self.db.bulk_update_mappings(GAMInventory, to_update)
                    batch_updated = len(to_update)
                    total_updated += batch_updated
                    logger.info(f"Batch updated {batch_updated} inventory items")
                    to_update.clear()
                self.db.commit()  # Commit each batch
            except Exception as e:
                logger.error(
                    f"Batch write failed at {total_inserted + total_updated} items: {e}",
                    exc_info=True,
                )
                self.db.rollback()
                raise  # Re-raise to fail the sync properly

        # Process ad units
        for ad_unit in discovery.ad_units.values():
            item_data = {
                "tenant_id": tenant_id,
                "inventory_type": "ad_unit",
                "inventory_id": ad_unit.id,
                "name": ad_unit.name,
                "path": ad_unit.path,
                "status": ad_unit.status.value,
                "inventory_metadata": {
                    "ad_unit_code": ad_unit.ad_unit_code,
                    "parent_id": ad_unit.parent_id,
                    "description": ad_unit.description,
                    "target_window": ad_unit.target_window,
                    "explicitly_targeted": ad_unit.explicitly_targeted,
                    "has_children": ad_unit.has_children,
                    "sizes": ad_unit.sizes,
                    "effective_applied_labels": ad_unit.effective_applied_labels,
                },
                "last_synced": sync_time,
            }

            key = ("ad_unit", ad_unit.id)
            if key in existing_ids:
                # Add database ID for update
                item_data["id"] = existing_ids[key]
                to_update.append(item_data)
            else:
                to_insert.append(item_data)

            # Flush batch every BATCH_SIZE items
            if (len(to_insert) + len(to_update)) >= BATCH_SIZE:
                flush_batch()

        # Flush remaining ad units
        flush_batch()
        logger.info("Completed saving ad units")

        # Process placements
        for placement in discovery.placements.values():
            item_data = {
                "tenant_id": tenant_id,
                "inventory_type": "placement",
                "inventory_id": placement.id,
                "name": placement.name,
                "path": [placement.name],  # Placements don't have hierarchy
                "status": placement.status,
                "inventory_metadata": {
                    "placement_code": placement.placement_code,
                    "description": placement.description,
                    "is_ad_sense_targeting_enabled": placement.is_ad_sense_targeting_enabled,
                    "ad_unit_ids": placement.ad_unit_ids,
                    "targeting_description": placement.targeting_description,
                },
                "last_synced": sync_time,
            }

            key = ("placement", placement.id)
            if key in existing_ids:
                item_data["id"] = existing_ids[key]
                to_update.append(item_data)
            else:
                to_insert.append(item_data)

            # Flush batch every BATCH_SIZE items
            if (len(to_insert) + len(to_update)) >= BATCH_SIZE:
                flush_batch()

        # Flush remaining placements
        flush_batch()
        logger.info("Completed saving placements")

        # Process labels
        for label in discovery.labels.values():
            item_data = {
                "tenant_id": tenant_id,
                "inventory_type": "label",
                "inventory_id": label.id,
                "name": label.name,
                "path": [label.name],
                "status": "ACTIVE" if label.is_active else "INACTIVE",
                "inventory_metadata": {
                    "description": label.description,
                    "ad_category": label.ad_category,
                    "label_type": label.label_type,
                },
                "last_synced": sync_time,
            }

            key = ("label", label.id)
            if key in existing_ids:
                item_data["id"] = existing_ids[key]
                to_update.append(item_data)
            else:
                to_insert.append(item_data)

            # Flush batch every BATCH_SIZE items
            if (len(to_insert) + len(to_update)) >= BATCH_SIZE:
                flush_batch()

        # Flush remaining labels
        flush_batch()
        logger.info("Completed saving labels")

        # Process custom targeting keys
        for key in discovery.custom_targeting_keys.values():
            item_data = {
                "tenant_id": tenant_id,
                "inventory_type": "custom_targeting_key",
                "inventory_id": key.id,
                "name": key.name,
                "path": [key.display_name],
                "status": key.status,
                "inventory_metadata": {
                    "display_name": key.display_name,
                    "type": key.type,  # PREDEFINED or FREEFORM
                    "reportable_type": key.reportable_type,
                },
                "last_synced": sync_time,
            }

            item_key = ("custom_targeting_key", key.id)
            if item_key in existing_ids:
                item_data["id"] = existing_ids[item_key]
                to_update.append(item_data)
            else:
                to_insert.append(item_data)

            # Process values for this key
            values = discovery.custom_targeting_values.get(key.id, [])
            for value in values:
                value_data = {
                    "tenant_id": tenant_id,
                    "inventory_type": "custom_targeting_value",
                    "inventory_id": value.id,
                    "name": value.name,
                    "path": [key.display_name, value.display_name],
                    "status": value.status,
                    "inventory_metadata": {
                        "custom_targeting_key_id": value.custom_targeting_key_id,
                        "display_name": value.display_name,
                        "match_type": value.match_type,
                        "key_name": key.name,
                        "key_display_name": key.display_name,
                    },
                    "last_synced": sync_time,
                }

                value_key = ("custom_targeting_value", value.id)
                if value_key in existing_ids:
                    value_data["id"] = existing_ids[value_key]
                    to_update.append(value_data)
                else:
                    to_insert.append(value_data)

                # Flush batch every BATCH_SIZE items (values can be huge)
                if (len(to_insert) + len(to_update)) >= BATCH_SIZE:
                    flush_batch()

        # Flush remaining targeting keys/values
        flush_batch()
        logger.info("Completed saving targeting keys and values")

        # Process audience segments
        for segment in discovery.audience_segments.values():
            item_data = {
                "tenant_id": tenant_id,
                "inventory_type": "audience_segment",
                "inventory_id": segment.id,
                "name": segment.name,
                "path": [segment.type, segment.name],  # e.g. ["FIRST_PARTY", "Sports Enthusiasts"]
                "status": segment.status,
                "inventory_metadata": {
                    "description": segment.description,
                    "category_ids": segment.category_ids,
                    "type": segment.type,  # FIRST_PARTY or THIRD_PARTY
                    "size": segment.size,
                    "data_provider_name": segment.data_provider_name,
                    "segment_type": segment.segment_type,  # RULE_BASED, SHARED, etc.
                },
                "last_synced": sync_time,
            }

            key = ("audience_segment", segment.id)
            if key in existing_ids:
                item_data["id"] = existing_ids[key]
                to_update.append(item_data)
            else:
                to_insert.append(item_data)

            # Flush batch every BATCH_SIZE items
            if (len(to_insert) + len(to_update)) >= BATCH_SIZE:
                flush_batch()

        # Flush remaining audience segments
        flush_batch()
        logger.info("Completed saving audience segments")

        # Mark old items as potentially stale (but keep ad units active)
        stale_cutoff = sync_time - timedelta(seconds=1)

        # Don't mark ad units as STALE - they should remain ACTIVE
        from sqlalchemy import update

        stmt = (
            update(GAMInventory)
            .where(
                and_(
                    GAMInventory.tenant_id == tenant_id,
                    GAMInventory.last_synced < stale_cutoff,
                    GAMInventory.inventory_type != "ad_unit",  # Keep ad units active
                )
            )
            .values(status="STALE")
        )
        self.db.execute(stmt)
        self.db.commit()

        logger.info(
            f"Saved inventory to database: {total_inserted} new, {total_updated} updated (batched operations - prevents OOM)"
        )

    def _streaming_sync_all_inventory(self, tenant_id: str, discovery: "GAMInventoryDiscovery") -> dict[str, Any]:
        """
        Stream inventory sync: fetch and write each type separately to minimize memory.

        This method syncs inventory types one at a time:
        1. Fetch ad units from GAM → write to DB → clear from memory
        2. Fetch placements from GAM → write to DB → clear from memory
        3. Fetch labels from GAM → write to DB → clear from memory
        4. Fetch custom targeting keys (values lazy loaded) → write to DB → clear from memory
        5. Fetch audience segments → write to DB → clear from memory

        Memory usage stays bounded regardless of inventory size.

        Args:
            tenant_id: Tenant ID
            discovery: GAMInventoryDiscovery instance (empty at start)

        Returns:
            Sync summary with counts and timing
        """
        from datetime import datetime

        start_time = datetime.now()
        sync_time = datetime.now()

        logger.info(f"Starting streaming inventory sync for tenant {tenant_id}")

        # Track counts
        counts = {
            "ad_units": 0,
            "placements": 0,
            "labels": 0,
            "custom_targeting_keys": 0,
            "custom_targeting_values": 0,
            "audience_segments": 0,
        }

        # 1. Sync ad units (stream and write)
        logger.info("Streaming ad units...")
        ad_units = discovery.discover_ad_units()
        self._write_inventory_batch(tenant_id, "ad_unit", ad_units, sync_time)
        counts["ad_units"] = len(ad_units)
        discovery.ad_units.clear()  # Clear from memory immediately
        logger.info(f"Synced {counts['ad_units']} ad units")

        # 2. Sync placements (stream and write)
        logger.info("Streaming placements...")
        try:
            placements = discovery.discover_placements()
            self._write_inventory_batch(tenant_id, "placement", placements, sync_time)
            counts["placements"] = len(placements)
            discovery.placements.clear()  # Clear from memory
            logger.info(f"Synced {counts['placements']} placements")
        except Exception as e:
            logger.error(f"⏰ Placements sync timed out or failed: {e}. Continuing with other inventory types...")
            counts["placements"] = 0

        # 3. Sync labels (stream and write)
        logger.info("Streaming labels...")
        try:
            labels = discovery.discover_labels()
            self._write_inventory_batch(tenant_id, "label", labels, sync_time)
            counts["labels"] = len(labels)
            discovery.labels.clear()  # Clear from memory
            logger.info(f"Synced {counts['labels']} labels")
        except Exception as e:
            logger.error(f"⏰ Labels sync timed out or failed: {e}. Continuing with other inventory types...")
            counts["labels"] = 0

        # 4. Sync custom targeting KEYS ONLY (values lazy loaded on demand)
        logger.info("Streaming custom targeting keys (values lazy loaded)...")
        try:
            custom_targeting = discovery.discover_custom_targeting(
                max_values_per_key=None,
                fetch_values=False,  # Don't fetch values  # Lazy load values on demand
            )
            self._write_custom_targeting_keys(tenant_id, discovery.custom_targeting_keys.values(), sync_time)
            counts["custom_targeting_keys"] = len(discovery.custom_targeting_keys)
            counts["custom_targeting_values"] = custom_targeting.get("total_values", 0)
            discovery.custom_targeting_keys.clear()  # Clear from memory
            discovery.custom_targeting_values.clear()  # Clear from memory
            logger.info(f"Synced {counts['custom_targeting_keys']} custom targeting keys (values lazy loaded)")
        except Exception as e:
            logger.error(f"⏰ Custom targeting sync timed out or failed: {e}. Continuing with other inventory types...")
            counts["custom_targeting_keys"] = 0
            counts["custom_targeting_values"] = 0

        # 5. Sync audience segments (first-party only)
        logger.info("Streaming audience segments...")
        audience_segments = discovery.discover_audience_segments()
        self._write_inventory_batch(tenant_id, "audience_segment", audience_segments, sync_time)
        counts["audience_segments"] = len(audience_segments)
        discovery.audience_segments.clear()  # Clear from memory
        logger.info(f"Synced {counts['audience_segments']} audience segments")

        # Mark old items as stale
        self._mark_stale_inventory(tenant_id, sync_time)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        summary = {
            "tenant_id": tenant_id,
            "sync_time": sync_time.isoformat(),
            "duration_seconds": duration,
            "ad_units": {"total": counts["ad_units"]},
            "placements": {"total": counts["placements"]},
            "labels": {"total": counts["labels"]},
            "custom_targeting": {
                "total_keys": counts["custom_targeting_keys"],
                "total_values": counts["custom_targeting_values"],
                "note": "Values lazy loaded on demand",
            },
            "audience_segments": {"total": counts["audience_segments"]},
            "streaming": True,
            "memory_optimized": True,
        }

        logger.info(f"Streaming sync completed in {duration:.2f}s: {counts}")
        return summary

    def _write_inventory_batch(self, tenant_id: str, inventory_type: str, items: list, sync_time: datetime):
        """Write a batch of inventory items to database efficiently.

        Args:
            tenant_id: Tenant ID
            inventory_type: Type of inventory (ad_unit, placement, label, audience_segment)
            items: List of inventory items to write
            sync_time: Sync timestamp
        """
        if not items:
            return

        logger.info(f"📊 Writing {len(items)} {inventory_type} items to database...")

        BATCH_SIZE = 500

        # Load existing inventory IDs once
        logger.info(f"🔍 Loading existing {inventory_type} IDs from database...")
        stmt = select(GAMInventory.inventory_id, GAMInventory.id).where(
            and_(GAMInventory.tenant_id == tenant_id, GAMInventory.inventory_type == inventory_type)
        )
        existing = self.db.execute(stmt).all()
        existing_ids = {row.inventory_id: row.id for row in existing}
        logger.info(f"✅ Found {len(existing_ids)} existing {inventory_type} items")

        to_insert = []
        to_update = []
        batch_num = 0

        logger.info(f"🔄 Processing {len(items)} items (batch size: {BATCH_SIZE})...")
        for idx, item in enumerate(items):
            item_data = self._convert_item_to_db_format(tenant_id, inventory_type, item, sync_time)

            if item.id in existing_ids:
                item_data["id"] = existing_ids[item.id]
                to_update.append(item_data)
            else:
                to_insert.append(item_data)

            # Flush batch
            if (len(to_insert) + len(to_update)) >= BATCH_SIZE:
                batch_num += 1
                logger.info(f"💾 Flushing batch {batch_num} (processed {idx + 1}/{len(items)} items)...")
                self._flush_batch(to_insert, to_update)
                to_insert.clear()
                to_update.clear()

        # Flush remaining
        if to_insert or to_update:
            batch_num += 1
            logger.info(f"💾 Flushing final batch {batch_num} ({len(to_insert)} new, {len(to_update)} updates)...")
            self._flush_batch(to_insert, to_update)

        logger.info(f"✅ Completed writing {len(items)} {inventory_type} items in {batch_num} batch(es)")

    def _write_custom_targeting_keys(self, tenant_id: str, keys: list, sync_time: datetime):
        """Write custom targeting keys to database (values are lazy loaded separately).

        Args:
            tenant_id: Tenant ID
            keys: List of CustomTargetingKey objects
            sync_time: Sync timestamp
        """
        if not keys:
            return

        BATCH_SIZE = 500

        # Load existing key IDs once
        # Use a fresh query to avoid stale connection issues
        stmt = select(GAMInventory.inventory_id, GAMInventory.id).where(
            and_(GAMInventory.tenant_id == tenant_id, GAMInventory.inventory_type == "custom_targeting_key")
        )

        # Explicitly expire_all() and test connection health before querying
        # This prevents hanging on stale connections in long-running syncs
        self.db.expire_all()

        # Test connection is alive with a simple query (connection keep-alive)
        try:
            self.db.execute(text("SELECT 1")).scalar()
        except Exception as e:
            logger.warning(f"Connection test failed, will retry query: {e}")
            # Connection is stale - SQLAlchemy will automatically reconnect on next query

        existing = self.db.execute(stmt).all()
        existing_ids = {row.inventory_id: row.id for row in existing}

        to_insert = []
        to_update = []

        for key in keys:
            item_data = {
                "tenant_id": tenant_id,
                "inventory_type": "custom_targeting_key",
                "inventory_id": key.id,
                "name": key.name,
                "path": [key.display_name],
                "status": key.status,
                "inventory_metadata": {
                    "display_name": key.display_name,
                    "type": key.type,
                    "reportable_type": key.reportable_type,
                },
                "last_synced": sync_time,
            }

            if key.id in existing_ids:
                item_data["id"] = existing_ids[key.id]
                to_update.append(item_data)
            else:
                to_insert.append(item_data)

            # Flush batch
            if (len(to_insert) + len(to_update)) >= BATCH_SIZE:
                self._flush_batch(to_insert, to_update)
                to_insert.clear()
                to_update.clear()

        # Flush remaining
        self._flush_batch(to_insert, to_update)

    def _convert_item_to_db_format(self, tenant_id: str, inventory_type: str, item, sync_time: datetime) -> dict:
        """Convert inventory item to database format.

        Args:
            tenant_id: Tenant ID
            inventory_type: Type of inventory
            item: Inventory item object
            sync_time: Sync timestamp

        Returns:
            Dictionary ready for database insert/update
        """

        if inventory_type == "ad_unit":
            return {
                "tenant_id": tenant_id,
                "inventory_type": "ad_unit",
                "inventory_id": item.id,
                "name": item.name,
                "path": item.path,
                "status": item.status.value,
                "inventory_metadata": {
                    "ad_unit_code": item.ad_unit_code,
                    "parent_id": item.parent_id,
                    "description": item.description,
                    "target_window": item.target_window,
                    "explicitly_targeted": item.explicitly_targeted,
                    "has_children": item.has_children,
                    "sizes": item.sizes,
                    "effective_applied_labels": item.effective_applied_labels,
                },
                "last_synced": sync_time,
            }
        elif inventory_type == "placement":
            return {
                "tenant_id": tenant_id,
                "inventory_type": "placement",
                "inventory_id": item.id,
                "name": item.name,
                "path": [item.name],
                "status": item.status,
                "inventory_metadata": {
                    "placement_code": item.placement_code,
                    "description": item.description,
                    "is_ad_sense_targeting_enabled": item.is_ad_sense_targeting_enabled,
                    "ad_unit_ids": item.ad_unit_ids,
                    "targeting_description": item.targeting_description,
                },
                "last_synced": sync_time,
            }
        elif inventory_type == "label":
            return {
                "tenant_id": tenant_id,
                "inventory_type": "label",
                "inventory_id": item.id,
                "name": item.name,
                "path": [item.name],
                "status": "ACTIVE" if item.is_active else "INACTIVE",
                "inventory_metadata": {
                    "description": item.description,
                    "ad_category": item.ad_category,
                    "label_type": item.label_type,
                },
                "last_synced": sync_time,
            }
        elif inventory_type == "audience_segment":
            return {
                "tenant_id": tenant_id,
                "inventory_type": "audience_segment",
                "inventory_id": item.id,
                "name": item.name,
                "path": [item.type, item.name],
                "status": item.status,
                "inventory_metadata": {
                    "description": item.description,
                    "category_ids": item.category_ids,
                    "type": item.type,
                    "size": item.size,
                    "data_provider_name": item.data_provider_name,
                    "segment_type": item.segment_type,
                },
                "last_synced": sync_time,
            }
        else:
            raise ValueError(f"Unknown inventory type: {inventory_type}")

    def _flush_batch(self, to_insert: list, to_update: list):
        """Flush a batch of inserts and updates to database with timeout and connection recovery.

        Args:
            to_insert: List of items to insert
            to_update: List of items to update
        """
        from sqlalchemy.exc import DBAPIError, OperationalError

        from src.adapters.gam.utils.timeout_handler import TimeoutError, timeout

        @timeout(seconds=120)  # 2 minute timeout for database operations
        def _commit_with_timeout():
            """Commit with timeout to prevent indefinite hangs."""
            self.db.commit()

        try:
            if to_insert:
                logger.info(f"📝 Starting bulk insert of {len(to_insert)} items...")
                self.db.bulk_insert_mappings(GAMInventory, to_insert)
                logger.info(f"✅ Batch inserted {len(to_insert)} items")
            if to_update:
                logger.info(f"📝 Starting bulk update of {len(to_update)} items...")
                self.db.bulk_update_mappings(GAMInventory, to_update)
                logger.info(f"✅ Batch updated {len(to_update)} items")
            logger.info("💾 Committing batch transaction (120s timeout)...")
            _commit_with_timeout()
            logger.info("✅ Batch committed successfully")
        except TimeoutError as e:
            logger.error(f"⏰ Database commit timed out after 120s: {e}")
            logger.error(f"   Insert count: {len(to_insert)}, Update count: {len(to_update)}")
            logger.error("   This usually indicates: lost connection, lock contention, or large transaction")
            self.db.rollback()
            raise TimeoutError(
                "Database commit timed out after 120s - possible lost connection, lock contention, or large transaction"
            )
        except (OperationalError, DBAPIError) as e:
            # Connection errors - log and re-raise with context
            logger.error(f"❌ Database connection error during batch write: {e}")
            logger.error(f"   Insert count: {len(to_insert)}, Update count: {len(to_update)}")
            logger.error("   Connection may have been lost during long-running sync")
            self.db.rollback()
            raise OperationalError(
                "Database connection lost during batch write. This can happen in long-running syncs if the connection times out.",
                params=None,
                orig=e.orig if hasattr(e, "orig") else None,
            )
        except Exception as e:
            logger.error(f"❌ Batch write failed: {e}", exc_info=True)
            logger.error(f"   Insert count: {len(to_insert)}, Update count: {len(to_update)}")
            self.db.rollback()
            raise

    def _mark_stale_inventory(self, tenant_id: str, sync_time: datetime):
        """Mark inventory items not updated in this sync as stale.

        Args:
            tenant_id: Tenant ID
            sync_time: Current sync timestamp
        """
        from sqlalchemy import update

        stale_cutoff = sync_time - timedelta(seconds=1)

        # Don't mark ad units as STALE - they should remain ACTIVE
        stmt = (
            update(GAMInventory)
            .where(
                and_(
                    GAMInventory.tenant_id == tenant_id,
                    GAMInventory.last_synced < stale_cutoff,
                    GAMInventory.inventory_type != "ad_unit",  # Keep ad units active
                )
            )
            .values(status="STALE")
        )
        self.db.execute(stmt)
        self.db.commit()
        logger.info("Marked stale inventory items")

    def _upsert_inventory_item(
        self,
        tenant_id: str,
        inventory_type: str,
        inventory_id: str,
        name: str,
        path: list[str],
        status: str,
        inventory_metadata: dict,
        last_synced: datetime,
    ):
        """Insert or update a single inventory item in database.

        Used for lazy loading individual items (e.g., custom targeting values).

        Args:
            tenant_id: Tenant ID
            inventory_type: Type of inventory
            inventory_id: GAM inventory ID
            name: Item name
            path: Item path
            status: Item status
            inventory_metadata: Item metadata
            last_synced: Sync timestamp
        """
        # Check if item exists
        stmt = select(GAMInventory).where(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == inventory_type,
                GAMInventory.inventory_id == inventory_id,
            )
        )
        existing = self.db.scalars(stmt).first()

        if existing:
            # Update existing
            existing.name = name
            existing.path = path
            existing.status = status
            existing.inventory_metadata = inventory_metadata
            existing.last_synced = last_synced
        else:
            # Insert new
            item = GAMInventory(
                tenant_id=tenant_id,
                inventory_type=inventory_type,
                inventory_id=inventory_id,
                name=name,
                path=path,
                status=status,
                inventory_metadata=inventory_metadata,
                last_synced=last_synced,
            )
            self.db.add(item)

        self.db.commit()

    def get_ad_unit_tree(self, tenant_id: str, limit: int = 1000) -> dict[str, Any]:
        """
        Get hierarchical ad unit tree from database.

        For large inventories (10k+ ad units), this returns a limited set
        to prevent browser timeouts. Use the search endpoint for finding
        specific ad units.

        Args:
            tenant_id: Tenant ID
            limit: Maximum number of ad units to return (default 1000)

        Returns:
            Hierarchical tree structure with limited ad units
        """
        # Get ad units with limit to prevent timeouts on large inventories
        stmt = (
            select(GAMInventory)
            .where(
                and_(
                    GAMInventory.tenant_id == tenant_id,
                    GAMInventory.inventory_type == "ad_unit",
                    GAMInventory.status != "STALE",
                )
            )
            .order_by(GAMInventory.name)
            .limit(limit)
        )
        ad_units = self.db.scalars(stmt).all()

        # Build lookup maps
        unit_map = {}
        root_units = []

        for unit in ad_units:
            unit_data = {
                "id": unit.inventory_id,
                "name": unit.name,
                "path": unit.path,
                "status": unit.status,
                "metadata": unit.inventory_metadata,
                "children": [],
            }
            unit_map[unit.inventory_id] = unit_data

            # Check if root (no parent or parent not in path)
            parent_id = unit.inventory_metadata.get("parent_id") if unit.inventory_metadata else None
            if not parent_id:
                root_units.append(unit_data)

        # Build hierarchy
        for unit in ad_units:
            parent_id = unit.inventory_metadata.get("parent_id") if unit.inventory_metadata else None
            if parent_id and parent_id in unit_map:
                unit_map[parent_id]["children"].append(unit_map[unit.inventory_id])

        # Get last sync info from gam_inventory table
        stmt = select(func.max(GAMInventory.last_synced)).where(GAMInventory.tenant_id == tenant_id)
        last_sync_result = self.db.scalar(stmt)
        last_sync = last_sync_result.isoformat() if last_sync_result else None

        # Get counts for other inventory types
        placements_count = (
            self.db.scalar(
                select(func.count()).where(
                    and_(
                        GAMInventory.tenant_id == tenant_id,
                        GAMInventory.inventory_type == "placement",
                        GAMInventory.status != "STALE",
                    )
                )
            )
            or 0
        )

        labels_count = (
            self.db.scalar(
                select(func.count()).where(
                    and_(
                        GAMInventory.tenant_id == tenant_id,
                        GAMInventory.inventory_type == "label",
                        GAMInventory.status != "STALE",
                    )
                )
            )
            or 0
        )

        custom_targeting_keys_count = (
            self.db.scalar(
                select(func.count()).where(
                    and_(
                        GAMInventory.tenant_id == tenant_id,
                        GAMInventory.inventory_type == "custom_targeting_key",
                        GAMInventory.status != "STALE",
                    )
                )
            )
            or 0
        )

        audience_segments_count = (
            self.db.scalar(
                select(func.count()).where(
                    and_(
                        GAMInventory.tenant_id == tenant_id,
                        GAMInventory.inventory_type == "audience_segment",
                        GAMInventory.status != "STALE",
                    )
                )
            )
            or 0
        )

        return {
            "root_units": root_units,
            "total_units": len(ad_units),
            "placements": placements_count,
            "labels": labels_count,
            "custom_targeting_keys": custom_targeting_keys_count,
            "audience_segments": audience_segments_count,
            "last_sync": last_sync,
            "needs_refresh": self._needs_refresh(last_sync),
        }

    def _needs_refresh(self, last_sync_str: str | None) -> bool:
        """Check if inventory needs refresh (older than 24 hours)."""
        if not last_sync_str:
            return True

        try:
            last_sync = datetime.fromisoformat(last_sync_str)
            return datetime.now() - last_sync > timedelta(hours=24)
        except:
            return True

    def search_inventory(
        self,
        tenant_id: str,
        query: str | None = None,
        inventory_type: str | None = None,
        status: str | None = None,
        sizes: list[dict[str, int]] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Search inventory with filters.

        For large inventories, results are limited to prevent timeouts.
        Use more specific search terms to narrow results.

        Args:
            tenant_id: Tenant ID
            query: Text search in name/path
            inventory_type: Filter by type (ad_unit, placement, label)
            status: Filter by status
            sizes: Filter ad units by size support
            limit: Maximum results to return (default 500)

        Returns:
            List of matching inventory items (up to limit)
        """
        filters = [GAMInventory.tenant_id == tenant_id, GAMInventory.status != "STALE"]

        if inventory_type:
            filters.append(GAMInventory.inventory_type == inventory_type)

        if status:
            filters.append(GAMInventory.status == status)

        if query:
            # Search in name and path
            filters.append(
                or_(GAMInventory.name.ilike(f"%{query}%"), func.cast(GAMInventory.path, String).ilike(f"%{query}%"))
            )

        stmt = select(GAMInventory).where(and_(*filters)).order_by(GAMInventory.name).limit(limit)
        results = self.db.scalars(stmt).all()

        # Filter by sizes if specified
        if sizes and inventory_type in (None, "ad_unit"):
            filtered_results = []
            for result in results:
                if result.inventory_type != "ad_unit":
                    if inventory_type is None:
                        continue
                    filtered_results.append(result)
                    continue

                unit_sizes = result.inventory_metadata.get("sizes", []) if result.inventory_metadata else []
                has_matching_size = False

                for required_size in sizes:
                    for unit_size in unit_sizes:
                        if (
                            unit_size["width"] == required_size["width"]
                            and unit_size["height"] == required_size["height"]
                        ):
                            has_matching_size = True
                            break
                    if has_matching_size:
                        break

                if has_matching_size:
                    filtered_results.append(result)

            results = filtered_results

        # Convert to dict format
        return [
            {
                "id": item.inventory_id,
                "type": item.inventory_type,
                "name": item.name,
                "path": item.path,
                "status": item.status,
                "metadata": item.inventory_metadata,
                "last_synced": item.last_synced.isoformat(),
            }
            for item in results
        ]

    def get_product_inventory(self, tenant_id: str, product_id: str) -> dict[str, Any]:
        """
        Get inventory mappings for a product.

        Args:
            tenant_id: Tenant ID
            product_id: Product ID

        Returns:
            Product inventory configuration
        """
        # Get product
        stmt = select(Product).where(and_(Product.tenant_id == tenant_id, Product.product_id == product_id))
        product = self.db.scalars(stmt).first()

        if not product:
            return None

        # Get mappings
        stmt = select(ProductInventoryMapping).where(
            and_(ProductInventoryMapping.tenant_id == tenant_id, ProductInventoryMapping.product_id == product_id)
        )
        mappings = self.db.scalars(stmt).all()

        # Get inventory details
        ad_units = []
        placements = []

        for mapping in mappings:
            stmt = select(GAMInventory).where(
                and_(
                    GAMInventory.tenant_id == tenant_id,
                    GAMInventory.inventory_type == mapping.inventory_type,
                    GAMInventory.inventory_id == mapping.inventory_id,
                )
            )
            inventory = self.db.scalars(stmt).first()

            if inventory:
                item = {
                    "id": inventory.inventory_id,
                    "name": inventory.name,
                    "path": inventory.path,
                    "is_primary": mapping.is_primary,
                    "metadata": inventory.inventory_metadata,
                }

                if mapping.inventory_type == "ad_unit":
                    ad_units.append(item)
                elif mapping.inventory_type == "placement":
                    placements.append(item)

        return {
            "product_id": product_id,
            "product_name": product.name,
            "ad_units": ad_units,
            "placements": placements,
            "total_mappings": len(mappings),
        }

    def update_product_inventory(
        self,
        tenant_id: str,
        product_id: str,
        ad_unit_ids: list[str],
        placement_ids: list[str] | None = None,
        primary_ad_unit_id: str | None = None,
    ) -> bool:
        """
        Update product inventory mappings.

        Args:
            tenant_id: Tenant ID
            product_id: Product ID
            ad_unit_ids: List of ad unit IDs to map
            placement_ids: Optional list of placement IDs
            primary_ad_unit_id: Optional primary ad unit

        Returns:
            Success boolean
        """
        try:
            # Verify product exists
            stmt = select(Product).where(and_(Product.tenant_id == tenant_id, Product.product_id == product_id))
            product = self.db.scalars(stmt).first()

            if not product:
                return False

            # Delete existing mappings
            stmt = delete(ProductInventoryMapping).where(
                and_(ProductInventoryMapping.tenant_id == tenant_id, ProductInventoryMapping.product_id == product_id)
            )
            self.db.execute(stmt)

            # Add new ad unit mappings
            for ad_unit_id in ad_unit_ids:
                mapping = ProductInventoryMapping(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    inventory_type="ad_unit",
                    inventory_id=ad_unit_id,
                    is_primary=(ad_unit_id == primary_ad_unit_id),
                )
                self.db.add(mapping)

            # Add placement mappings if provided
            if placement_ids:
                for placement_id in placement_ids:
                    mapping = ProductInventoryMapping(
                        tenant_id=tenant_id,
                        product_id=product_id,
                        inventory_type="placement",
                        inventory_id=placement_id,
                        is_primary=False,
                    )
                    self.db.add(mapping)

            # Update product implementation config
            if not product.implementation_config:
                product.implementation_config = {}

            product.implementation_config["targeted_ad_unit_ids"] = ad_unit_ids
            if placement_ids:
                product.implementation_config["targeted_placement_ids"] = placement_ids

            self.db.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to update product inventory: {e}")
            self.db.rollback()
            return False

    def suggest_inventory_for_product(self, tenant_id: str, product_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Suggest inventory based on product configuration.

        Args:
            tenant_id: Tenant ID
            product_id: Product ID
            limit: Maximum suggestions to return

        Returns:
            List of suggested inventory items with scores
        """
        # Get product
        stmt = select(Product).where(and_(Product.tenant_id == tenant_id, Product.product_id == product_id))
        product = self.db.scalars(stmt).first()

        if not product:
            return []

        # Extract product characteristics
        creative_sizes = []
        if product.formats:
            # Parse formats to get sizes
            for format_id in product.formats:
                if "display" in format_id:
                    # Extract size from format like "display_300x250"
                    parts = format_id.split("_")
                    if len(parts) > 1 and "x" in parts[1]:
                        width, height = parts[1].split("x")
                        creative_sizes.append({"width": int(width), "height": int(height)})

        # Get keywords from product name and description
        keywords = []
        if product.name:
            keywords.extend(product.name.lower().split())
        if product.description:
            keywords.extend(product.description.lower().split()[:5])  # First 5 words

        # Search for matching ad units
        suggestions = []

        # Get active ad units
        stmt = select(GAMInventory).where(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == "ad_unit",
                GAMInventory.status == "ACTIVE",
            )
        )
        ad_units = self.db.scalars(stmt).all()

        for unit in ad_units:
            score = 0
            reasons = []

            # Check size match
            unit_sizes = unit.inventory_metadata.get("sizes", [])
            for creative_size in creative_sizes:
                for unit_size in unit_sizes:
                    if unit_size["width"] == creative_size["width"] and unit_size["height"] == creative_size["height"]:
                        score += 10
                        reasons.append(f"Size match: {unit_size['width']}x{unit_size['height']}")

            # Check keyword match
            unit_text = " ".join([unit.name.lower()] + [p.lower() for p in unit.path])
            for keyword in keywords:
                if keyword in unit_text:
                    score += 5
                    reasons.append(f"Keyword match: {keyword}")

            # Prefer explicitly targeted units
            if unit.inventory_metadata.get("explicitly_targeted"):
                score += 3
                reasons.append("Explicitly targeted")

            # Prefer specific placements
            if len(unit.path) > 2:
                score += 2
                reasons.append("Specific placement")

            if score > 0:
                suggestions.append(
                    {
                        "inventory": {
                            "id": unit.inventory_id,
                            "name": unit.name,
                            "path": " > ".join(unit.path),
                            "sizes": unit_sizes,
                        },
                        "score": score,
                        "reasons": reasons,
                    }
                )

        # Sort by score and limit
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:limit]

    def get_all_targeting_data(self, tenant_id: str) -> dict[str, Any]:
        """
        Get all targeting data for browsing.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dictionary with all targeting data organized by type
        """
        # Get custom targeting keys
        stmt = select(GAMInventory).where(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == "custom_targeting_key",
                GAMInventory.status != "STALE",
            )
        )
        custom_keys = self.db.scalars(stmt).all()

        # Get custom targeting values grouped by key
        custom_values = {}
        stmt = select(GAMInventory).where(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == "custom_targeting_value",
                GAMInventory.status != "STALE",
            )
        )
        all_values = self.db.scalars(stmt).all()

        for value in all_values:
            if not value.inventory_metadata:
                continue
            key_id = value.inventory_metadata.get("custom_targeting_key_id")
            if key_id:
                if key_id not in custom_values:
                    custom_values[key_id] = []
                custom_values[key_id].append(
                    {
                        "id": value.inventory_id,
                        "name": value.name,
                        "display_name": value.inventory_metadata.get("display_name", value.name),
                        "match_type": value.inventory_metadata.get("match_type", "EXACT"),
                        "status": value.status,
                    }
                )

        # Get audience segments
        stmt = select(GAMInventory).where(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == "audience_segment",
                GAMInventory.status != "STALE",
            )
        )
        audiences = self.db.scalars(stmt).all()

        # Get labels
        stmt = select(GAMInventory).where(
            and_(
                GAMInventory.tenant_id == tenant_id,
                GAMInventory.inventory_type == "label",
                GAMInventory.status != "STALE",
            )
        )
        labels = self.db.scalars(stmt).all()

        # Get last sync info from gam_inventory table
        stmt = select(func.max(GAMInventory.last_synced)).where(GAMInventory.tenant_id == tenant_id)
        last_sync_result = self.db.scalar(stmt)
        last_sync = last_sync_result.isoformat() if last_sync_result else None

        # Format response
        return {
            "customKeys": [
                {
                    "id": key.inventory_id,
                    "name": key.name,
                    "display_name": (
                        key.inventory_metadata.get("display_name", key.name) if key.inventory_metadata else key.name
                    ),
                    "type": key.inventory_metadata.get("type", "UNKNOWN") if key.inventory_metadata else "UNKNOWN",
                    "status": key.status,
                    "metadata": {
                        "reportable_type": (
                            key.inventory_metadata.get("reportable_type") if key.inventory_metadata else None
                        ),
                        "values_count": len(custom_values.get(key.inventory_id, [])),
                        "values_loaded": key.inventory_id in custom_values and len(custom_values[key.inventory_id]) > 0,
                    },
                }
                for key in custom_keys
            ],
            "customValues": custom_values,
            "audiences": [
                {
                    "id": seg.inventory_id,
                    "name": seg.name,
                    "description": seg.inventory_metadata.get("description") if seg.inventory_metadata else None,
                    "type": seg.inventory_metadata.get("type", "UNKNOWN") if seg.inventory_metadata else "UNKNOWN",
                    "size": seg.inventory_metadata.get("size") if seg.inventory_metadata else None,
                    "data_provider_name": (
                        seg.inventory_metadata.get("data_provider_name") if seg.inventory_metadata else None
                    ),
                    "segment_type": (
                        seg.inventory_metadata.get("segment_type", "UNKNOWN") if seg.inventory_metadata else "UNKNOWN"
                    ),
                    "status": seg.status,
                    "category_ids": seg.inventory_metadata.get("category_ids", []) if seg.inventory_metadata else [],
                }
                for seg in audiences
            ],
            "labels": [
                {
                    "id": label.inventory_id,
                    "name": label.name,
                    "description": label.inventory_metadata.get("description"),
                    "is_active": label.status == "ACTIVE",
                    "ad_category": label.inventory_metadata.get("ad_category"),
                    "label_type": label.inventory_metadata.get("label_type", "UNKNOWN"),
                }
                for label in labels
            ],
            "last_sync": last_sync,
        }


def create_inventory_endpoints(app):
    """Create Flask endpoints for inventory management."""

    # Check if endpoints already exist to avoid duplicate registration
    if "gam_inventory_tree" in app.view_functions:
        logger.info("Inventory endpoints already registered, skipping")
        return

    logger.info("Registering GAM inventory endpoints...")

    @app.route("/api/tenant/<tenant_id>/inventory/sync", methods=["POST"], endpoint="gam_inventory_sync")
    def sync_inventory(tenant_id):
        """Trigger inventory sync for tenant."""
        from flask import jsonify

        # Remove any existing session to start fresh
        db_session.remove()

        try:
            # Get GAM client
            from src.adapters.google_ad_manager import GoogleAdManager
            from src.core.database.models import AdapterConfig, Tenant

            stmt = select(Tenant).filter_by(tenant_id=tenant_id)
            tenant = db_session.scalars(stmt).first()
            if not tenant:
                db_session.remove()
                return jsonify({"error": "Tenant not found"}), 404

            # Check if GAM is the active adapter
            if tenant.ad_server != "google_ad_manager":
                db_session.remove()
                return jsonify({"error": "GAM not enabled for tenant"}), 400

            # Get adapter config from adapter_config table
            stmt = select(AdapterConfig).filter_by(tenant_id=tenant_id)
            adapter_config = db_session.scalars(stmt).first()

            if not adapter_config:
                db_session.remove()
                return jsonify({"error": "GAM configuration not found"}), 400

            # Build GAM config from adapter_config columns
            gam_config = {
                "enabled": True,
                "refresh_token": adapter_config.gam_refresh_token,
                "manual_approval_required": adapter_config.gam_manual_approval_required,
            }

            # Create dummy principal for client initialization
            from src.core.schemas import Principal

            principal = Principal(
                principal_id="system",
                name="System",
                access_token="system_token",  # Required field
                platform_mappings={},  # No advertiser_id needed for inventory sync
            )

            # Validate required fields for inventory sync (only network code is required)
            if not adapter_config.gam_network_code:
                return jsonify({"error": "GAM network code not configured"}), 400
            # Note: company_id and trafficker_id are only required for order operations, not inventory sync

            adapter = GoogleAdManager(
                config=gam_config,
                principal=principal,
                network_code=adapter_config.gam_network_code,
                advertiser_id=None,  # Not needed for inventory sync
                trafficker_id=None,  # Not needed for inventory sync
                tenant_id=tenant_id,
                dry_run=False,
            )

            # Perform sync
            service = GAMInventoryService(db_session)
            summary = service.sync_tenant_inventory(tenant_id, adapter.client)

            # Commit the transaction
            db_session.commit()

            return jsonify(summary)

        except Exception as e:
            logger.error(f"Inventory sync failed: {e}", exc_info=True)
            db_session.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            # Always remove the session to clean up
            db_session.remove()

    @app.route("/api/tenant/<tenant_id>/inventory/tree", endpoint="gam_inventory_tree")
    def get_inventory_tree(tenant_id):
        """Get ad unit tree for tenant."""
        from flask import jsonify

        # Remove any existing session to start fresh
        db_session.remove()

        try:
            service = GAMInventoryService(db_session)
            tree = service.get_ad_unit_tree(tenant_id)
            return jsonify(tree)

        except Exception as e:
            logger.error(f"Failed to get inventory tree: {e}", exc_info=True)
            db_session.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            db_session.remove()

    @app.route("/api/tenant/<tenant_id>/inventory/search", endpoint="gam_inventory_search")
    def search_inventory(tenant_id):
        """Search inventory with filters."""
        from flask import jsonify, request

        # Remove any existing session to start fresh
        db_session.remove()

        try:
            service = GAMInventoryService(db_session)
            results = service.search_inventory(
                tenant_id=tenant_id,
                query=request.args.get("q"),
                inventory_type=request.args.get("type"),
                status=request.args.get("status"),
            )
            return jsonify({"results": results, "total": len(results)})

        except Exception as e:
            logger.error(f"Inventory search failed: {e}", exc_info=True)
            db_session.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            db_session.remove()

    @app.route("/api/tenant/<tenant_id>/product/<product_id>/inventory")
    def get_product_inventory(tenant_id, product_id):
        """Get inventory configuration for a product."""
        from flask import jsonify

        try:
            service = GAMInventoryService(db_session)
            config = service.get_product_inventory(tenant_id, product_id)
            if not config:
                return jsonify({"error": "Product not found"}), 404
            return jsonify(config)

        except Exception as e:
            logger.error(f"Failed to get product inventory: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/tenant/<tenant_id>/product/<product_id>/inventory", methods=["POST"])
    def update_product_inventory(tenant_id, product_id):
        """Update inventory mappings for a product."""
        from flask import jsonify, request

        try:
            data = request.get_json()

            service = GAMInventoryService(db_session)
            success = service.update_product_inventory(
                tenant_id=tenant_id,
                product_id=product_id,
                ad_unit_ids=data.get("ad_unit_ids", []),
                placement_ids=data.get("placement_ids"),
                primary_ad_unit_id=data.get("primary_ad_unit_id"),
            )

            if success:
                return jsonify({"status": "success"})
            else:
                return jsonify({"error": "Update failed"}), 400

        except Exception as e:
            logger.error(f"Failed to update product inventory: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/tenant/<tenant_id>/product/<product_id>/inventory/suggest")
    def suggest_product_inventory(tenant_id, product_id):
        """Get inventory suggestions for a product."""
        from flask import jsonify

        try:
            service = GAMInventoryService(db_session)
            suggestions = service.suggest_inventory_for_product(tenant_id=tenant_id, product_id=product_id)
            return jsonify({"suggestions": suggestions, "total": len(suggestions)})

        except Exception as e:
            logger.error(f"Failed to get inventory suggestions: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/tenant/<tenant_id>/targeting/all")
    def get_all_targeting(tenant_id):
        """Get all targeting data for browsing."""
        from flask import jsonify

        try:
            service = GAMInventoryService(db_session)
            targeting_data = service.get_all_targeting_data(tenant_id)
            return jsonify(targeting_data)

        except Exception as e:
            logger.error(f"Failed to get targeting data: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/tenant/<tenant_id>/targeting/values/<key_id>", methods=["GET", "POST"])
    def fetch_custom_targeting_values(tenant_id, key_id):
        """Fetch custom targeting values for a specific key (lazy loading)."""
        from flask import jsonify, request

        try:
            # Get optional limit parameter
            max_values = request.args.get("limit", type=int, default=None)

            # Validate that the key exists in our database
            stmt = select(GAMInventory).where(
                and_(
                    GAMInventory.tenant_id == tenant_id,
                    GAMInventory.inventory_type == "custom_targeting_key",
                    GAMInventory.inventory_id == key_id,
                )
            )
            key_item = db_session.scalars(stmt).first()
            if not key_item:
                db_session.remove()
                return jsonify({"error": f"Custom targeting key {key_id} not found"}), 404

            # Get key display name for consistent path construction
            key_display_name = key_item.inventory_metadata.get("display_name", key_item.name)

            # Get GAM client
            from src.adapters.google_ad_manager import GoogleAdManager
            from src.core.database.models import AdapterConfig, Tenant

            stmt = select(Tenant).filter_by(tenant_id=tenant_id)
            tenant = db_session.scalars(stmt).first()
            if not tenant:
                db_session.remove()
                return jsonify({"error": "Tenant not found"}), 404

            # Check if GAM is the active adapter
            if tenant.ad_server != "google_ad_manager":
                db_session.remove()
                return jsonify({"error": "GAM not enabled for tenant"}), 400

            # Get adapter config
            stmt = select(AdapterConfig).filter_by(tenant_id=tenant_id)
            adapter_config = db_session.scalars(stmt).first()

            if not adapter_config:
                db_session.remove()
                return jsonify({"error": "GAM configuration not found"}), 400

            # Build GAM config
            gam_config = {
                "enabled": True,
                "refresh_token": adapter_config.gam_refresh_token,
                "manual_approval_required": adapter_config.gam_manual_approval_required,
            }

            # Create dummy principal
            from src.core.schemas import Principal

            principal = Principal(
                principal_id="system",
                name="System",
                access_token="system_token",
                platform_mappings={},
            )

            adapter = GoogleAdManager(
                config=gam_config,
                principal=principal,
                network_code=adapter_config.gam_network_code,
                advertiser_id=None,
                trafficker_id=None,
                tenant_id=tenant_id,
                dry_run=False,
            )

            # Fetch values using GAM API
            from src.adapters.gam_inventory_discovery import GAMInventoryDiscovery

            discovery = GAMInventoryDiscovery(adapter.client, tenant_id)
            values = discovery.discover_custom_targeting_values_for_key(key_id, max_values)

            # Save to database
            service = GAMInventoryService(db_session)
            sync_time = datetime.now()

            for value in values:
                service._upsert_inventory_item(
                    tenant_id=tenant_id,
                    inventory_type="custom_targeting_value",
                    inventory_id=value.id,
                    name=value.name,
                    path=[key_display_name, value.display_name],  # Use key display name for consistency
                    status=value.status,
                    inventory_metadata={
                        "custom_targeting_key_id": value.custom_targeting_key_id,
                        "display_name": value.display_name,
                        "match_type": value.match_type,
                        "key_name": key_item.name,
                        "key_display_name": key_display_name,
                    },
                    last_synced=sync_time,
                )

            db_session.commit()

            return jsonify(
                {
                    "key_id": key_id,
                    "values_count": len(values),
                    "max_values": max_values,
                    "values": [
                        {
                            "id": v.id,
                            "name": v.name,
                            "display_name": v.display_name,
                            "match_type": v.match_type,
                            "status": v.status,
                        }
                        for v in values
                    ],
                }
            )

        except Exception as e:
            logger.error(f"Failed to fetch custom targeting values: {e}", exc_info=True)
            db_session.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            db_session.remove()

    logger.info("GAM inventory endpoints successfully registered")
