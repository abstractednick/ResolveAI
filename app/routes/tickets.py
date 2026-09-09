"""Ticket CRUD, replies, AI assist actions."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth import AgentUser, CurrentUser
from app.db import get_session
from app.models import Ticket, TicketEvent, TicketMessage, TicketStatus, utcnow
from app.schemas import TicketCreate, TicketOut, TicketReply, TicketUpdate
from app.services.audit import log_audit, log_ticket_event
from app.services.reply_assistant import generate_agent_draft
from app.services.sanitize import sanitize_email, sanitize_text
from app.services.summarizer import summarize_thread
from app.services.translator import translate_outgoing
from app.workers.tasks import enqueue_ticket_processing

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _to_out(ticket: Ticket) -> TicketOut:
    return TicketOut.model_validate(ticket)


@router.post("", response_model=TicketOut)
def create_ticket(
    payload: TicketCreate,
    user: AgentUser,
    session: Session = Depends(get_session),
):
    try:
        email = sanitize_email(str(payload.customer_email))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ticket = Ticket(
        tenant_id=user.tenant_id,
        customer_email=email,
        customer_id=payload.customer_id,
        subject=sanitize_text(payload.subject, max_length=500),
        body=sanitize_text(payload.body),
        channel=payload.channel,
        priority=payload.priority or ticket_priority_default(),
        meta=payload.meta,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    session.add(
        TicketMessage(
            tenant_id=user.tenant_id,
            ticket_id=ticket.id,
            author_type="customer",
            body=ticket.body,
            language="en",
        )
    )
    session.commit()

    log_ticket_event(
        session,
        tenant_id=user.tenant_id,
        ticket_id=ticket.id,
        action="created",
        actor_type="agent",
        actor_id=str(user.id),
        details={"channel": ticket.channel.value},
    )
    enqueue_ticket_processing(ticket.id)
    session.refresh(ticket)
    return _to_out(ticket)


def ticket_priority_default():
    from app.models import TicketPriority

    return TicketPriority.medium


@router.get("", response_model=list[TicketOut])
def list_tickets(
    user: CurrentUser,
    session: Session = Depends(get_session),
    status_filter: Optional[TicketStatus] = Query(None, alias="status"),
    priority: Optional[str] = None,
    team: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    query = select(Ticket).where(
        Ticket.tenant_id == user.tenant_id,
        Ticket.merged_into_id.is_(None),  # type: ignore
    )
    if status_filter:
        query = query.where(Ticket.status == status_filter)
    if priority:
        query = query.where(Ticket.priority == priority)
    if team:
        query = query.where(Ticket.assigned_team == team)
    if q:
        like = f"%{q}%"
        query = query.where((Ticket.subject.ilike(like)) | (Ticket.body.ilike(like)) | (Ticket.customer_email.ilike(like)))  # type: ignore
    query = query.order_by(Ticket.created_at.desc()).limit(limit)  # type: ignore
    tickets = session.exec(query).all()
    return [_to_out(t) for t in tickets]


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: UUID, user: CurrentUser, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _to_out(ticket)


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: UUID,
    payload: TicketUpdate,
    user: AgentUser,
    session: Session = Depends(get_session),
):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(ticket, k, v)
    if payload.status == TicketStatus.resolved and not ticket.resolved_at:
        ticket.resolved_at = utcnow()
    ticket.updated_at = utcnow()
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    log_ticket_event(
        session,
        tenant_id=user.tenant_id,
        ticket_id=ticket.id,
        action="updated",
        actor_type="agent",
        actor_id=str(user.id),
        details=data,
    )
    return _to_out(ticket)


@router.post("/{ticket_id}/reply", response_model=TicketOut)
def reply_to_ticket(
    ticket_id: UUID,
    payload: TicketReply,
    user: AgentUser,
    session: Session = Depends(get_session),
):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Ticket not found")

    body = sanitize_text(payload.body)
    outbound = body
    original = None
    if payload.send_translation and ticket.language and ticket.language != "en":
        outbound = translate_outgoing(body, ticket.language)
        original = body

    msg = TicketMessage(
        tenant_id=user.tenant_id,
        ticket_id=ticket.id,
        author_type="agent",
        author_id=user.id,
        body=outbound,
        body_original=original,
        language=ticket.language,
        is_internal=payload.is_internal,
    )
    session.add(msg)
    if not payload.is_internal:
        if not ticket.first_response_sent:
            ticket.first_response_sent = True
            ticket.first_responded_at = utcnow()
        ticket.status = TicketStatus.pending
    ticket.updated_at = utcnow()
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    log_ticket_event(
        session,
        tenant_id=user.tenant_id,
        ticket_id=ticket.id,
        action="agent_replied",
        actor_type="agent",
        actor_id=str(user.id),
        details={"internal": payload.is_internal},
    )
    return _to_out(ticket)


@router.post("/{ticket_id}/draft")
def draft_reply(ticket_id: UUID, user: AgentUser, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return generate_agent_draft(ticket_id, session=session)


@router.post("/{ticket_id}/summarize")
def summarize(ticket_id: UUID, user: AgentUser, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return summarize_thread(ticket_id, session=session)


@router.get("/{ticket_id}/events")
def ticket_events(ticket_id: UUID, user: CurrentUser, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    events = session.exec(
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket_id, TicketEvent.tenant_id == user.tenant_id)
        .order_by(TicketEvent.created_at.desc())  # type: ignore
    ).all()
    return [
        {
            "id": str(e.id),
            "action": e.action,
            "actor_type": e.actor_type,
            "actor_id": e.actor_id,
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.get("/{ticket_id}/messages")
def ticket_messages(ticket_id: UUID, user: CurrentUser, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    messages = session.exec(
        select(TicketMessage)
        .where(TicketMessage.ticket_id == ticket_id, TicketMessage.tenant_id == user.tenant_id)
        .order_by(TicketMessage.created_at)  # type: ignore
    ).all()
    return [
        {
            "id": str(m.id),
            "author_type": m.author_type,
            "body": m.body,
            "body_original": m.body_original,
            "language": m.language,
            "is_internal": m.is_internal,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]
