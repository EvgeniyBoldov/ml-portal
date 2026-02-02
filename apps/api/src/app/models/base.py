"""
Base SQLAlchemy model
"""
from sqlalchemy.orm import registry

# Use registry instead of declarative_base for better control
mapper_registry = registry()
Base = mapper_registry.generate_base()

