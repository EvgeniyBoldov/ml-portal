"""Seed default tenant and admin user

Revision ID: 0002
Revises: 7ac97d34b0aa
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone


revision = "0002"
down_revision = "7ac97d34b0aa"
branch_labels = None
depends_on = None


# Default IDs
DEFAULT_TENANT_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a01")
DEFAULT_ADMIN_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
DEFAULT_ADMIN_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$EvghGOjfmI+H4NSs1czzGg$DVGHRkMwIzQWPxXfyybS+T7WmfIbo6G2UUQlscZVeTM"  # admin123


def upgrade() -> None:
    """Create default tenant and admin user"""
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    
    # 1. Create default tenant
    conn.execute(
        sa.text("""
            INSERT INTO tenants (id, name, ocr, layout, is_active, created_at, updated_at)
            VALUES (:id, :name, :ocr, :layout, :is_active, :created_at, :updated_at)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": DEFAULT_TENANT_ID,
            "name": "Default",
            "ocr": False,
            "layout": False,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    print("  ✅ Created default tenant")
    
    # 2. Create admin user
    conn.execute(
        sa.text("""
            INSERT INTO users (id, login, password_hash, email, role, is_active, created_at, updated_at)
            VALUES (:id, :login, :password_hash, :email, :role, :is_active, :created_at, :updated_at)
            ON CONFLICT (login) DO UPDATE SET
                email = EXCLUDED.email,
                role = EXCLUDED.role,
                is_active = EXCLUDED.is_active,
                updated_at = EXCLUDED.updated_at
        """),
        {
            "id": DEFAULT_ADMIN_ID,
            "login": "admin",
            "password_hash": DEFAULT_ADMIN_PASSWORD_HASH,
            "email": "admin@test.com",
            "role": "admin",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    print("  ✅ Created admin user (admin/admin123)")
    
    # 3. Link admin to default tenant
    conn.execute(
        sa.text("""
            INSERT INTO user_tenants (id, user_id, tenant_id, is_default)
            VALUES (:id, :user_id, :tenant_id, :is_default)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": uuid.uuid4(),
            "user_id": DEFAULT_ADMIN_ID,
            "tenant_id": DEFAULT_TENANT_ID,
            "is_default": True,
        }
    )
    print("  ✅ Linked admin to default tenant")


def downgrade() -> None:
    """Remove default tenant and admin"""
    conn = op.get_bind()
    
    # Remove user_tenants link
    conn.execute(
        sa.text("DELETE FROM user_tenants WHERE user_id = :user_id"),
        {"user_id": DEFAULT_ADMIN_ID}
    )
    
    # Remove admin user
    conn.execute(
        sa.text("DELETE FROM users WHERE id = :id"),
        {"id": DEFAULT_ADMIN_ID}
    )
    
    # Remove default tenant (if no other users)
    conn.execute(
        sa.text("DELETE FROM tenants WHERE id = :id AND NOT EXISTS (SELECT 1 FROM user_tenants WHERE tenant_id = :id)"),
        {"id": DEFAULT_TENANT_ID}
    )
