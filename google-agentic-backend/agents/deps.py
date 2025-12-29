from pydantic import BaseModel
from typing import Any
from sqlalchemy.orm import Session

class AgentDeps(BaseModel):
    user_email: str
    db_session: Any
    conversation_id: str
    google_credentials: Any
    qdrant_service: Any
    
    class Config:
        arbitrary_types_allowed = True