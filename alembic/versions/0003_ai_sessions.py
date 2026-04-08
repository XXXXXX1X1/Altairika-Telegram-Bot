"""AI sessions table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_sessions",
        sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
        sa.Column("active_intent", sa.String(100), nullable=True),
        sa.Column("state_json", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_sessions_expires_at", "ai_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_sessions_expires_at", "ai_sessions")
    op.drop_table("ai_sessions")
