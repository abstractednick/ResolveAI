# ResolveAI — AI-Powered Ticket Automation & Support Resolution Platform

> Full production-grade support automation system — not an MVP. Classifies, resolves, routes, translates, and summarizes tickets end to end, with agent-assist tools and admin dashboard. Built to be handed straight to Cursor AI as a phased build plan.

---

## 1. Project Overview

**What it does:** Ingests tickets from any channel (email, widget, helpdesk API), classifies and prioritizes them, auto-resolves simple issues, drafts responses for agents, predicts SLA breaches, detects duplicates, and keeps the knowledge base self-updating — as a real deployable multi-tenant product.

---

## 2. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Python 3.11 + FastAPI | Async, scalable, clean for AI + webhook-heavy workloads |
| **AI Model** | Claude API (Anthropic) | Classification, reply drafting, summarization, translation |
| **Embeddings / Vector Search** | Claude embeddings + pgvector (Postgres) | Similar-ticket matching, KB search |
| **Primary DB** | PostgreSQL (Supabase/Railway) | Tickets, users, tenants, logs |
| **Cache / Queue** | Redis + Celery | Async jobs (classification, translation, SLA checks) |
| **Auth** | JWT + OAuth2 (Auth0 or custom) | Multi-tenant, agent + admin roles |
| **Ticket Ingestion** | REST API + Email parsing (Postmark/Resend inbound) + Zendesk/Freshdesk/Intercom connectors | Channel-agnostic intake |
| **Realtime Updates** | WebSockets (FastAPI native) | Live ticket status for agent dashboard |
| **Frontend** | Next.js + Tailwind + shadcn/ui | Agent dashboard, admin panel |
| **Translation** | Claude API | Multi-language ticket + reply translation |
| **Monitoring / Logging** | Sentry + Prometheus + Grafana | Error tracking, performance, SLA metrics |
| **CI/CD** | GitHub Actions | Automated test + deploy pipeline |
| **Deployment** | Docker + Railway/Render (scale-ready to Kubernetes) | Fast to ship, scales later |
| **Secrets/Config** | `.env` + Doppler or Vault (prod) | API keys, DB creds, per-tenant config |

---

## 3. Feature List

1. **Auto-Ticket Classification** — category, priority, team routing on arrival
2. **AI First-Response Agent** — instant contextual reply using ticket + KB
3. **Auto-Resolution Bot** — resolves common issues via tool-calls (reset password, order status)
4. **Sentiment & Urgency Detection** — auto-escalates angry/urgent tickets
5. **Similar Ticket Matcher** — vector search over resolved tickets, suggests fix
6. **Knowledge Base Auto-Updater** — drafts new KB articles from recurring unresolved issues
7. **Agent Reply Assistant** — full draft reply suggested inside agent's ticket view
8. **SLA Breach Predictor** — flags tickets at risk before breach
9. **Multi-Language Auto-Translate** — real-time translation both directions
10. **Ticket Summarizer** — condenses long threads for handoffs
11. **Customer Self-Service Deflection Widget** — answers before ticket is created
12. **Escalation Routing Agent** — routes complex tickets to right specialist
13. **CSAT Prediction & Proactive Follow-up** — predicts low satisfaction, triggers save action
14. **Duplicate Ticket Merger** — detects and merges duplicate/related tickets
15. **Multi-Tenant Admin Dashboard** — manage teams, routing rules, SLA policies per tenant
16. **Audit Logging & Compliance** — full action history per ticket for compliance/QA

---

## 4. Step-by-Step Development Plan — Cursor AI Prompts

Paste each prompt into Cursor in order. Test and commit after every phase.

