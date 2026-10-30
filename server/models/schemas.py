from typing import Literal

from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    document: str
    page: int | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128)


class ChatResponse(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)
    sources: list[SourceReference] = Field(default_factory=list)
    conversation_id: str


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ConversationHistory(BaseModel):
    conversation_id: str
    messages: list[ConversationMessage]


class DocumentInfo(BaseModel):
    name: str
    source: str
    chunks: int
    categories: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
