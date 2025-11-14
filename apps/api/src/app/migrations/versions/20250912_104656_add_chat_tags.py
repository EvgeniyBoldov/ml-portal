"""add chat tags column

Revision ID: 20250912_104656_add_chat_tags
Revises: 20250910_175628_initial
Create Date: 2025-09-12 10:46:56
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250912_104656_add_chat_tags'
down_revision = '20250910_175628_initial'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('chats', sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=False, server_default='{}'))
    op.alter_column('chats', 'tags', server_default=None)

def downgrade() -> None:
    op.drop_column('chats', 'tags')
