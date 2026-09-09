"""Public ticket creation for widget/API key clients."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.middleware.rate_limit import rate_limit_dependency
from app.models import Tenant, Ticket, TicketChannel, TicketMessage, TicketPriority
from app.schemas import TicketCreate, TicketOut
from app.services.sanitize import sanitize_email, sanitize_text
from app.workers.tasks import enqueue_ticket_processing

router = APIRouter(prefix="/public", tags=["public"], dependencies=[Depends(rate_limit_dependency)])


@router.post("/tickets", response_model=TicketOut)
def public_create_ticket(
    payload: TicketCreate,
    session: Session = Depends(get_session),
    x_tenant_key: str | None = Header(default=None, alias="X-Tenant-Key"),
):
    if not x_tenant_key:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-Key")
    tenant = session.exec(select(Tenant).where(Tenant.api_key == x_tenant_key)).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid tenant key")

    ticket = Ticket(
        tenant_id=tenant.id,
        customer_email=sanitize_email(str(payload.customer_email)),
        customer_id=payload.customer_id,
        subject=sanitize_text(payload.subject, max_length=500),
        body=sanitize_text(payload.body),
        channel=payload.channel or TicketChannel.api,
        priority=payload.priority or TicketPriority.medium,
        meta=payload.meta,
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
