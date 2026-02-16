"""
Add instance_type (local/remote) and slug to tool_instances.
Flatten RBAC: remove rbac_policies container, keep rbac_rules with direct owner binding.

Revision ID: 0042_instance_type_rbac
Revises: 0041_agent_permissions_system
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0042_instance_type_rbac'
down_revision = '0041_agent_permissions_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Kept for backward compatibility with databases already stamped at this revision.
    # Real schema changes were moved to the main linear migration chain.
    pass


def downgrade() -> None:
    pass