### Phase 1 — Project Foundation
```
Create a production-grade FastAPI project called "resolveai" with this structure:
- app/main.py
- app/models/ (Tenant, User, Ticket, TicketEvent, KBArticle, SLAPolicy)
- app/db.py (Postgres + pgvector extension enabled via SQLModel/SQLAlchemy)
- app/auth/ (JWT auth, role-based access: admin, agent, viewer)
- app/config.py (.env: ANTHROPIC_API_KEY, DATABASE_URL, REDIS_URL, JWT_SECRET)
- app/services/, app/routes/, app/workers/ (empty, for later)
- requirements.txt: fastapi, uvicorn, sqlmodel, psycopg2-binary, pgvector, 
  anthropic, celery, redis, python-jose, python-dotenv, pytest
- Dockerfile + docker-compose.yml (app + postgres + redis)
- GitHub Actions workflow: run pytest on every push
Multi-tenant from day one: every table has a tenant_id column, every query scoped to it.
```

### Phase 2 — Ticket Ingestion
```
Build ticket ingestion from 3 sources:
1. POST /tickets (direct API/widget submission)
2. Inbound email webhook (Postmark/Resend inbound parse) -> creates ticket
3. Zendesk/Freshdesk webhook receiver -> normalizes external ticket into internal Ticket model
Ticket model: id, tenant_id, customer_email, subject, body, channel, status, 
priority, category, assigned_team, created_at.
Every new ticket triggers an async Celery job: classify_ticket(ticket_id).
```

### Phase 3 — Classification & Routing Engine
```
Create app/services/classifier.py. Function classify_ticket(ticket_id):
- Calls Claude API with ticket subject+body
- Returns category, priority (low/medium/high/urgent), suggested_team
- Updates the Ticket record
- If priority is urgent, trigger escalation_router immediately
Write this as a Celery task so it runs async right after ticket creation.
```

### Phase 4 — Sentiment & Urgency Detection
```
Extend classifier.py with analyze_sentiment(ticket_id):
- Scores tone: neutral / frustrated / angry
- If angry + high priority, auto-bump to top of queue and notify senior agent (via websocket + email)
Store sentiment_score on the Ticket model.
```

### Phase 5 — Similar Ticket Matcher + Knowledge Base
```
Set up pgvector on the KBArticle and Ticket tables (embedding column).
Create app/services/similarity.py:
- embed_ticket(ticket_id) generates embedding via Claude/embeddings API on creation
- find_similar_tickets(ticket_id) returns top 5 resolved tickets by vector similarity
- find_kb_article(ticket_id) returns best-matching KB article if similarity > threshold
Create app/services/kb_updater.py: 
- If 3+ similar unresolved tickets appear with no matching KB article, 
  auto-draft a new KBArticle via Claude and flag it for admin review.
```

### Phase 6 — Auto-Resolution Bot
```
Create app/services/auto_resolver.py using the Claude Agent SDK.
Give it tools: reset_password(customer_id), get_order_status(order_id), 
check_subscription_status(customer_id).
Function attempt_auto_resolve(ticket_id):
- If classification matches a known auto-resolvable category, let the agent 
  call the relevant tool and resolve the ticket directly
- Log every tool call and outcome to TicketEvent
- If it can't confidently resolve, leave ticket for a human agent
```

### Phase 7 — First-Response & Agent Reply Assistant
```
Create app/services/reply_assistant.py:
- generate_first_response(ticket_id): drafts contextual reply using ticket + 
  matched KB article + similar resolved tickets, sends automatically if 
  auto-resolvable, else stores as a suggested draft for agent review
- generate_agent_draft(ticket_id): same generation logic but always returns 
  draft only, surfaced in agent dashboard ticket view for edit + send
```

### Phase 8 — SLA Breach Predictor
```
Create app/services/sla_predictor.py:
- Given ticket's priority, current queue load, and historical response times, 
  compute breach_risk_score (0-1)
- Celery beat job runs every 15 min, flags tickets above risk threshold, 
  notifies team lead via dashboard alert + email
Add SLAPolicy model per tenant: response_time_targets by priority level.
```

