"""migrate_creatives_to_v24_format

Revision ID: 4b8c3ffb6ae7
Revises: ed248e24dfc0
Create Date: 2025-11-17 10:23:27.566712

Migration to convert legacy creative format to AdCP v2.4 format.

Legacy format (top-level fields in data JSON):
{
  "url": "https://example.com/image.jpg",
  "width": 728,
  "height": 90,
  "click_url": "https://example.com/click",
  "snippet": "<html>...</html>",
  ...other fields
}

AdCP v2.4 format (assets object in data JSON):
{
  "assets": {
    "primary": {
      "asset_type": "image",
      "url": "https://example.com/image.jpg",
      "width": 728,
      "height": 90
    },
    "clickthrough": {
      "asset_type": "url",
      "url": "https://example.com/click",
      "url_type": "clickthrough"
    }
  },
  ...other fields (excluding legacy fields)
}
"""

from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "4b8c3ffb6ae7"
down_revision: Union[str, Sequence[str], None] = "ed248e24dfc0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Transform legacy creative format to AdCP v2.4 format."""

    # Use raw SQL to update JSONB data column
    # This migration transforms legacy creatives to v2.4 format by:
    # 1. Creating an "assets" object if it doesn't exist
    # 2. Moving url/width/height to a "primary" image asset
    # 3. Moving click_url to a "clickthrough" url asset
    # 4. Moving snippet to an "html" asset
    # 5. Removing legacy top-level fields

    conn = op.get_bind()

    # First, identify legacy creatives (those without assets object or with legacy fields)
    result = conn.execute(
        text(
            """
        SELECT creative_id, data
        FROM creatives
        WHERE
            -- Legacy format: has top-level fields but no assets object
            (data ? 'url' OR data ? 'width' OR data ? 'height' OR data ? 'click_url' OR data ? 'snippet')
            AND (
                NOT (data ? 'assets')
                OR jsonb_typeof(data->'assets') != 'object'
            )
    """
        )
    )

    legacy_creatives = result.fetchall()

    print(f"Found {len(legacy_creatives)} legacy creatives to migrate")

    # Transform each legacy creative
    for creative_id, data in legacy_creatives:
        # Build assets object
        assets = {}

        # Extract primary asset (image/video)
        url = data.get("url") or data.get("media_url")
        width = data.get("width")
        height = data.get("height")

        if url:
            # Determine asset type from URL or default to image
            asset_type = "image"
            if url and isinstance(url, str):
                lower_url = url.lower()
                if any(ext in lower_url for ext in [".mp4", ".webm", ".mov", ".avi"]):
                    asset_type = "video"

            # Create primary asset
            primary_asset = {"asset_type": asset_type, "url": url}

            # Add dimensions if available
            if width is not None:
                try:
                    primary_asset["width"] = int(width) if not isinstance(width, int) else width
                except (ValueError, TypeError):
                    pass

            if height is not None:
                try:
                    primary_asset["height"] = int(height) if not isinstance(height, int) else height
                except (ValueError, TypeError):
                    pass

            assets["primary"] = primary_asset

        # Extract click URL
        click_url = data.get("click_url") or data.get("clickthrough_url")
        if click_url:
            assets["clickthrough"] = {"asset_type": "url", "url": click_url, "url_type": "clickthrough"}

        # Extract snippet (HTML)
        snippet = data.get("snippet")
        if snippet:
            assets["html_content"] = {"asset_type": "html", "content": snippet}

        # Extract template variables as text assets
        template_vars = data.get("template_variables")
        if template_vars and isinstance(template_vars, dict):
            for key, value in template_vars.items():
                asset_id = f"text_{key}"
                assets[asset_id] = {"asset_type": "text", "content": str(value), "variable_name": key}

        # Create new data object with assets
        new_data = dict(data)
        new_data["assets"] = assets

        # Remove legacy fields
        legacy_fields = [
            "url",
            "media_url",
            "width",
            "height",
            "click_url",
            "clickthrough_url",
            "snippet",
            "template_variables",
        ]
        for field in legacy_fields:
            new_data.pop(field, None)

        # Update database (convert dict to JSON string for PostgreSQL JSONB)
        conn.execute(
            text(
                """
                UPDATE creatives
                SET data = :new_data::jsonb
                WHERE creative_id = :creative_id
            """
            ),
            {"new_data": json.dumps(new_data), "creative_id": creative_id},
        )

        print(f"Migrated creative {creative_id}")

    print(f"Migration complete: transformed {len(legacy_creatives)} creatives to v2.4 format")


def downgrade() -> None:
    """Revert AdCP v2.4 format back to legacy format.

    This downgrade extracts fields from the assets object back to top-level fields.
    Note: Some information may be lost in the conversion (e.g., multiple assets).
    """

    conn = op.get_bind()

    # Find v2.4 creatives (those with assets object)
    result = conn.execute(
        text(
            """
        SELECT creative_id, data
        FROM creatives
        WHERE
            data ? 'assets'
            AND jsonb_typeof(data->'assets') = 'object'
    """
        )
    )

    v24_creatives = result.fetchall()

    print(f"Found {len(v24_creatives)} v2.4 creatives to downgrade")

    # Transform each v2.4 creative back to legacy format
    for creative_id, data in v24_creatives:
        assets = data.get("assets", {})

        # Create new data object
        new_data = dict(data)

        # Extract primary asset
        primary = assets.get("primary", {})
        if primary.get("url"):
            new_data["url"] = primary["url"]
        if primary.get("width"):
            new_data["width"] = primary["width"]
        if primary.get("height"):
            new_data["height"] = primary["height"]

        # Extract clickthrough URL
        clickthrough = assets.get("clickthrough", {})
        if clickthrough.get("url"):
            new_data["click_url"] = clickthrough["url"]

        # Extract HTML content
        html_content = assets.get("html_content", {})
        if html_content.get("content"):
            new_data["snippet"] = html_content["content"]

        # Extract text assets back to template_variables
        template_vars = {}
        for asset_id, asset in assets.items():
            if isinstance(asset, dict) and asset.get("asset_type") == "text":
                var_name = asset.get("variable_name") or asset_id.replace("text_", "")
                template_vars[var_name] = asset.get("content", "")

        if template_vars:
            new_data["template_variables"] = template_vars

        # Remove assets object
        new_data.pop("assets", None)

        # Update database (convert dict to JSON string for PostgreSQL JSONB)
        conn.execute(
            text(
                """
                UPDATE creatives
                SET data = :new_data::jsonb
                WHERE creative_id = :creative_id
            """
            ),
            {"new_data": json.dumps(new_data), "creative_id": creative_id},
        )

        print(f"Downgraded creative {creative_id}")

    print(f"Downgrade complete: reverted {len(v24_creatives)} creatives to legacy format")
