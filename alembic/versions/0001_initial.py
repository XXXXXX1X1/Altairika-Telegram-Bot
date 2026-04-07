"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("order", sa.Integer(), server_default="0"),
        sa.Column("item_count", sa.Integer(), server_default="0"),
    )

    op.create_table(
        "catalog_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("short_description", sa.Text()),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id")),
        sa.Column("tags", sa.Text()),
        sa.Column("image_url", sa.String(1000)),
        sa.Column("price", sa.String(500)),
        sa.Column("duration", sa.String(100)),
        sa.Column("age_rating", sa.String(20)),
        sa.Column("url", sa.String(1000)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "bot_users",
        sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(255)),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column("language_code", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50), nullable=False),
        sa.Column("lead_type", sa.Enum("booking", "franchise", "contact", name="leadtype"), nullable=False),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id")),
        sa.Column("preferred_time", sa.String(255)),
        sa.Column("city", sa.String(255)),
        sa.Column("status", sa.Enum("new", "in_progress", "done", name="leadstatus"), server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "faq_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )

    op.create_table(
        "faq_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("faq_topics.id"), nullable=False),
        sa.Column("question", sa.String(1000), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )

    op.create_table(
        "user_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_answered", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "franchise_content",
        sa.Column(
            "section",
            sa.Enum("pitch", "conditions", "support", "faq", name="franchisesection"),
            primary_key=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "competitors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("website", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "comparison_parameters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("altairika_value", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), server_default="0"),
    )

    op.create_table(
        "comparison_values",
        sa.Column("parameter_id", sa.Integer(), sa.ForeignKey("comparison_parameters.id"), primary_key=True),
        sa.Column("competitor_id", sa.Integer(), sa.ForeignKey("competitors.id"), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "rating",
            sa.Enum("good", "neutral", "bad", name="comparisonrating"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("comparison_values")
    op.drop_table("comparison_parameters")
    op.drop_table("competitors")
    op.drop_table("franchise_content")
    op.drop_table("user_questions")
    op.drop_table("faq_items")
    op.drop_table("faq_topics")
    op.drop_table("leads")
    op.drop_table("bot_users")
    op.drop_table("catalog_items")
    op.drop_table("categories")
    op.execute("DROP TYPE IF EXISTS leadtype")
    op.execute("DROP TYPE IF EXISTS leadstatus")
    op.execute("DROP TYPE IF EXISTS franchisesection")
    op.execute("DROP TYPE IF EXISTS comparisonrating")
