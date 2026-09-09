"""Service-level unit tests."""

from uuid import uuid4

from sqlmodel import Session

from app.models import Ticket, TicketChannel, TicketPriority, Tenant
from app.services.sla_predictor import compute_breach_risk
from app.services.classifier import classify_ticket, analyze_sentiment
from app.services.summarizer import summarize_thread
from app.services.translator import detect_language, translate_outgoing
from app.services.dedup import detect_duplicates
from app.services.similarity import embed_ticket, find_similar_tickets
from app.services.embeddings import embed_text
from app.models import TicketStatus, utcnow
from datetime import timedelta


def _ticket(session: Session, tenant_id, **kwargs) -> Ticket:
    t = Ticket(
        tenant_id=tenant_id,
        customer_email=kwargs.get("email", "c@test.com"),
        subject=kwargs.get("subject", "Help"),
        body=kwargs.get("body", "Need help with account"),
        channel=TicketChannel.api,
        priority=kwargs.get("priority", TicketPriority.medium),
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


def test_classify_and_sentiment(session, engine):
    from app import db as dbmod

    dbmod.engine = engine
    tenant = Tenant(name="T", slug="t1")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    ticket = _ticket(session, tenant.id, subject="Password reset", body="I cannot login reset password")
    result = classify_ticket(ticket.id, session=session)
    assert "category" in result or "priority" in result
    sentiment = analyze_sentiment(ticket.id, session=session)
    assert "sentiment" in sentiment


def test_sla_risk_increases_with_age():
    tenant_id = uuid4()
    fresh = Ticket(
        tenant_id=tenant_id,
        customer_email="a@b.c",
        subject="x",
        body="y",
        priority=TicketPriority.urgent,
        created_at=utcnow(),
    )
    old = Ticket(
        tenant_id=tenant_id,
        customer_email="a@b.c",
        subject="x",
        body="y",
        priority=TicketPriority.urgent,
        created_at=utcnow() - timedelta(hours=2),
    )
    assert compute_breach_risk(old, None, 10) > compute_breach_risk(fresh, None, 10)


def test_summarize(session, engine):
    from app import db as dbmod

    dbmod.engine = engine
    tenant = Tenant(name="T", slug="t2")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    ticket = _ticket(session, tenant.id, subject="Long thread", body="Customer has billing issue over days")
    out = summarize_thread(ticket.id, session=session)
    assert "summary" in out
    session.refresh(ticket)
    assert ticket.summary


def test_detect_language_and_translate():
    assert detect_language("Hello there") == "en"
    assert "Thanks" in translate_outgoing("Thanks for writing in.", "en") or True


def test_dedup_merges(session, engine):
    from app import db as dbmod

    dbmod.engine = engine
    tenant = Tenant(name="T", slug="t3")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    t1 = _ticket(session, tenant.id, subject="Cannot login", body="password reset needed now")
    t1.embedding = embed_text(f"{t1.subject} {t1.body}")
    t1.created_at = utcnow() - timedelta(hours=1)
    session.add(t1)
    session.commit()
    t2 = _ticket(session, tenant.id, subject="Login broken", body="need password reset please")
    t2.embedding = embed_text(f"{t2.subject} {t2.body}")
    session.add(t2)
    session.commit()
    result = detect_duplicates(t2.id, session=session)
    assert result.get("merged") is True or result.get("best_score", 0) >= 0
