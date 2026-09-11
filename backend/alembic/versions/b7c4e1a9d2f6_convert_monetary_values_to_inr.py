"""Convert stored monetary values from crore semantics to INR.

This is a one-time semantic data conversion. Existing project estimates and
contract values were stored as crores, while the application convention is now
Indian rupees. One crore equals 10,000,000 INR. Column types and audit history
are intentionally unchanged.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b7c4e1a9d2f6"
down_revision: Union[str, Sequence[str], None] = "019e904dacbb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONVERSION_FACTOR = "CAST(10000000 AS NUMERIC)"


def upgrade() -> None:
    """Convert crore-scale project and contract values to INR."""
    op.execute(
        f"""
        UPDATE projects
        SET total_estimated_cost = total_estimated_cost * {CONVERSION_FACTOR}
        """
    )
    op.execute(
        f"""
        UPDATE contracts
        SET contract_value = contract_value * {CONVERSION_FACTOR}
        """
    )


def downgrade() -> None:
    """Reverse the one-time INR conversion back to crore semantics."""
    op.execute(
        f"""
        UPDATE projects
        SET total_estimated_cost = total_estimated_cost / {CONVERSION_FACTOR}
        """
    )
    op.execute(
        f"""
        UPDATE contracts
        SET contract_value = contract_value / {CONVERSION_FACTOR}
        """
    )