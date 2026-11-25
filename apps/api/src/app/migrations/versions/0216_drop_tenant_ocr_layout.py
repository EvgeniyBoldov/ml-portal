"""Drop dead OCR plan remnants: tenant flags and OCR model rows.

Revision ID: 0216
Revises: 0215
"""
import sqlalchemy as sa
from alembic import op


revision = "0216"
down_revision = "0215"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Docling is now the single document parsing path; the legacy OCR plan is retired.
    # PG stores enum labels in uppercase and cannot drop a value, so the enum type is kept.
    op.execute("DELETE FROM models WHERE type = 'OCR'")
    op.drop_column("tenants", "ocr")
    op.drop_column("tenants", "layout")


def downgrade() -> None:
    op.add_column("tenants", sa.Column("ocr", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("tenants", sa.Column("layout", sa.Boolean(), nullable=False, server_default="false"))
