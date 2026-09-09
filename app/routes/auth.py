"""Auth routes: register tenant+admin, login."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth import create_access_token, hash_password, verify_password
from app.db import get_session
from app.models import SLAPolicy, Tenant, User, UserRole, utcnow
from app.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.services.audit import log_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(Tenant).where(Tenant.slug == payload.tenant_slug)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tenant slug already exists")

    tenant = Tenant(name=payload.tenant_name, slug=payload.tenant_slug, created_at=utcnow())
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.admin,
        team="admin",
    )
    session.add(user)
    session.add(
        SLAPolicy(
            tenant_id=tenant.id,
            name="Default SLA",
            is_default=True,
        )
    )
    session.commit()
    session.refresh(user)

    log_audit(
        session,
        tenant_id=tenant.id,
        action="tenant_registered",
        resource_type="tenant",
        resource_id=str(tenant.id),
        actor_id=user.id,
        actor_email=user.email,
    )

    token = create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role, email=user.email
    )
    return TokenResponse(
        access_token=token,
        role=user.role,
        tenant_id=tenant.id,
        user_id=user.id,
        email=user.email,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)):
    tenant = session.exec(select(Tenant).where(Tenant.slug == payload.tenant_slug)).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = session.exec(
        select(User).where(User.tenant_id == tenant.id, User.email == payload.email.lower())
    ).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")

    token = create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role, email=user.email
    )
    return TokenResponse(
        access_token=token,
        role=user.role,
        tenant_id=tenant.id,
        user_id=user.id,
        email=user.email,
    )
