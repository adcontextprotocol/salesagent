"""allow_pricing_option_deletion_when_product_deleted

Fix product deletion to work with pricing_options constraint.

The original trigger `prevent_empty_pricing_options` prevented deletion of the last
pricing option. This was blocking product deletion because:

1. Products had `cascade="all, delete-orphan"` in SQLAlchemy
2. SQLAlchemy explicitly DELETEs pricing_options BEFORE deleting the product
3. These explicit DELETEs fire the BEFORE DELETE trigger
4. The trigger blocks deletion of the last pricing_option

The solution: Remove SQLAlchemy cascade and use `passive_deletes=True` instead.
This tells SQLAlchemy to rely on database CASCADE (ON DELETE CASCADE), which
bypasses the trigger and allows product deletion to work correctly.

**Code change required**: Update Product.pricing_options relationship to use
`passive_deletes=True` instead of `cascade="all, delete-orphan"`.

This is a no-op database migration - the fix is in the Python code (models.py).

Revision ID: 2453043b72da
Revises: 47e05de8f5c2
Create Date: 2025-10-16 07:41:07.424584

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "2453043b72da"
down_revision: str | Sequence[str] | None = "47e05de8f5c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op migration - fix is in Python code (passive_deletes=True)."""
    # The fix is changing the SQLAlchemy relationship from:
    #   cascade="all, delete-orphan"
    # to:
    #   passive_deletes=True
    #
    # This tells SQLAlchemy to let the database handle CASCADE deletion,
    # which bypasses the prevent_empty_pricing_options trigger.
    pass


def downgrade() -> None:
    """No-op downgrade - fix is in Python code."""
    pass
