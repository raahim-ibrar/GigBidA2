"""Encrypted per-account Upwork OAuth credentials and verified tool discovery."""

import sqlalchemy as sa
from alembic import op

revision = "0011_upwork_oauth"
down_revision = "0010_search_execution"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "oauth_credentials",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(30), primary_key=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("generation", sa.String(36), nullable=False),
        sa.Column("connected", sa.Boolean(), nullable=False),
        sa.Column("schema_snapshot", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("oauth_credentials")
