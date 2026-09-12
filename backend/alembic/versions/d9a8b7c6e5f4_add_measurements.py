"""Add measurements table.

Revision ID: d9a8b7c6e5f4
Revises: c4d8e2f1a907
Create Date: 2026-09-12 12:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d9a8b7c6e5f4"
down_revision: Union[str, Sequence[str], None] = "c4d8e2f1a907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("boq_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("measurement_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="Draft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_measurements_quantity_nonnegative"),
        sa.ForeignKeyConstraint(["boq_item_id"], ["boq_items.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_measurements_boq_item_id", "measurements", ["boq_item_id"], unique=False)
    op.create_index("ix_measurements_status", "measurements", ["status"], unique=False)
    op.create_index("ix_measurements_measurement_date", "measurements", ["measurement_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_measurements_measurement_date", table_name="measurements")
    op.drop_index("ix_measurements_status", table_name="measurements")
    op.drop_index("ix_measurements_boq_item_id", table_name="measurements")
    op.drop_table("measurements")

