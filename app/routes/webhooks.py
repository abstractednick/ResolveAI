"""Inbound webhooks: email + helpdesk connectors."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.middleware.rate_limit import rate_limit_dependency
from app.models import Tenant, Ticket, TicketChannel, TicketMessage, TicketPriority
from app.schemas import EmailInboundPayload, HelpdeskWebhookPayload, TicketOut
from app.services.sanitize import sanitize_email, sanitize_text
from app.workers.tasks import enqueue_ticket_processing

router = APIRouter(prefix="/webhooks", tags=["webhooks"], dependencies=[Depends(rate_limit_dependency)])


def _tenant_from_key(session: Session, api_key: str | None) -> Tenant:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-Key")
    tenant = session.exec(select(Tenant).where(Tenant.api_key == api_key)).first()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=401, detail="Invalid tenant key")
    return tenant


@router.post("/email/inbound", response_model=TicketOut)
def inbound_email(
    payload: EmailInboundPayload,
    session: Session = Depends(get_session),
    x_tenant_key: str | None = Header(default=None, alias="X-Tenant-Key"),
):
    tenant = _tenant_from_key(session, x_tenant_key)
    raw_from = payload.From or payload.from_email or ""
    # Postmark style: "Name <email@x.com>"
    if "<" in raw_from and ">" in raw_from:
        email = raw_from.split("<")[1].split(">")[0]
    else:
        email = raw_from
    try:
        email = sanitize_email(email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    subject = sanitize_text(payload.Subject or payload.subject or "(no subject)", max_length=500)
    body = sanitize_text(payload.TextBody or payload.text or payload.HtmlBody or payload.html or "")
    ticket = Ticket(
        tenant_id=tenant.id,
        customer_email=email,
        subject=subject,
        body=body or "(empty)",
        channel=TicketChannel.email,
        external_id=payload.MessageID,
        meta={"source": "email_inbound"},
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    session.add(
        TicketMessage(
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            author_type="customer",
            body=ticket.body,
        )
    )
    session.commit()
    enqueue_ticket_processing(ticket.id)
    session.refresh(ticket)
    return TicketOut.model_validate(ticket)


@router.post("/zendesk", response_model=TicketOut)
@router.post("/freshdesk", response_model=TicketOut)
@router.post("/intercom", response_model=TicketOut)
def helpdesk_webhook(
    payload: HelpdeskWebhookPayload,
    session: Session = Depends(get_session),
    x_tenant_key: str | None = Header(default=None, alias="X-Tenant-Key"),
    x_channel: str | None = Header(default="zendesk", alias="X-Helpdesk-Channel"),
):
    tenant = _tenant_from_key(session, x_tenant_key)
    channel_map = {
        "zendesk": TicketChannel.zendesk,
        "freshdesk": TicketChannel.freshdesk,
        "intercom": TicketChannel.intercom,
    }
    channel = channel_map.get((x_channel or "zendesk").lower(), TicketChannel.zendesk)

    existing = session.exec(
        select(Ticket).where(
            Ticket.tenant_id == tenant.id,
            Ticket.external_id == payload.external_id,
        )
    ).first()
    if existing:
        return TicketOut.model_validate(existing)

    priority = TicketPriority.medium
    if payload.priority:
        try:
            priority = TicketPriority(payload.priority.lower())
        except ValueError:
            priority = TicketPriority.medium

    ticket = Ticket(
        tenant_id=tenant.id,
        customer_email=sanitize_email(str(payload.customer_email)),
        subject=sanitize_text(payload.subject, max_length=500),
        body=sanitize_text(payload.body) or "(empty)",
        channel=channel,
        priority=priority,
        external_id=payload.external_id,
        meta={"tags": payload.tags, "raw": payload.raw},
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    session.add(
        TicketMessage(
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            author_type="customer",
            body=ticket.body,
        )
    )
    session.commit()
    enqueue_ticket_processing(ticket.id)
    session.refresh(ticket)
    return TicketOut.model_validate(ticket)
