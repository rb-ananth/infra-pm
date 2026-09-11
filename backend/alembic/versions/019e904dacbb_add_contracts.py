"""add contracts

Revision ID: 019e904dacbb
Revises: 0001_sprint1
Create Date: 2026-09-12 00:28:01.945271
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "019e904dacbb"
down_revision: Union[str, Sequence[str], None] = "0001_sprint1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_number", sa.String(length=100), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contractor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "contract_type",
            sa.String(length=50),
            nullable=False,
            server_default="Works",
        ),
        sa.Column("award_date", sa.Date(), nullable=False),
        sa.Column(
            "contract_value",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("original_completion_date", sa.Date(), nullable=False),
        sa.Column("current_completion_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="Draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_number"),
    )

    op.create_index(
        "ix_contracts_contract_number",
        "contracts",
        ["contract_number"],
        unique=False,
    )
    op.create_index(
        "ix_contracts_project_id",
        "contracts",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_contracts_contractor_id",
        "contracts",
        ["contractor_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contracts_contractor_id",
        table_name="contracts",
    )
    op.drop_index(
        "ix_contracts_project_id",
        table_name="contracts",
    )
    op.drop_index(
        "ix_contracts_contract_number",
        table_name="contracts",
    )
    op.drop_table("contracts")
