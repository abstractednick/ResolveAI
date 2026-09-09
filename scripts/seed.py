#!/usr/bin/env python3
"""Seed a demo tenant with sample KB + tickets for local demo."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select

from app.auth import hash_password
from app.db import engine, init_db
from app.models import KBArticle, RoutingRule, SLAPolicy, Team, Tenant, User, UserRole
from app.services.similarity import embed_kb_article


def main() -> None:
    init_db()
    with Session(engine) as session:
        existing = session.exec(select(Tenant).where(Tenant.slug == "demo")).first()
        if existing:
            print(f"Demo tenant already exists. API key: {existing.api_key}")
            return

        tenant = Tenant(name="Demo Corp", slug="demo")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

        admin = User(
            tenant_id=tenant.id,
            email="admin@demo.resolveai",
            full_name="Demo Admin",
            hashed_password=hash_password("demo12345"),
            role=UserRole.admin,
            team="admin",
        )
        agent = User(
            tenant_id=tenant.id,
            email="agent@demo.resolveai",
            full_name="Demo Agent",
            hashed_password=hash_password("demo12345"),
            role=UserRole.agent,
            team="support",
        )
        session.add(admin)
        session.add(agent)
        session.add(SLAPolicy(tenant_id=tenant.id, name="Default SLA", is_default=True))
        session.add(Team(tenant_id=tenant.id, name="Support", slug="support", categories=["general", "account_access"]))
        session.add(Team(tenant_id=tenant.id, name="Billing", slug="billing", categories=["billing", "subscription"]))
        session.add(
            RoutingRule(
                tenant_id=tenant.id,
                name="Billing keywords",
                keywords=["invoice", "refund", "charge"],
                categories=["billing"],
                assign_team="billing",
            )
        )
        kb = KBArticle(
            tenant_id=tenant.id,
            title="How to reset your password",
            content=(
                "1. Go to the login page and click Forgot Password.\n"
                "2. Enter your email address.\n"
                "3. Check your inbox for a reset link (valid 60 minutes).\n"
                "4. Choose a new password with at least 8 characters."
            ),
            category="account_access",
            tags=["password", "login"],
            status="published",
        )
        session.add(kb)
        session.commit()
        session.refresh(kb)
        embed_kb_article(kb.id, session=session)

        print("Seeded demo tenant")
        print(f"  slug:     demo")
        print(f"  admin:    admin@demo.resolveai / demo12345")
        print(f"  agent:    agent@demo.resolveai / demo12345")
        print(f"  api_key:  {tenant.api_key}")


if __name__ == "__main__":
    main()
