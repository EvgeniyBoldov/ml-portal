from sqlalchemy.orm import declarative_base
from pydantic import BaseModel as PydanticBaseModel

Base = declarative_base()

class BaseModel(PydanticBaseModel):
    """Base Pydantic model for all schemas."""
    pass