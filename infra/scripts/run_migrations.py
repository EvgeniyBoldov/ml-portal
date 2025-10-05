# backend/scripts/run_migrations.py
"""Programmatic Alembic upgrade to head.
Use: python scripts/run_migrations.py
Requires: ALEMBIC_CONFIG (optional) or uses app/migrations as script_location.
"""
import os, sys
from alembic import command
from alembic.config import Config

here = os.path.dirname(os.path.abspath(__file__))
# We expect migrations under apps/api/src/app/migrations
cfg = Config()
cfg.set_main_option("script_location", "../src/app/migrations")
cfg.set_main_option("sqlalchemy.url", "postgresql://ml_portal:ml_portal_password@postgres:5432/ml_portal")
# DB URL read by env.py via app.core.config.settings, so no need to set here.
try:
    command.upgrade(cfg, "head")
    print("Migrations applied: head")
except Exception as e:
    print(f"Migration failed: {e}")
    # Try to create tables without migrations for dev
    from app.core.db import engine
    from app.models import Base
    Base.metadata.create_all(bind=engine)
    print("Tables created directly")
