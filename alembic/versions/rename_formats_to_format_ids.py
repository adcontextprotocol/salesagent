"""rename_formats_to_format_ids

Renames database columns to match AdCP spec naming:
- products.formats → products.format_ids
- inventory_profiles.formats → inventory_profiles.format_ids
- tenants.auto_approve_formats → tenants.auto_approve_format_ids

Adds PostgreSQL CHECK constraints to validate FormatId structure per AdCP spec:
- Each format_id must be an object with "agent_url" and "id" properties
- Both properties are required and must be strings
- No additional properties allowed

This ensures database-level type safety matching the AdCP FormatId schema:
{
  "type": "object",
  "properties": {
    "agent_url": {"type": "string"},
    "id": {"type": "string"}
  },
  "required": ["agent_url", "id"],
  "additionalProperties": false
}

Revision ID: {TIMESTAMP}
Revises: {PREVIOUS}
Create Date: {DATE}

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "rename_formats_to_format_ids"
down_revision: str | Sequence[str] | None = "039d59477ab4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename formats columns to format_ids and add validation constraints."""

    # ========================================================================
    # 1. Rename columns
    # ========================================================================

    print("\n📝 Renaming columns to match AdCP spec...")

    # Products table
    print("  → products.formats → products.format_ids")
    op.alter_column("products", "formats", new_column_name="format_ids")

    # Inventory profiles table
    print("  → inventory_profiles.formats → inventory_profiles.format_ids")
    op.alter_column("inventory_profiles", "formats", new_column_name="format_ids")

    # Tenants table
    print("  → tenants.auto_approve_formats → tenants.auto_approve_format_ids")
    op.alter_column("tenants", "auto_approve_formats", new_column_name="auto_approve_format_ids")

    # ========================================================================
    # 2. Transform existing data to new FormatId structure
    # ========================================================================

    print("\n🔄 Transforming existing format data to AdCP-compliant structure...")

    # Transform products.format_ids: extract format_id → id, preserve agent_url
    transform_products = """
    UPDATE products
    SET format_ids = (
        SELECT jsonb_agg(
            jsonb_build_object(
                'agent_url', COALESCE(elem->>'agent_url', 'https://creatives.adcontextprotocol.org'),
                'id', COALESCE(elem->>'format_id', elem->>'id')
            )
        )
        FROM jsonb_array_elements(format_ids) elem
    )
    WHERE format_ids IS NOT NULL
      AND jsonb_typeof(format_ids) = 'array'
      AND jsonb_array_length(format_ids) > 0
      -- Only transform if not already in correct format (has 'id' key, not 'format_id')
      AND EXISTS (
          SELECT 1 FROM jsonb_array_elements(format_ids) elem
          WHERE elem ? 'format_id' OR NOT (elem ? 'id')
      );
    """
    print("  → Transforming products.format_ids...")
    result = op.get_bind().execute(text(transform_products))
    print(f"    ✓ Transformed {result.rowcount} product records")

    # Transform inventory_profiles.format_ids: preserve agent_url
    transform_inventory = """
    UPDATE inventory_profiles
    SET format_ids = (
        SELECT jsonb_agg(
            jsonb_build_object(
                'agent_url', COALESCE(elem->>'agent_url', 'https://creatives.adcontextprotocol.org'),
                'id', COALESCE(elem->>'format_id', elem->>'id')
            )
        )
        FROM jsonb_array_elements(format_ids) elem
    )
    WHERE format_ids IS NOT NULL
      AND jsonb_typeof(format_ids) = 'array'
      AND jsonb_array_length(format_ids) > 0
      -- Only transform if not already in correct format (has 'id' key, not 'format_id')
      AND EXISTS (
          SELECT 1 FROM jsonb_array_elements(format_ids) elem
          WHERE elem ? 'format_id' OR NOT (elem ? 'id')
      );
    """
    print("  → Transforming inventory_profiles.format_ids...")
    result = op.get_bind().execute(text(transform_inventory))
    print(f"    ✓ Transformed {result.rowcount} inventory profile records")

    print("  ✅ Data transformation complete")

    # ========================================================================
    # 3. Add JSON schema validation constraints
    # ========================================================================

    print("\n🔒 Adding JSON schema validation constraints...")

    # PostgreSQL function to validate FormatId structure
    # This validates against the AdCP spec:
    # - Must be array of objects
    # - Each object must have "agent_url" and "id" properties (both strings)
    # - No additional properties allowed
    validation_function = """
    CREATE OR REPLACE FUNCTION validate_format_ids(format_ids_json jsonb)
    RETURNS boolean AS $$
    DECLARE
        format_id jsonb;
        keys text[];
    BEGIN
        -- Must be array
        IF jsonb_typeof(format_ids_json) != 'array' THEN
            RAISE EXCEPTION 'format_ids must be a JSON array, got: %', jsonb_typeof(format_ids_json);
        END IF;

        -- Validate each FormatId object
        FOR format_id IN SELECT * FROM jsonb_array_elements(format_ids_json)
        LOOP
            -- Must be object
            IF jsonb_typeof(format_id) != 'object' THEN
                RAISE EXCEPTION 'Each format_id must be an object, got: %', jsonb_typeof(format_id);
            END IF;

            -- Must have exactly 2 keys: agent_url and id
            SELECT array_agg(key) INTO keys FROM jsonb_object_keys(format_id) key;
            IF array_length(keys, 1) != 2 OR NOT (keys @> ARRAY['agent_url', 'id']) THEN
                RAISE EXCEPTION 'FormatId must have exactly "agent_url" and "id" properties, got: %', keys;
            END IF;

            -- agent_url must be string
            IF jsonb_typeof(format_id->'agent_url') != 'string' THEN
                RAISE EXCEPTION 'FormatId.agent_url must be a string, got: %', jsonb_typeof(format_id->'agent_url');
            END IF;

            -- id must be string
            IF jsonb_typeof(format_id->'id') != 'string' THEN
                RAISE EXCEPTION 'FormatId.id must be a string, got: %', jsonb_typeof(format_id->'id');
            END IF;

            -- Validate agent_url is not empty
            IF length(format_id->>'agent_url') = 0 THEN
                RAISE EXCEPTION 'FormatId.agent_url cannot be empty string';
            END IF;

            -- Validate id is not empty
            IF length(format_id->>'id') = 0 THEN
                RAISE EXCEPTION 'FormatId.id cannot be empty string';
            END IF;
        END LOOP;

        RETURN true;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """

    print("  → Creating validation function: validate_format_ids()")
    op.execute(validation_function)

    # Add CHECK constraints to tables
    print("  → Adding CHECK constraint to products.format_ids")
    op.create_check_constraint(
        "products_format_ids_valid",
        "products",
        "validate_format_ids(format_ids)",
    )

    print("  → Adding CHECK constraint to inventory_profiles.format_ids")
    op.create_check_constraint(
        "inventory_profiles_format_ids_valid",
        "inventory_profiles",
        "validate_format_ids(format_ids)",
    )

    # Note: tenants.auto_approve_format_ids can be NULL or array of strings (just IDs, not full FormatId objects)
    # Create a simpler validation function for array of strings
    print("  → Creating validation function for auto_approve_format_ids")
    string_array_validation = """
    CREATE OR REPLACE FUNCTION validate_string_array(arr jsonb)
    RETURNS boolean AS $$
    DECLARE
        elem jsonb;
    BEGIN
        -- NULL is valid
        IF arr IS NULL THEN
            RETURN true;
        END IF;

        -- Must be array
        IF jsonb_typeof(arr) != 'array' THEN
            RAISE EXCEPTION 'auto_approve_format_ids must be an array, got: %', jsonb_typeof(arr);
        END IF;

        -- Each element must be string
        FOR elem IN SELECT * FROM jsonb_array_elements(arr)
        LOOP
            IF jsonb_typeof(elem) != 'string' THEN
                RAISE EXCEPTION 'Each element must be a string, got: %', jsonb_typeof(elem);
            END IF;
        END LOOP;

        RETURN true;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """
    op.execute(string_array_validation)

    print("  → Adding CHECK constraint to tenants.auto_approve_format_ids")
    op.create_check_constraint(
        "tenants_auto_approve_format_ids_valid",
        "tenants",
        "validate_string_array(auto_approve_format_ids)",
    )

    print("\n✅ Migration complete! format_ids columns now have database-level type safety.")
    print("   All format_ids must match AdCP FormatId spec: {agent_url: string, id: string}")


def downgrade() -> None:
    """Revert column renames and remove validation constraints."""

    print("\n⏪ Reverting migration...")

    # Remove CHECK constraints
    print("  → Removing CHECK constraints")
    op.drop_constraint("products_format_ids_valid", "products")
    op.drop_constraint("inventory_profiles_format_ids_valid", "inventory_profiles")
    op.drop_constraint("tenants_auto_approve_format_ids_valid", "tenants")

    # Drop validation functions
    print("  → Dropping validation functions")
    op.execute("DROP FUNCTION IF EXISTS validate_format_ids(jsonb)")
    op.execute("DROP FUNCTION IF EXISTS validate_string_array(jsonb)")

    # Rename columns back
    print("  → Renaming columns back to original names")
    op.alter_column("products", "format_ids", new_column_name="formats")
    op.alter_column("inventory_profiles", "format_ids", new_column_name="formats")
    op.alter_column("tenants", "auto_approve_format_ids", new_column_name="auto_approve_formats")

    print("\n✅ Downgrade complete! Reverted to original column names.")
