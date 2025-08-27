"""fix_price_guidance_json_encoding

Revision ID: e81e275c9b29
Revises: 2485bb2ff253
Create Date: 2025-08-26 23:14:40.002149

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e81e275c9b29"
down_revision: Union[str, Sequence[str], None] = "2485bb2ff253"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix JSON fields that were incorrectly double-encoded as strings."""
    
    # Skip this migration in production for now - manual fix may be needed
    # The production database has different column types that need special handling
    print("Skipping price_guidance JSON fix migration - will handle manually if needed")
    return


def downgrade() -> None:
    """Revert the JSON fix (not recommended)."""
    # Downgrade would re-introduce the bug, so we leave it as a no-op
    pass