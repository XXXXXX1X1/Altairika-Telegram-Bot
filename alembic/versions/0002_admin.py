"""Admin: user_questions fields + analytics_events table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_questions", sa.Column("username", sa.String(255), nullable=True))
    op.add_column("user_questions", sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_questions", sa.Column("answered_by", sa.BigInteger(), nullable=True))
    op.add_column("user_questions", sa.Column("answer_text", sa.Text(), nullable=True))

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analytics_events_event_type", "analytics_events", ["event_type"])
    op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])
    op.create_index("ix_analytics_events_user", "analytics_events", ["telegram_user_id"])


def downgrade() -> None:
    op.drop_index("ix_analytics_events_user", "analytics_events")
    op.drop_index("ix_analytics_events_created_at", "analytics_events")
    op.drop_index("ix_analytics_events_event_type", "analytics_events")
    op.drop_table("analytics_events")

    op.drop_column("user_questions", "answer_text")
    op.drop_column("user_questions", "answered_by")
    op.drop_column("user_questions", "answered_at")
    op.drop_column("user_questions", "username")
