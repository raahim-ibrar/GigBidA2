"""Trusted proposal lifecycle receipts; local drafts never imply submission."""

import sqlalchemy as sa
from alembic import op

revision = "0008_pipeline"
down_revision = "0007_recovery_schedules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pipeline_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("proposal_id", sa.String(200), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connects_spent", sa.Integer, nullable=True),
        sa.UniqueConstraint("user_id", "event_id", name="uq_pipeline_provider_event"),
    )
    op.create_index("ix_pipeline_events_user_id", "pipeline_events", ["user_id"])
    op.create_index("ix_pipeline_events_run_id", "pipeline_events", ["run_id"])


def downgrade():
    op.drop_table("pipeline_events")
