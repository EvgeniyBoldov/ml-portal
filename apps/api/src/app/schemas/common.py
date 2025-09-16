from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime, date

class ErrorResponse(BaseModel):
    error: Dict[str, Any]
    request_id: Optional[str] = Field(None)
