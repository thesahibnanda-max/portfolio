from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from main.package.ai.common import ContextType
from main.package.ai.orchestrator import QueryScope
from main.package.repository import ChatOrigin, MessageRole
from main.package.service.data import ProfessionalDetails
from main.package.static.dto import Favorites, Interests, Lifestyle, PersonalityTraits, Profile, SpokenLanguage


class _RequestModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class _ResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)


class CreateChatRequest(_RequestModel):
    title: str | None = None
    origin: Literal["chat", "cli"] | None = None


class RenameChatRequest(_RequestModel):
    title: str


class SendMessageRequest(_RequestModel):
    message: str


class ContactRequest(_RequestModel):
    email: str
    subject: str
    message: str


class ApiResponse[T](_ResponseModel):
    status: int
    timestamp: datetime
    data: T


class ErrorDetail(_ResponseModel):
    field: str
    message: str


class ErrorResponse(_ResponseModel):
    status: int
    timestamp: datetime
    error: str
    message: str
    details: tuple[ErrorDetail, ...] = ()


class HealthResponse(_ResponseModel):
    status: str


class SessionResponse(_ResponseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime


class ChatSummaryResponse(_ResponseModel):
    chat_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    origin: ChatOrigin


class MessageResponse(_ResponseModel):
    message_id: int
    role: MessageRole
    content: str
    created_at: datetime


class ChatResponse(ChatSummaryResponse):
    messages: tuple[MessageResponse, ...]


class ChatListResponse(_ResponseModel):
    chats: tuple[ChatSummaryResponse, ...]


class ChatReplyResponse(_ResponseModel):
    chat: ChatResponse
    answer: str
    scope: QueryScope
    required_contexts: tuple[ContextType, ...]


class ContactResponse(_ResponseModel):
    status: str
    reply_to: str
    sent_at: datetime


class StreamTokenResponse(_ResponseModel):
    text: str


class StreamStepResponse(_ResponseModel):
    label: str


class AccountsResponse[T](_ResponseModel):
    accounts: tuple[T, ...]


class ProfileResponse(Profile):
    profile_image_url: str


class PublicPersonalProfile(_ResponseModel):
    personality: PersonalityTraits
    interests: Interests
    favorites: Favorites
    lifestyle: Lifestyle
    languages: tuple[SpokenLanguage, ...]


class PersonalityResponse(_ResponseModel):
    personal_profile: PublicPersonalProfile


class ProfessionalResponse(ProfessionalDetails):
    resume_link: str
