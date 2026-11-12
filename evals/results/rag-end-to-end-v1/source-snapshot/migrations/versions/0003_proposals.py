"""Manual jobs, durable runs/events, approval audit and idempotent local drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_proposals"
down_revision = "0002_portfolio"
branch_labels = None
depends_on = None


def owner():
    return sa.Column(
        "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


def timestamp(name="created_at"):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def run_id(*, primary_key=False):
    return sa.Column(
        "run_id",
        sa.String(36),
        sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        primary_key=primary_key,
        nullable=False,
    )


def upgrade():
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        owner(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("raw", sa.JSON, nullable=False),
        timestamp(),
        sa.UniqueConstraint("user_id", "fingerprint", name="uq_job_source"),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        owner(),
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("review", sa.JSON, nullable=True),
        sa.Column("resume", sa.JSON, nullable=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("tokens", sa.Integer, nullable=False),
        sa.Column("steps", sa.Integer, nullable=False),
        sa.Column("worker_token", sa.String(36), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        timestamp(),
        timestamp("updated_at"),
        sa.UniqueConstraint("user_id", "request_key", name="uq_run_request"),
    )
    for field in ("user_id", "job_id", "status"):
        op.create_index(f"ix_agent_runs_{field}", "agent_runs", [field])
    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer, primary_key=True),
        run_id(),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
        timestamp(),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_table(
        "approval_audit",
        sa.Column("id", sa.Integer, primary_key=True),
        run_id(),
        owner(),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("draft_digest", sa.String(64), nullable=False),
        sa.Column("decision", sa.JSON, nullable=False),
        timestamp(),
        sa.UniqueConstraint("run_id", "version", name="uq_approval_version"),
    )
    op.create_index("ix_approval_audit_run_id", "approval_audit", ["run_id"])
    op.create_table(
        "local_drafts",
        run_id(primary_key=True),
        owner(),
        sa.Column("draft", sa.JSON, nullable=False),
        sa.Column("idempotency_key", sa.String(200), unique=True, nullable=False),
        timestamp(),
    )
    op.create_index("ix_local_drafts_user_id", "local_drafts", ["user_id"])


def downgrade():
    for table in ("local_drafts", "approval_audit", "run_events", "agent_runs", "jobs"):
        op.drop_table(table)
