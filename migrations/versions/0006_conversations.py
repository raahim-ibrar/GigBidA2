"""One durable run per client conversation and idempotent manual message intake."""

import sqlalchemy as sa
from alembic import op

revision = "0006_conversations"
down_revision = "0005_workspace"
branch_labels = None
depends_on = None


def owner():
    return sa.Column(
        "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


def upgrade():
    op.add_column(
        "agent_runs", sa.Column("kind", sa.String(20), nullable=False, server_default="bid")
    )
    op.create_table(
        "client_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        owner(),
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_client_conversations_user_id", "client_conversations", ["user_id"])
    op.create_table(
        "client_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        owner(),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("client_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "request_key", name="uq_client_message_request"),
    )
    op.create_index("ix_client_messages_user_id", "client_messages", ["user_id"])
    op.create_index("ix_client_messages_conversation_id", "client_messages", ["conversation_id"])


def downgrade():
    op.drop_table("client_messages")
    op.drop_table("client_conversations")
    op.drop_column("agent_runs", "kind")
