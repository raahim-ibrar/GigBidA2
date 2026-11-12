"""Edit observations, trusted outcome observations and a durable memory-promotion ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0004_memory"
down_revision = "0003_proposals"
branch_labels = None
depends_on = None


def owner(*, primary_key=False):
    return sa.Column(
        "user_id",
        sa.String(36),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=primary_key,
    )


def run():
    return sa.Column(
        "run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )


def timestamp():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade():
    op.create_table(
        "draft_edits",
        sa.Column(
            "audit_id",
            sa.Integer,
            sa.ForeignKey("approval_audit.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        owner(),
        run(),
        sa.Column("before_text", sa.Text, nullable=False),
        sa.Column("after_text", sa.Text, nullable=False),
        sa.Column("diff", sa.Text, nullable=False),
        sa.Column("patterns", sa.JSON, nullable=False),
        timestamp(),
    )
    for field in ("user_id", "run_id"):
        op.create_index(f"ix_draft_edits_{field}", "draft_edits", [field])
    op.create_table(
        "outcome_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        owner(),
        run(),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        timestamp(),
        sa.UniqueConstraint("user_id", "event_id", name="uq_outcome_event"),
    )
    for field in ("user_id", "run_id"):
        op.create_index(f"ix_outcome_observations_{field}", "outcome_observations", [field])
    op.create_table(
        "memory_records",
        owner(primary_key=True),
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("synced", sa.Boolean, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for table in ("memory_records", "outcome_observations", "draft_edits"):
        op.drop_table(table)
