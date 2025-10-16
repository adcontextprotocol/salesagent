"""fix delivery_type values hyphen to underscore

Revision ID: f9300bf2246d
Revises: 2453043b72da
Create Date: 2025-10-16 10:00:09.134045

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9300bf2246d"
down_revision: str | Sequence[str] | None = "2453043b72da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Fix delivery_type values from hyphen to underscore to match AdCP spec.

    AdCP spec defines delivery_type enum as:
    - "guaranteed"
    - "non_guaranteed" (underscore)

    But database has "non-guaranteed" (hyphen) which causes validation errors.
    """
    # Update all products with hyphenated delivery_type to underscored version
    op.execute(
        """
        UPDATE products
        SET delivery_type = 'non_guaranteed'
        WHERE delivery_type = 'non-guaranteed'
        """
    )


def downgrade() -> None:
    """Revert delivery_type values back to hyphenated form."""
    # Revert underscore back to hyphen
    op.execute(
        """
        UPDATE products
        SET delivery_type = 'non-guaranteed'
        WHERE delivery_type = 'non_guaranteed'
        """
    )
