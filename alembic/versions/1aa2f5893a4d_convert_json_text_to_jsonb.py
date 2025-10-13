"""convert_json_text_to_jsonb

Revision ID: 1aa2f5893a4d
Revises: ab57bdcf4bd8
Create Date: 2025-10-13 10:46:49.851222

Convert all JSON columns from TEXT to native PostgreSQL JSONB.

Architecture Decision:
    Per CLAUDE.md, this codebase is PostgreSQL-only (no SQLite support).
    JSONType now uses native JSONB for optimal performance and features.

This migration converts all TEXT columns storing JSON to native JSONB:
    - Better performance (binary format vs TEXT parsing)
    - Smaller storage (compressed binary)
    - Native GIN indexes (no CAST needed)
    - JSONB operators work directly (@>, ?, ->, etc.)

Tables affected: ~48 columns across 20+ tables

Safety:
    - Uses USING clause to validate and convert JSON
    - Will fail if any column contains invalid JSON
    - Atomic operation (all-or-nothing)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1aa2f5893a4d'
down_revision: Union[str, Sequence[str], None] = 'eef85c5fe627'  # After XOR constraint, before GIN index
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Complete mapping of all tables and their JSON columns
# Format: {"table_name": ["column1", "column2", ...]}
JSON_COLUMNS = {
    "tenants": [
        "authorized_emails",
        "authorized_domains",
        "auto_approve_formats",
        "policy_settings",
        "signals_agent_config",
    ],
    "creative_formats": [
        "specs",
        "modifications",
        "platform_config",
    ],
    "products": [
        "formats",
        "targeting_template",
        "measurement",
        "creative_policy",
        "price_guidance",
        "countries",
        "implementation_config",
        "properties",
        "property_tags",
    ],
    "pricing_options": [
        "price_guidance",
        "parameters",
    ],
    "principals": [
        "platform_mappings",
    ],
    "media_buys": [
        "config",
        "packages",
    ],
    "creatives": [
        "asset_properties",
    ],
    "contexts": [
        "data",
        "metadata",
    ],
    "workflow_steps": [
        "request_data",
        "response_data",
        "transaction_details",
        "comments",
    ],
    "audit_logs": [
        "details",
    ],
    "creative_associations": [
        "mapping",
    ],
    "authorized_properties": [
        "identifiers",
        "verification_metadata",
    ],
    "webhook_deliveries": [
        "payload",
        "response_body",
    ],
    "creative_reviews": [
        "review_result",
    ],
    "gam_ad_units": [
        "sizes",
        "targeting",
    ],
    "gam_placements": [
        "targeting",
    ],
    "gam_orders": [
        "external_metadata",
    ],
    "gam_line_items": [
        "targeting",
        "creative_placeholders",
    ],
}


def upgrade() -> None:
    """Convert all TEXT JSON columns to native JSONB."""
    connection = op.get_bind()

    converted_count = 0

    for table_name, columns in JSON_COLUMNS.items():
        if not columns:
            continue

        for column_name in columns:
            try:
                # Check if table and column exist before converting
                result = connection.execute(sa.text(
                    f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}'
                      AND column_name = '{column_name}'
                    """
                ))
                row = result.fetchone()

                if row is None:
                    print(f"⚠️  Skipping {table_name}.{column_name} - column doesn't exist")
                    continue

                current_type = row[1]

                # Skip if already JSONB
                if current_type == 'jsonb':
                    print(f"✓ {table_name}.{column_name} already JSONB")
                    continue

                # Convert TEXT to JSONB using CAST
                # USING clause validates JSON and converts
                connection.execute(sa.text(
                    f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN {column_name}
                    TYPE jsonb USING {column_name}::jsonb
                    """
                ))

                converted_count += 1
                print(f"✅ Converted {table_name}.{column_name} from {current_type} to JSONB")

            except Exception as e:
                print(f"❌ Failed to convert {table_name}.{column_name}: {e}")
                raise

    print(f"\n🎉 Successfully converted {converted_count} columns from TEXT to JSONB")
    print("   All JSON columns now use native PostgreSQL JSONB storage")


def downgrade() -> None:
    """Convert JSONB columns back to TEXT (not recommended)."""
    connection = op.get_bind()

    for table_name, columns in JSON_COLUMNS.items():
        if not columns:
            continue

        for column_name in columns:
            try:
                # Check if column exists and is JSONB
                result = connection.execute(sa.text(
                    f"""
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}'
                      AND column_name = '{column_name}'
                    """
                ))
                row = result.fetchone()

                if row is None or row[0] != 'jsonb':
                    continue

                # Convert JSONB back to TEXT
                connection.execute(sa.text(
                    f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN {column_name}
                    TYPE text USING {column_name}::text
                    """
                ))

                print(f"⚠️  Downgraded {table_name}.{column_name} from JSONB to TEXT")

            except Exception as e:
                print(f"❌ Failed to downgrade {table_name}.{column_name}: {e}")
                raise

    print("\n⚠️  WARNING: Downgrade complete. TEXT storage is less efficient than JSONB.")
