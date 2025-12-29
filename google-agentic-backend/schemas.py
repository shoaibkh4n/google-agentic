from pydantic import BaseModel, SecretStr, EmailStr, UUID4, HttpUrl, Field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import uuid
import enum
from uuid import UUID


class Database(BaseModel):
    postgres_connection_string: SecretStr

class SwaggerDocs(BaseModel):
    username: str
    password: SecretStr

class AppConfig(BaseModel):
    allowed_origins: List[str]

class LogfireToken(BaseModel):
    token: SecretStr
    url: str

class SMTPCreds(BaseModel):
    smtp_server:str
    email:str
    password:SecretStr

class GoogleOAuth(BaseModel):
    client_id: str
    client_secret: SecretStr

class AgentCreds(BaseModel):
    llm_api_key: SecretStr
    openai_api_key: SecretStr

class QdrantCreds(BaseModel):
    url: str
    api_key: SecretStr

class Settings(BaseModel):
    database: Database
    swagger_docs: SwaggerDocs
    logfire:LogfireToken
    app_config: AppConfig
    agent_creds:AgentCreds
    google_oauth:GoogleOAuth
    smtp_creds:SMTPCreds
    qdrant_creds:QdrantCreds
    frontend_url: str

    def get_environment_variables(self) -> Dict[str, str]:
        env_vars = {
            "LOGFIRE_TOKEN": self.logfire.token.get_secret_value(),
        }
        return env_vars


class Role(str, enum.Enum):
    BOT = "bot"
    USER = "user"

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    conversation_id: Optional[UUID] = None


class Intent(BaseModel):
    services: List[str] = Field(default_factory=list)
    intent: str
    entities: Dict[str, Any] = Field(default_factory=dict)
    steps: List[str] = Field(default_factory=list)
    parallel_operations: List[List[str]] = Field(default_factory=list)
    sequential_operations: List[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    response: str
    actions_taken: List[str] = []
    intent: Optional[Intent] = None
    conversation_id: Optional[UUID] = None


class AuthStatusResponse(BaseModel):
    connected: bool
    services: Dict[str, bool]
    user_email: Optional[str] = None


class MessageContent(BaseModel):
    text: str
    metadata: Optional[Dict[str, Any]] = None


class MessageCreate(BaseModel):
    conversation_id: UUID
    content: Dict[str, Any]
    role: Role
    intent: Optional[Dict[str, Any]] = None


class ConversationCreate(BaseModel):
    name: str
    user_id: UUID


class ConversationResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    detail: str
    requires_auth: bool = False