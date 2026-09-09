# ResolveAI

### AI-Powered Ticket Automation & Support Resolution Platform

<p align="center">
  <img src="docs/screenshots/02-dashboard.png" alt="ResolveAI Agent Dashboard" width="100%" />
</p>

<p align="center">
  <b>Ingest → Classify → Resolve → Route → Translate → Summarize</b><br/>
  End-to-end support automation with agent-assist tools and a multi-tenant admin dashboard.
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Async%20API-009688?style=flat&logo=fastapi&logoColor=white" />
  <img alt="Claude" src="https://img.shields.io/badge/AI-Claude%20API-D97706?style=flat" />
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-14-000000?style=flat&logo=next.js&logoColor=white" />
  <img alt="Postgres" src="https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=flat&logo=postgresql&logoColor=white" />
  <img alt="Tests" src="https://img.shields.io/badge/Tests-14%20passing-22C55E?style=flat" />
</p>

---

## Why this project exists

Support teams drown in repetitive tickets. ResolveAI is a **production-shaped, multi-tenant product** that doesn't stop at "AI chat" — it runs a full agentic pipeline on every ticket:

1. Translate incoming language  
2. Classify category / priority / team  
3. Detect sentiment & escalate anger  
4. Embed + find similar resolved tickets + KB matches  
5. Attempt auto-resolution with tool calls  
6. Draft first response / agent reply  
7. Score SLA breach risk  
8. Summarize thread for handoff  
9. Predict CSAT and trigger save actions  
10. Auto-draft KB articles from recurring unresolved issues  

Built as a portfolio-grade system: **auth + RBAC, tenant isolation, audit logs, webhooks, WebSockets, CI, Docker, metrics**.

---

## Live product screenshots

### Sign in / create workspace
<img src="docs/screenshots/01-login.png" alt="ResolveAI login" width="100%" />

### Agent queue — live filters, AI summaries, auto-resolved badges, escalation alerts
<img src="docs/screenshots/02-dashboard.png" alt="ResolveAI dashboard" width="100%" />

### Ticket detail — sentiment, SLA risk, CSAT prediction, AI draft, full audit trail
<img src="docs/screenshots/03-ticket-detail.png" alt="Ticket detail with AI assist" width="100%" />

### Admin — teams, SLA policies, routing rules, KB, tenant API key, audit log
<img src="docs/screenshots/04-admin.png" alt="Admin multi-tenant controls" width="100%" />

### OpenAPI surface — JWT-secured FastAPI with health / ready / metrics
<img src="docs/screenshots/05-api-docs.png" alt="Swagger API docs" width="100%" />

---

## Architecture

```text
                    ┌──────────────────────────────┐
   Email / Widget / │     FastAPI  (async API)     │
   Zendesk / API ──►│  JWT · RBAC · rate limits    │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │     Ticket Pipeline (AI)     │
                    │  Claude + local embeddings   │
                    │  classify → resolve → SLA…   │
                    └──────┬─────────────┬─────────┘
                           │             │
              ┌────────────▼──┐     ┌────▼────────────┐
              │  PostgreSQL   │     │ Redis + Celery  │
              │  (+ pgvector) │     │ workers + beat  │
              └───────────────┘     └─────────────────┘
                           │
              ┌────────────▼───────────────────────┐
              │ Next.js Dashboard + Embed Widget   │
              │ WebSocket live updates             │
              └────────────────────────────────────┘
```

| Layer | Stack |
|---|---|
| Backend | Python · FastAPI · SQLModel · JWT/OAuth2-style auth |
| AI | Anthropic Claude (classification, drafts, translation, summarization, agent tools) |
| Similarity | Deterministic embeddings + cosine search (Voyage/OpenAI-ready swap) |
| Data | PostgreSQL · Redis · Celery |
| Frontend | Next.js 14 · Tailwind · agent + admin views |
| Ops | Docker Compose · GitHub Actions · Prometheus `/metrics` · Sentry hook |

---

## Feature map (16 capabilities)

| # | Feature | What it does |
|---:|---|---|
| 1 | Auto classification | Category, priority, team routing on arrival |
| 2 | AI first-response | Contextual reply from ticket + KB + similars |
| 3 | Auto-resolution bot | Tool calls: password reset, order status, subscription |
| 4 | Sentiment & urgency | Angry + high priority → escalate + alert |
| 5 | Similar ticket matcher | Vector similarity over resolved tickets |
| 6 | KB auto-updater | Drafts articles from 3+ recurring open issues |
| 7 | Agent reply assistant | Editable draft inside ticket view |
| 8 | SLA breach predictor | Risk score + Celery beat scan every 15 min |
| 9 | Multi-language | Detect / translate in + out |
| 10 | Ticket summarizer | 2–3 line handoff summary |
| 11 | Deflection widget | Answer before ticket creation |
| 12 | Escalation router | Keyword / rule / complexity routing |
| 13 | CSAT prediction | Low score → proactive follow-up |
| 14 | Duplicate merger | Same customer + similar embedding (48h) |
| 15 | Multi-tenant admin | Teams, SLA, routing, KB, audit |
| 16 | Compliance audit | Every AI + agent action timestamped |

