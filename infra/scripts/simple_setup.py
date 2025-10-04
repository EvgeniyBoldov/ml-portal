#!/usr/bin/env python3
"""
Simple setup script for development without migrations.
"""
import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add app to path
sys.path.insert(0, '/app')

try:
    from app.core.db import engine
    from app.models.base import Base
    
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully!")
    
except Exception as e:
    logger.error(f"Database setup failed: {e}")
    sys.exit(1)
