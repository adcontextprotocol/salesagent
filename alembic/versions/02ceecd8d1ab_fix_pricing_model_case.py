"""fix_pricing_model_case

Convert uppercase pricing_model values to lowercase to match AdCP schema.
AdCP spec requires lowercase pricing models (cpm, cpcv, cpp, cpc, cpv, flat_rate).

Revision ID: 02ceecd8d1ab
Revises: b61ff75713c0
Create Date: 2025-10-15 07:20:46.905113

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '02ceecd8d1ab'
down_revision: Union[str, Sequence[str], None] = 'b61ff75713c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert pricing_model values to lowercase."""
    conn = op.get_bind()

    # Update all uppercase pricing models to lowercase
    result = conn.execute(
        text(
            """
            UPDATE pricing_options
            SET pricing_model = LOWER(pricing_model)
            WHERE pricing_model != LOWER(pricing_model)
            """
        )
    )

    print(f"✅ Converted {result.rowcount} pricing_model values to lowercase")


def downgrade() -> None:
    """Convert pricing_model values back to uppercase (not recommended)."""
    conn = op.get_bind()

    # Convert back to uppercase (only for rollback purposes)
    result = conn.execute(
        text(
            """
            UPDATE pricing_options
            SET pricing_model = UPPER(pricing_model)
            WHERE pricing_model IN ('cpm', 'cpcv', 'cpp', 'cpc', 'cpv')
            """
        )
    )

    print(f"✅ Converted {result.rowcount} pricing_model values to uppercase (downgrade)")
