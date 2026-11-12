"""Opt-in bounded scheduled analysis of newly imported simulator jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0010_search_execution"
down_revision = "0009_student_marketplace"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "search_schedules",
        sa.Column("auto_analyse", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("search_schedules", "auto_analyse")
