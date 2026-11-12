"""Approved local calendar holds and email drafts with immutable preview receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0005_workspace"
down_revision = "0004_memory"
branch_labels = None
depends_on = None


def owner():
    return sa.Column(
        "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


def time_columns():
    return [
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.add_column("approval_audit", sa.Column("preview", sa.JSON, nullable=True))
    op.create_table(
        "calendar_availability",
        sa.Column("id", sa.String(36), primary_key=True),
        owner(),
        *time_columns(),
    )
    op.create_index("ix_calendar_availability_user_id", "calendar_availability", ["user_id"])
    op.create_table(
        "workspace_writes",
        sa.Column("id", sa.String(36), primary_key=True),
        owner(),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approval_id",
            sa.Integer,
            sa.ForeignKey("approval_audit.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("arguments", sa.JSON, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "tool", "idempotency_key", name="uq_workspace_write"),
    )
    for field in ("user_id", "run_id"):
        op.create_index(f"ix_workspace_writes_{field}", "workspace_writes", [field])
    op.create_table(
        "calendar_holds",
        sa.Column(
            "id",
            sa.String(36),
            sa.ForeignKey("workspace_writes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        owner(),
        *time_columns(),
    )
    op.create_index("ix_calendar_holds_user_id", "calendar_holds", ["user_id"])


def downgrade():
    op.drop_table("calendar_holds")
    op.drop_table("workspace_writes")
    op.drop_table("calendar_availability")
    op.drop_column("approval_audit", "preview")
