"""Core API and isolation tests."""

from app.services.sanitize import sanitize_text
from app.services.embeddings import embed_text, cosine_similarity
from app.services.auto_resolver import reset_password, get_order_status
from app.services.classifier import classify_ticket, analyze_sentiment
from app.services.pipeline import process_new_ticket
from app.models import Ticket, TicketChannel
from sqlmodel import Session


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_and_login(client):
    r = client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": "Demo Co",
            "tenant_slug": "demo",
            "email": "owner@demo.example",
            "full_name": "Owner",
            "password": "password123",
        },
    )
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@demo.example", "password": "password123", "tenant_slug": "demo"},
    )
    assert login.status_code == 200


def test_sanitize_strips_script():
    dirty = '<script>alert(1)</script>Hello <b>world</b>'
    clean = sanitize_text(dirty)
    assert "<script>" not in clean
    assert "Hello" in clean


def test_embeddings_similarity():
    a = embed_text("reset my password please")
    b = embed_text("I need a password reset link")
    c = embed_text("where is my pizza delivery")
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_auto_resolve_tools():
    assert reset_password("cust_1")["ok"] is True
    assert get_order_status("ORD-12345")["ok"] is True


def test_create_ticket_and_pipeline(client, tenant_admin, engine):
    # Override session for pipeline uses get_session_context — patch via creating ticket through API
    # and processing with same engine by monkeypatching
    from app import db as dbmod

    dbmod.engine = engine

    r = client.post(
        "/api/v1/tickets",
        headers=tenant_admin["headers"],
        json={
            "customer_email": "cust@example.com",
            "subject": "I forgot my password",
            "body": "Please reset my password urgently",
            "customer_id": "cust_99",
        },
    )
    assert r.status_code == 200
    ticket_id = r.json()["id"]

    result = process_new_ticket(__import__("uuid").UUID(ticket_id))
    assert "classify" in result
    assert "sentiment" in result

    detail = client.get(f"/api/v1/tickets/{ticket_id}", headers=tenant_admin["headers"])
    assert detail.status_code == 200
    body = detail.json()
    assert body["category"] is not None
    assert body["suggested_reply"] or body["auto_resolved"] is not None


def test_tenant_isolation(client, tenant_admin, other_tenant, engine):
    from app import db as dbmod

    dbmod.engine = engine

    created = client.post(
        "/api/v1/tickets",
        headers=tenant_admin["headers"],
        json={
            "customer_email": "a@acme.example",
            "subject": "Secret ticket",
            "body": "Tenant A only",
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]

    leak = client.get(f"/api/v1/tickets/{ticket_id}", headers=other_tenant["headers"])
    assert leak.status_code == 404

    listed = client.get("/api/v1/tickets", headers=other_tenant["headers"])
    assert listed.status_code == 200
    assert all(t["id"] != ticket_id for t in listed.json())


def test_widget_query(client, tenant_admin, session):
    tenant = tenant_admin["tenant"]
    r = client.post(
        "/api/v1/widget/query",
        headers={"X-Tenant-Key": tenant.api_key},
        json={"question": "How do I reset my password?"},
    )
    assert r.status_code == 200
    assert "answered" in r.json()


def test_public_ticket(client, tenant_admin):
    r = client.post(
        "/api/v1/public/tickets",
        headers={"X-Tenant-Key": tenant_admin["tenant"].api_key},
        json={
            "customer_email": "public@example.com",
            "subject": "Order status",
            "body": "Where is order ORD-999888?",
            "channel": "api",
        },
    )
    assert r.status_code == 200
