"""Portfolio source revisions, evidence chunks and a vector-deletion outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0002_portfolio"
down_revision = "0001_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portfolio_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error", sa.String(200), nullable=True),
        sa.Column("indexed_model", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "filename", name="uq_portfolio_user_source"),
    )
    op.create_index("ix_portfolio_documents_user_id", "portfolio_documents", ["user_id"])
    op.create_index("ix_portfolio_documents_status", "portfolio_documents", ["status"])
    op.create_table(
        "evidence_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("portfolio_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
    )
    op.create_index("ix_evidence_chunks_user_id", "evidence_chunks", ["user_id"])
    op.create_index("ix_evidence_chunks_document_id", "evidence_chunks", ["document_id"])
    op.create_table(
        "vector_cleanup",
        sa.Column("document_id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vector_cleanup_user_id", "vector_cleanup", ["user_id"])


def downgrade():
    op.drop_table("vector_cleanup")
    op.drop_table("evidence_chunks")
    op.drop_table("portfolio_documents")