---

## Agentic pipeline (the interesting part)

Every new ticket triggers:

```text
translate → classify → sentiment → embed → dedup
        → similar/KB → auto_resolve(tools)
        → first_response → sla_risk → summarize
        → csat (if resolved) → kb_draft_check
```

**Auto-resolver tools**

- `reset_password(customer_id)`
- `get_order_status(order_id)`
- `check_subscription_status(customer_id)`

If confidence is low, the ticket stays with a human — no silent wrong resolves.

---

## Quick start

### Option A — local (SQLite, zero infra)

```bash
git clone https://github.com/abstractednick/ResolveAI.git
cd ResolveAI

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python scripts/seed.py
uvicorn app.main:app --reload --port 8000

# new terminal
cd frontend && npm install && npm run dev
```

**Demo login**

| Field | Value |
|---|---|
| Workspace slug | `demo` |
| Email | `admin@demo.resolveai` |
| Password | `demo12345` |

- API docs → http://localhost:8000/docs  
- Dashboard → http://localhost:3000  
- Widget demo → open `widget/index.html`

### Option B — Docker (Postgres + Redis + Celery + API + Frontend)

```bash
cp .env.example .env
# set JWT_SECRET and optionally ANTHROPIC_API_KEY
docker compose up --build
docker compose exec api python scripts/seed.py
```

> Tip: without `ANTHROPIC_API_KEY`, Claude calls use deterministic offline fallbacks so the product still demos end-to-end.

---

## API cheat sheet

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/register` | Create tenant + admin |
| `POST /api/v1/auth/login` | JWT login |
| `POST /api/v1/tickets` | Create ticket (runs pipeline) |
| `POST /api/v1/public/tickets` | Public create with `X-Tenant-Key` |
| `POST /api/v1/webhooks/email/inbound` | Postmark/Resend inbound |
| `POST /api/v1/webhooks/zendesk` | Helpdesk normalize |
| `POST /api/v1/widget/query` | Self-service deflection |
| `WS /ws/{tenant_id}` | Live dashboard events |
| `GET /health` · `/ready` · `/metrics` | Ops |

---

## Project structure

```text
app/
  auth/          JWT + RBAC
  models/        Tenant, User, Ticket, KB, SLA, Audit…
  routes/        auth, tickets, webhooks, widget, admin
  services/      classifier, resolver, SLA, translate, …
  workers/       Celery tasks + beat schedule
frontend/        Next.js agent + admin UI
widget/          Embeddable deflection widget
tests/           Isolation + pipeline coverage
docs/screenshots Product screenshots
```

---

## Engineering highlights (interview talking points)

- **Multi-tenant from day one** — every table has `tenant_id`; queries are scoped; tests prove tenant A cannot read tenant B.
- **Agentic core, not prompt spaghetti** — chained services with tool side-effects and confidence gating.
- **Production hardening** — rate limits, XSS sanitization, audit events, health/ready, Prometheus metrics, CI on push.
- **Graceful degradation** — works without Redis workers (inline pipeline in non-prod) and without Claude (offline fallbacks).
- **Operator UX** — live WebSocket queue, AI draft regenerate, escalation alerts, admin controls for SLA/routing/KB.

---

## Tests & CI

```bash
pytest -q
# 14 passed
```

GitHub Actions (`.github/workflows/ci.yml`):

1. Install + pytest  
2. Build Docker image on `main`  
3. Deploy placeholder ready for Railway/Render secrets  

---

## Production notes

- Set strong `JWT_SECRET`, managed Postgres (`DATABASE_URL`), Redis, and `ANTHROPIC_API_KEY`
- `APP_ENV=production` enables async Celery workers (run worker + beat)
- Swap local embeddings in `app/services/embeddings.py` for Voyage/OpenAI when scaling similarity
- Monitor `/metrics`, wire `SENTRY_DSN`, uptime-check `/health` + `/ready`
- Rollback = previous Docker image tag + DB snapshot if migrations applied

---

## Author

**Nirmal Tailor** — AI / Full-stack engineer  

Building agentic systems that ship: classification pipelines, tool-using bots, multi-tenant SaaS, and operator dashboards.

🔗 Repo: [github.com/abstractednick/ResolveAI](https://github.com/abstractednick/ResolveAI)

---

<p align="center"><i>ResolveAI — ticket automation that behaves like a product, not a demo notebook.</i></p>
