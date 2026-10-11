"""Add vector embeddings to document chunks."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "e1a2b3c4d5f6"
down_revision: Union[str, None] = "aadf0813e992"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "embedding")