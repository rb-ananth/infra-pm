"""Add BOQ, revision, and item foundation tables.

This migration establishes the Contract -> BOQ -> Revision -> Item structure.
BOQ item rates and amounts use INR semantics and are stored as PostgreSQL
NUMERIC values. Item amounts are calculated by the application service.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4d8e2f1a907"
down_revision: Union[str, Sequence[str], None] = "b7c4e1a9d2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "boqs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("boq_number", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="Draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "boq_number"),
    )
    op.create_index("ix_boqs_contract_id", "boqs", ["contract_id"], unique=False)

    op.create_table(
        "boq_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("boq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("revision_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="Draft"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_number >= 1", name="ck_boq_revisions_revision_number_positive"),
        sa.ForeignKeyConstraint(["boq_id"], ["boqs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("boq_id", "revision_number"),
    )
    op.create_index("ix_boq_revisions_boq_id", "boq_revisions", ["boq_id"], unique=False)

    op.create_table(
        "boq_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_code", sa.String(length=100), nullable=False),
        sa.Column("item_number", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("rate", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_boq_items_quantity_nonnegative"),
        sa.CheckConstraint("rate >= 0", name="ck_boq_items_rate_nonnegative"),
        sa.CheckConstraint("amount >= 0", name="ck_boq_items_amount_nonnegative"),
        sa.ForeignKeyConstraint(["revision_id"], ["boq_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "item_number"),
    )
    op.create_index("ix_boq_items_revision_id", "boq_items", ["revision_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_boq_items_revision_id", table_name="boq_items")
    op.drop_table("boq_items")
    op.drop_index("ix_boq_revisions_boq_id", table_name="boq_revisions")
    op.drop_table("boq_revisions")
    op.drop_index("ix_boqs_contract_id", table_name="boqs")
    op.drop_table("boqs")