### Phase 9 — Multi-Language Support
```
Create app/services/translator.py:
- detect_language(text) 
- translate_incoming(ticket_id) -> stores original + English translation
- translate_outgoing(reply_text, target_language) -> translates agent/AI reply 
  back to customer's language before sending
Wire this into ticket ingestion and reply sending automatically.
```

### Phase 10 — Ticket Summarizer & Duplicate Merger
```
Create app/services/summarizer.py: summarize_thread(ticket_id) condenses full 
ticket history into a 2-3 line summary, shown at top of agent view and used 
on agent handoff/shift change.
Create app/services/dedup.py: detect_duplicates(ticket_id) checks for tickets 
from same customer_email with similar embedding within last 48 hours, 
auto-merges into a single thread and notifies both queues.
```

### Phase 11 — Escalation Routing & CSAT Prediction
```
Create app/services/escalation.py: route_escalation(ticket_id) detects 
technical complexity/keywords, assigns to specialist queue or specific engineer 
based on tenant's routing rules.
Create app/services/csat_predictor.py: predict_csat(ticket_id) scores likely 
satisfaction from resolution tone + time-to-resolve; if predicted low, 
triggers a proactive "how did we do" follow-up before the survey goes out.
```

### Phase 12 — Self-Service Deflection Widget
```
Build a small embeddable widget (vanilla JS or React) that:
- Takes customer's typed question before ticket submission
- Searches KB + similar resolved tickets via the similarity service
- Shows likely answer first; only creates a ticket if customer says "still need help"
Serve via a public API endpoint POST /widget/query (rate-limited, tenant-scoped).
```

### Phase 13 — Admin Dashboard & Multi-Tenant Controls
```
Build a Next.js + Tailwind + shadcn/ui dashboard with:
- Agent view: ticket queue, filters, ticket detail with AI draft + similar tickets + KB suggestions
- Admin view: manage teams, routing rules, SLA policies, KB articles, tenant settings
- Live ticket status via WebSocket connection to backend
- Audit log viewer per ticket (every AI action + agent action, timestamped)
```

### Phase 14 — Testing, Security & Production Hardening
```
Add pytest coverage for every service in app/services/.
Add rate limiting (per-tenant) on all public endpoints.
Add input sanitization on ticket body/email content (XSS/injection safety).
Add row-level tenant isolation tests (tenant A can never see tenant B's data).
Set up Sentry for error tracking and Prometheus/Grafana for latency + SLA metrics.
Write a production README: environment setup, migration steps, scaling notes.
```

### Phase 15 — CI/CD & Deployment
```
Finalize GitHub Actions: run tests -> build Docker image -> deploy to Railway/Render 
on merge to main.
Add staging + production environments with separate DBs.
Add health check endpoint and uptime monitoring (e.g., Better Uptime/UptimeRobot).
Document rollback procedure in README.
```

---

## 5. Suggested Build Order Summary
1. Foundation → 2. Ingestion → 3. Classification → 4. Sentiment → 5. Similarity/KB → 
6. Auto-Resolution → 7. Reply Assistant → 8. SLA Predictor → 9. Translation → 
10. Summarizer/Dedup → 11. Escalation/CSAT → 12. Deflection Widget → 
13. Dashboard → 14. Hardening → 15. CI/CD & Deploy

---

## 6. Notes for Interview / Resume Framing
- **Why it's a full product, not an MVP:** multi-tenant from day one, auth + RBAC, 
  audit logging, SLA policies per tenant, production monitoring and CI/CD included.
- **Most complex piece:** auto-resolution bot — agent has to decide confidently 
  whether it can resolve or must hand off, using tool-calls with real side effects.
- **Agentic core:** classification → similarity search → auto-resolve attempt → 
  escalation/SLA check, all chained per ticket without hardcoded rules.
- **Claude usage:** classification, reply generation, summarization, translation, 
  and the auto-resolution agent all run on Claude.
