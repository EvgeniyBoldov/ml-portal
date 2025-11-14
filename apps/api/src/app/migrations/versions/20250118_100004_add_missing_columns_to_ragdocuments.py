"""add missing columns to ragdocuments table

Revision ID: 20250118_100004
Revises: 20250118_100003
Create Date: 2025-01-18 10:00:04.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250118_100004'
down_revision = '20250118_100003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing columns to ragdocuments table
    op.add_column('ragdocuments', sa.Column('filename', sa.String(255), nullable=True))
    op.add_column('ragdocuments', sa.Column('title', sa.String(255), nullable=True))
    op.add_column('ragdocuments', sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('ragdocuments', sa.Column('content_type', sa.String(100), nullable=True))
    op.add_column('ragdocuments', sa.Column('size', sa.Integer(), nullable=True))
    op.add_column('ragdocuments', sa.Column('s3_key_raw', sa.String(500), nullable=True))
    op.add_column('ragdocuments', sa.Column('s3_key_processed', sa.String(500), nullable=True))
    op.add_column('ragdocuments', sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))
    op.add_column('ragdocuments', sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ragdocuments', sa.Column('error_message', sa.Text(), nullable=True))
    
    # Update existing records to have default values
    op.execute("UPDATE ragdocuments SET filename = name WHERE filename IS NULL")
    op.execute("UPDATE ragdocuments SET title = name WHERE title IS NULL")
    op.execute("UPDATE ragdocuments SET user_id = uploaded_by WHERE user_id IS NULL")
    op.execute("UPDATE ragdocuments SET content_type = source_mime WHERE content_type IS NULL")
    op.execute("UPDATE ragdocuments SET size = size_bytes WHERE size IS NULL")
    op.execute("UPDATE ragdocuments SET s3_key_raw = url_file WHERE s3_key_raw IS NULL")
    op.execute("UPDATE ragdocuments SET s3_key_processed = url_canonical_file WHERE s3_key_processed IS NULL")
    op.execute("UPDATE ragdocuments SET created_at = date_upload WHERE created_at IS NULL")
    op.execute("UPDATE ragdocuments SET error_message = error WHERE error_message IS NULL")
    
    # Make columns NOT NULL where appropriate
    op.alter_column('ragdocuments', 'filename', nullable=False)
    op.alter_column('ragdocuments', 'title', nullable=False)
    op.alter_column('ragdocuments', 'user_id', nullable=False)
    op.alter_column('ragdocuments', 'created_at', nullable=False)


def downgrade() -> None:
    # Drop columns
    op.drop_column('ragdocuments', 'error_message')
    op.drop_column('ragdocuments', 'processed_at')
    op.drop_column('ragdocuments', 'created_at')
    op.drop_column('ragdocuments', 's3_key_processed')
    op.drop_column('ragdocuments', 's3_key_raw')
    op.drop_column('ragdocuments', 'size')
    op.drop_column('ragdocuments', 'content_type')
    op.drop_column('ragdocuments', 'user_id')
    op.drop_column('ragdocuments', 'title')
    op.drop_column('ragdocuments', 'filename')
