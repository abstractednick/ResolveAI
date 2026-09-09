"""Pytest fixtures — SQLite for isolated unit/integration tests."""

from __future__ import annotations

import os

# Force test settings before imports that read config
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-key-not-for-production"
os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "false"
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Tenant, User, UserRole, SLAPolicy
from app.auth import hash_password, create_access_token


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture()
def client(engine):
    def _get_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def tenant_admin(session):
    tenant = Tenant(name="Acme", slug="acme")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = User(
        tenant_id=tenant.id,
        email="admin@acme.test",
        full_name="Admin",
        hashed_password=hash_password("password123"),
        role=UserRole.admin,
    )
    session.add(user)
    session.add(SLAPolicy(tenant_id=tenant.id, name="Default", is_default=True))
    session.commit()
    session.refresh(user)
    token = create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role, email=user.email
    )
    return {"tenant": tenant, "user": user, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture()
def other_tenant(session):
    tenant = Tenant(name="Other", slug="other")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = User(
        tenant_id=tenant.id,
        email="admin@other.test",
        full_name="Other Admin",
        hashed_password=hash_password("password123"),
        role=UserRole.admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role, email=user.email
    )
    return {"tenant": tenant, "user": user, "token": token, "headers": {"Authorization": f"Bearer {token}"}}
