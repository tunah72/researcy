from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from researcy.citations.models import ResolvedCitation
from researcy.ingestion.models import DocumentScope

RunState = Literal['running', 'completed', 'refused', 'failed', 'interrupted']
MessageRole = Literal['user', 'assistant']


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


class MessageSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')

    client_message_id: UUID
    question: str = Field(min_length=1, max_length=2400)

    @field_validator('question')
    @classmethod
    def supported_question(cls, question: str) -> str:
        if not question.strip():
            raise ValueError('A question is required.')
        if '\x00' in question:
            raise ValueError('A valid question is required.')
        try:
            question.encode('utf-8')
        except UnicodeError as exc:
            raise ValueError('A valid question is required.') from exc
        return question


class MessageSummary(BaseModel):
    id: UUID
    role: MessageRole
    text: str
    state: RunState


class Conversation(BaseModel):
    id: UUID
    paper_id: UUID
    document_version: UUID
    created_at: datetime
    updated_at: datetime
    last_message: MessageSummary | None = None


class Message(BaseModel):
    id: UUID
    sequence: int
    role: MessageRole
    text: str
    state: RunState
    error_code: str | None
    request_id: UUID
    created_at: datetime
    updated_at: datetime
    citations: tuple[ResolvedCitation, ...] = ()


class ConversationResponse(BaseModel):
    conversation: Conversation
    request_id: UUID


class ConversationListResponse(BaseModel):
    conversations: list[Conversation]
    next_before: UUID | None
    request_id: UUID


class MessageListResponse(BaseModel):
    messages: list[Message]
    next_after: UUID | None
    request_id: UUID


@dataclass(frozen=True, slots=True)
class RunReservation:
    run_id: UUID
    scope: DocumentScope
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    question: str
    request_id: UUID
    lease_expires_at: datetime
    state: RunState
    is_replay: bool


@dataclass(frozen=True, slots=True)
class CompletedAnswer:
    run_id: UUID
    message: Message
    citations: tuple[ResolvedCitation, ...]


class MessageStreamReplayResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: UUID
    message_id: UUID
    state: RunState
    request_id: UUID
