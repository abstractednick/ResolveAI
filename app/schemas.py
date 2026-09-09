"""Shared schemas for API request/response bodies."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import TicketChannel, TicketPriority, TicketStatus, UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    tenant_id: UUID
    user_id: UUID
    email: str


class RegisterRequest(BaseModel):
    tenant_name: str
    tenant_slug: str
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str
    tenant_slug: str


class TicketCreate(BaseModel):
    customer_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=50000)
    channel: TicketChannel = TicketChannel.api
    customer_id: Optional[str] = None
    priority: Optional[TicketPriority] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class TicketUpdate(BaseModel):
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    assigned_team: Optional[str] = None
    assigned_agent_id: Optional[UUID] = None
    category: Optional[str] = None


class TicketReply(BaseModel):
    body: str = Field(min_length=1, max_length=50000)
    is_internal: bool = False
    send_translation: bool = True


class TicketOut(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_email: str
    subject: str
    body: str
    body_original: Optional[str]
    language: str
    channel: TicketChannel
    status: TicketStatus
    priority: TicketPriority
    category: Optional[str]
    assigned_team: Optional[str]
    assigned_agent_id: Optional[UUID]
    sentiment: str
    sentiment_score: float
    breach_risk_score: float
    predicted_csat: Optional[float]
    summary: Optional[str]
    suggested_reply: Optional[str]
    first_response_sent: bool
    auto_resolved: bool
    created_at: datetime
    updated_at: datetime
    first_responded_at: Optional[datetime]
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


class KBArticleCreate(BaseModel):
    title: str
    content: str
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    status: str = "published"


class KBArticleOut(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    content: str
    category: Optional[str]
    tags: list[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SLAPolicyCreate(BaseModel):
    name: str
    response_targets: dict[str, int]
    resolution_targets: dict[str, int]
    is_default: bool = True


class TeamCreate(BaseModel):
    name: str
    slug: str
    categories: list[str] = Field(default_factory=list)


class RoutingRuleCreate(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    assign_team: str
    assign_agent_email: Optional[str] = None
    priority_override: Optional[str] = None


class WidgetQuery(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    customer_email: Optional[str] = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    create_ticket_if_unresolved: bool = False


class WidgetAnswer(BaseModel):
    answered: bool
    answer: Optional[str] = None
    kb_article_id: Optional[UUID] = None
    similar_ticket_ids: list[UUID] = Field(default_factory=list)
    ticket_id: Optional[UUID] = None
    confidence: float = 0.0


class EmailInboundPayload(BaseModel):
    From: Optional[str] = None
    from_email: Optional[str] = None
    Subject: Optional[str] = None
    subject: Optional[str] = None
    TextBody: Optional[str] = None
    HtmlBody: Optional[str] = None
    text: Optional[str] = None
    html: Optional[str] = None
    MessageID: Optional[str] = None


class HelpdeskWebhookPayload(BaseModel):
    external_id: str
    customer_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    subject: str
    body: str
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str
