"""Bounded manual run recovery and persisted saved-search polling settings."""

import sqlalchemy as sa
from alembic import op

revision = "0007_recovery_schedules"
down_revision = "0006_conversations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_runs", sa.Column("retry_count", sa.Integer, nullable=False, server_default="0")
    )
    op.add_column(
        "agent_runs", sa.Column("retryable", sa.Boolean, nullable=False, server_default=sa.false())
    )
    op.create_table(
        "search_schedules",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("interval_minutes", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
    )
    op.create_index("ix_search_schedules_next_check_at", "search_schedules", ["next_check_at"])


def downgrade():
    op.drop_table("search_schedules")
    op.drop_column("agent_runs", "retryable")
    op.drop_column("agent_runs", "retry_count")
