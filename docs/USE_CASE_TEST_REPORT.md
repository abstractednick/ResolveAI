# ResolveAI — Use-case verification notes

**API under test:** `http://127.0.0.1:8010`  
**Environment:** local development, rule-based model responses when `ANTHROPIC_API_KEY` is unset  

## Summary

| Metric | Value |
|---|---|
| Assertions | 46 / 48 passed (95.8%) |
| Scenarios | 7 |
| Crashes | 0 |

---

## Pipeline (every new ticket)

```text
1  translate_incoming
2  classify
3  analyze_sentiment
4  embed_ticket
5  detect_duplicates
6  find_similar_tickets
7  find_kb_article
8  attempt_auto_resolve
9  generate_first_response
10 predict_sla
11 summarize_thread
12 predict_csat (if resolved)
13 maybe_draft_kb
```

Inspect a ticket:

```bash
GET /api/v1/tickets/{id}
GET /api/v1/tickets/{id}/events
GET /api/v1/tickets/{id}/messages
```

---

## Scenarios

### UC1 — Password reset (pass)

- Category `account_access`, team `identity`, priority `urgent`, sentiment angry
- Tool: `reset_password` → resolved automatically
- Events include `classified`, `tool_called`, `auto_resolved`, `summarized`, `csat_predicted`

### UC2 — Order status (pass)

- Category `orders`, team `commerce`
- Tool: `get_order_status(ORD-778899)` → resolved

### UC3 — Billing / subscription (pass)

- Category `billing`, team `billing`
- Tool: `check_subscription_status` → resolved

### UC4 — Complex technical issue (pass)

- Category `general`, status remains `open`
- Event `auto_resolve_skipped` — no tool call; draft stored for the agent, not sent as a resolution

### UC5 — Email inbound webhook (pass)

- `POST /api/v1/webhooks/email/inbound` with `X-Tenant-Key`
- Channel `email`; same pipeline as API tickets

### UC6 — Zendesk webhook (pass)

- Normalized with `external_id`, channel `zendesk`
- Classified; left open when no confident tool path applied

### UC7 — Duplicate merge (partial)

- Two similar password tickets from the same email both auto-resolved
- Merge did not fire because cosine similarity stayed below `SIMILARITY_THRESHOLD` (0.78)
- Unit test `test_dedup_merges` covers the merge path when vectors are close enough

---

## Other checks

| Area | Result |
|---|---|
| `/health`, `/ready`, `/metrics` | Pass |
| Demo login | Pass |
| Widget query | Pass |
| Agent draft + summarize endpoints | Pass |
| Tenant isolation (cross-tenant GET → 404) | Pass |
| Admin teams / SLA / KB / alerts | Pass |
| Admin `AuditLog` list | Empty in this run — ticket history is on `TicketEvent` |

---

## Event meanings

| Event | Meaning |
|---|---|
| `classified` | Category / priority / team set |
| `sentiment_escalated` | Angry + elevated priority → alert |
| `tool_called` | Auto-resolver invoked a tool |
| `auto_resolved` | Bot closed the ticket |
| `auto_resolve_skipped` | Bot refused; human owns it |
| `first_response_drafted` | Suggested reply exists |
| `summarized` | Handoff summary written |
| `csat_predicted` | Satisfaction score after resolve |
| `duplicate_merged` / `merged_into` | Dedup succeeded |
