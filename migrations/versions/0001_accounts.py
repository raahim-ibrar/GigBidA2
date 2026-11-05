"""Accounts, revocable sessions, and user-owned freelancer settings."""

import sqlalchemy as sa
from alembic import op

revision = "0001_accounts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "user_sessions",
        sa.Column("token_digest", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_table(
        "freelancer_profiles",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("display_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("persona", sa.String(30), nullable=False, server_default="own"),
        sa.Column("hourly_floor", sa.Numeric(10, 2), nullable=False, server_default="15.00"),
        sa.Column("weekly_connects_budget", sa.Integer, nullable=False, server_default="100"),
        sa.Column("saved_searches", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("onboarding_complete", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_table("freelancer_profiles")
    op.drop_table("user_sessions")
    op.drop_table("users")
