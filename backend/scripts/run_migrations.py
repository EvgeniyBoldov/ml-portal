# backend/scripts/run_migrations.py
"""Programmatic Alembic upgrade to head.
Use: python scripts/run_migrations.py
Requires: ALEMBIC_CONFIG (optional) or uses app/migrations as script_location.
"""
import os, sys
from alembic import command
from alembic.config import Config

here = os.path.dirname(os.path.abspath(__file__))
# We expect migrations under app/migrations
cfg = Config()
cfg.set_main_option("script_location", "app/migrations")
# DB URL read by env.py via app.core.config.settings, so no need to set here.
command.upgrade(cfg, "head")
print("Migrations applied: head")
