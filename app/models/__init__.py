"""SQLModel domain models — multi-tenant from day one."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    admin = "admin"
    agent = "agent"
    viewer = "viewer"
    customer = "customer"


class TicketStatus(str, Enum):
    open = "open"
    pending = "pending"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"
    merged = "merged"


class TicketPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class TicketChannel(str, Enum):
    api = "api"
    email = "email"
    widget = "widget"
    zendesk = "zendesk"
    freshdesk = "freshdesk"
    intercom = "intercom"


class SentimentTone(str, Enum):
    neutral = "neutral"
    frustrated = "frustrated"
    angry = "angry"


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    api_key: str = Field(default_factory=lambda: uuid4().hex, index=True)
    settings_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    email: str = Field(index=True)
    full_name: str
    hashed_password: str
    role: UserRole = Field(default=UserRole.agent)
    team: Optional[str] = Field(default=None, index=True)
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class SLAPolicy(SQLModel, table=True):
    __tablename__ = "sla_policies"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    name: str
    # minutes by priority
    response_targets: dict[str, int] = Field(
        default_factory=lambda: {"low": 480, "medium": 240, "high": 60, "urgent": 15},
        sa_column=Column(JSON),
    )
    resolution_targets: dict[str, int] = Field(
        default_factory=lambda: {"low": 2880, "medium": 1440, "high": 480, "urgent": 120},
        sa_column=Column(JSON),
    )
    is_default: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class Team(SQLModel, table=True):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_team_tenant_slug"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    name: str
    slug: str
    categories: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class RoutingRule(SQLModel, table=True):
    __tablename__ = "routing_rules"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    name: str
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    categories: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    assign_team: str
    assign_agent_email: Optional[str] = None
    priority_override: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    customer_email: str = Field(index=True)
    customer_id: Optional[str] = None
    subject: str
    body: str = Field(sa_column=Column(Text))
    body_original: Optional[str] = Field(default=None, sa_column=Column(Text))
    language: str = "en"
    channel: TicketChannel = TicketChannel.api
    status: TicketStatus = TicketStatus.open
    priority: TicketPriority = TicketPriority.medium
    category: Optional[str] = Field(default=None, index=True)
    assigned_team: Optional[str] = Field(default=None, index=True)
    assigned_agent_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    external_id: Optional[str] = Field(default=None, index=True)
    sentiment: SentimentTone = SentimentTone.neutral
    sentiment_score: float = 0.0
    breach_risk_score: float = 0.0
    predicted_csat: Optional[float] = None
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    suggested_reply: Optional[str] = Field(default=None, sa_column=Column(Text))
    first_response_sent: bool = False
    auto_resolved: bool = False
    merged_into_id: Optional[UUID] = Field(default=None, foreign_key="tickets.id")
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(JSON))
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
    first_responded_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class TicketMessage(SQLModel, table=True):
    __tablename__ = "ticket_messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    ticket_id: UUID = Field(foreign_key="tickets.id", index=True)
    author_type: str  # customer | agent | ai | system
    author_id: Optional[UUID] = None
    body: str = Field(sa_column=Column(Text))
    body_original: Optional[str] = Field(default=None, sa_column=Column(Text))
    language: str = "en"
    is_internal: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class TicketEvent(SQLModel, table=True):
    __tablename__ = "ticket_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    ticket_id: UUID = Field(foreign_key="tickets.id", index=True)
    actor_type: str  # system | ai | agent | admin
    actor_id: Optional[str] = None
    action: str
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class KBArticle(SQLModel, table=True):
    __tablename__ = "kb_articles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    title: str
    content: str = Field(sa_column=Column(Text))
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "published"  # draft | pending_review | published
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(JSON))
    source_ticket_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    ticket_id: Optional[UUID] = Field(default=None, foreign_key="tickets.id")
    alert_type: str
    message: str
    severity: str = "info"
    acknowledged: bool = False
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenants.id", index=True)
    actor_id: Optional[UUID] = None
    actor_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    ip_address: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
