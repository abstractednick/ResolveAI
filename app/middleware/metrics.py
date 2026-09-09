"""Prometheus metrics endpoint helpers."""

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

REQUEST_COUNT = Counter(
    "resolveai_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "resolveai_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)
TICKETS_CREATED = Counter("resolveai_tickets_created_total", "Tickets created", ["tenant", "channel"])
AI_ACTIONS = Counter("resolveai_ai_actions_total", "AI actions", ["action"])
