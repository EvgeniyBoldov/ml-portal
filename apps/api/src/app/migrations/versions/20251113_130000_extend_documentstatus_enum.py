"""extend documentstatus enum with missing values

Revision ID: 20251113_130000
Revises: 20250118_100006
Create Date: 2025-11-13 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251113_130000"
down_revision = "20250118_100006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure enum type exists (created earlier migrations). Add values idempotently.
    # Note: Postgres doesn't support IF NOT EXISTS before v13 for ADD VALUE, so use DO block.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                           WHERE t.typname = 'documentstatus' AND n.nspname = 'public') THEN
                CREATE TYPE documentstatus AS ENUM ('uploading', 'processing', 'processed', 'failed', 'archived');
            END IF;
        END$$;
        """
    )

    # Add missing values: uploaded, ready, queued (Postgres >= 12 supports IF NOT EXISTS)
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'uploaded'")
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'ready'")
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'queued'")

    # Intentionally skip setting default here to avoid "unsafe use of new value" in same transaction.


def downgrade() -> None:
    # Downgrade is a no-op for removing enum values (not supported safely)
    pass
