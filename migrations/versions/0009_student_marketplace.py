"""Per-user student-simulator connections and immutable approved effect receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0009_student_marketplace"
down_revision = "0008_pipeline"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("client_conversations", sa.Column("provider_id", sa.String(200), nullable=True))
    op.create_table(
        "marketplace_connections",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("event_cursor", sa.Integer, nullable=False),
        sa.Column("error", sa.String(200), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "marketplace_writes",
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
        sa.Column("approval_id", sa.Integer, sa.ForeignKey("approval_audit.id"), nullable=False),
        sa.Column("tool", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("arguments", sa.JSON, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("connects_spent", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_marketplace_effect"),
    )
    op.create_index("ix_marketplace_writes_user_id", "marketplace_writes", ["user_id"])
    op.create_index("ix_marketplace_writes_run_id", "marketplace_writes", ["run_id"])


def downgrade():
    op.drop_table("marketplace_writes")
    op.drop_table("marketplace_connections")
    op.drop_column("client_conversations", "provider_id")
