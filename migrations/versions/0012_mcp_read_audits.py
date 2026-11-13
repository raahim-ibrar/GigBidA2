"""Tenant-scoped, redacted MCP read attempts and completion receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0012_mcp_read_audits"
down_revision = "0011_upwork_oauth"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "mcp_read_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")),
        sa.Column("server", sa.String(40), nullable=False),
        sa.Column("tool", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("elapsed_seconds", sa.Float()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    for field in ("user_id", "run_id", "started_at"):
        op.create_index(f"ix_mcp_read_audits_{field}", "mcp_read_audits", [field])


def downgrade():
    op.drop_table("mcp_read_audits")
