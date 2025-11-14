# app/migrations/versions/20250908_154500_add_tokens.py
"""Compatibility shim: previously existed in DB history.
This migration is intentionally a no-op to satisfy databases already stamped
with this revision id.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250908_154500_add_tokens"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # No operation on purpose
    pass

def downgrade():
    # No operation on purpose
    pass
