"""Admin: teams, SLA, routing, KB, alerts, audit."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import AdminUser, AgentUser, CurrentUser
from app.db import get_session
from app.models import Alert, AuditLog, KBArticle, RoutingRule, SLAPolicy, Team, Tenant, User, UserRole
from app.schemas import KBArticleCreate, KBArticleOut, RoutingRuleCreate, SLAPolicyCreate, TeamCreate
from app.services.audit import log_audit
from app.services.similarity import embed_kb_article
from app.auth import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tenant")
def get_tenant(user: CurrentUser, session: Session = Depends(get_session)):
    tenant = session.get(Tenant, user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "api_key": tenant.api_key,
        "settings": tenant.settings_json,
    }


@router.get("/teams")
def list_teams(user: CurrentUser, session: Session = Depends(get_session)):
    teams = session.exec(select(Team).where(Team.tenant_id == user.tenant_id)).all()
    return [{"id": str(t.id), "name": t.name, "slug": t.slug, "categories": t.categories} for t in teams]


@router.post("/teams")
def create_team(payload: TeamCreate, user: AdminUser, session: Session = Depends(get_session)):
    team = Team(tenant_id=user.tenant_id, name=payload.name, slug=payload.slug, categories=payload.categories)
    session.add(team)
    session.commit()
    session.refresh(team)
    log_audit(session, tenant_id=user.tenant_id, action="team_created", resource_type="team", resource_id=str(team.id), actor_id=user.id, actor_email=user.email)
    return {"id": str(team.id), "name": team.name, "slug": team.slug}


@router.get("/sla")
def list_sla(user: CurrentUser, session: Session = Depends(get_session)):
    policies = session.exec(select(SLAPolicy).where(SLAPolicy.tenant_id == user.tenant_id)).all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "response_targets": p.response_targets,
            "resolution_targets": p.resolution_targets,
            "is_default": p.is_default,
        }
        for p in policies
    ]


@router.post("/sla")
def create_sla(payload: SLAPolicyCreate, user: AdminUser, session: Session = Depends(get_session)):
    if payload.is_default:
        existing = session.exec(select(SLAPolicy).where(SLAPolicy.tenant_id == user.tenant_id, SLAPolicy.is_default == True)).all()  # noqa: E712
        for p in existing:
            p.is_default = False
            session.add(p)
    policy = SLAPolicy(
        tenant_id=user.tenant_id,
        name=payload.name,
        response_targets=payload.response_targets,
        resolution_targets=payload.resolution_targets,
        is_default=payload.is_default,
    )
    session.add(policy)
    session.commit()
    session.refresh(policy)
    return {"id": str(policy.id), "name": policy.name}


@router.get("/routing-rules")
def list_rules(user: CurrentUser, session: Session = Depends(get_session)):
    rules = session.exec(select(RoutingRule).where(RoutingRule.tenant_id == user.tenant_id)).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "keywords": r.keywords,
            "categories": r.categories,
            "assign_team": r.assign_team,
            "assign_agent_email": r.assign_agent_email,
            "priority_override": r.priority_override,
            "is_active": r.is_active,
        }
        for r in rules
    ]


@router.post("/routing-rules")
def create_rule(payload: RoutingRuleCreate, user: AdminUser, session: Session = Depends(get_session)):
    rule = RoutingRule(
        tenant_id=user.tenant_id,
        name=payload.name,
        keywords=payload.keywords,
        categories=payload.categories,
        assign_team=payload.assign_team,
        assign_agent_email=payload.assign_agent_email,
        priority_override=payload.priority_override,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return {"id": str(rule.id), "name": rule.name}


@router.get("/kb", response_model=list[KBArticleOut])
def list_kb(user: CurrentUser, session: Session = Depends(get_session)):
    articles = session.exec(select(KBArticle).where(KBArticle.tenant_id == user.tenant_id)).all()
    return [KBArticleOut.model_validate(a) for a in articles]


@router.post("/kb", response_model=KBArticleOut)
def create_kb(payload: KBArticleCreate, user: AdminUser, session: Session = Depends(get_session)):
    article = KBArticle(
        tenant_id=user.tenant_id,
        title=payload.title,
        content=payload.content,
        category=payload.category,
        tags=payload.tags,
        status=payload.status,
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    embed_kb_article(article.id, session=session)
    return KBArticleOut.model_validate(article)


@router.patch("/kb/{article_id}/publish", response_model=KBArticleOut)
def publish_kb(article_id: UUID, user: AdminUser, session: Session = Depends(get_session)):
    article = session.get(KBArticle, article_id)
    if not article or article.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Article not found")
    article.status = "published"
    session.add(article)
    session.commit()
    session.refresh(article)
    return KBArticleOut.model_validate(article)


@router.get("/alerts")
def list_alerts(user: AgentUser, session: Session = Depends(get_session), limit: int = 50):
    alerts = session.exec(
        select(Alert)
        .where(Alert.tenant_id == user.tenant_id)
        .order_by(Alert.created_at.desc())  # type: ignore
        .limit(limit)
    ).all()
    return [
        {
            "id": str(a.id),
            "ticket_id": str(a.ticket_id) if a.ticket_id else None,
            "alert_type": a.alert_type,
            "message": a.message,
            "severity": a.severity,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: UUID, user: AgentUser, session: Session = Depends(get_session)):
    alert = session.get(Alert, alert_id)
    if not alert or alert.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    session.add(alert)
    session.commit()
    return {"ok": True}


@router.get("/audit")
def list_audit(user: AdminUser, session: Session = Depends(get_session), limit: int = 100):
    logs = session.exec(
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .order_by(AuditLog.created_at.desc())  # type: ignore
        .limit(limit)
    ).all()
    return [
        {
            "id": str(l.id),
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "actor_email": l.actor_email,
            "details": l.details,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]


@router.post("/users")
def create_user(
    email: str,
    full_name: str,
    password: str,
    user: AdminUser,
    role: UserRole = UserRole.agent,
    team: str | None = None,
    session: Session = Depends(get_session),
):
    existing = session.exec(select(User).where(User.tenant_id == user.tenant_id, User.email == email.lower())).first()
    if existing:
        raise HTTPException(status_code=400, detail="User exists")
    new_user = User(
        tenant_id=user.tenant_id,
        email=email.lower(),
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role,
        team=team,
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    return {"id": str(new_user.id), "email": new_user.email, "role": new_user.role}
