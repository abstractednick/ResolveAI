"""Input sanitization for ticket/email content."""

from __future__ import annotations

import html
import re

_SCRIPT_RE = re.compile(r"<script[\s\S]*?>[\s\S]*?</script>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_text(value: str, *, max_length: int = 50000) -> str:
    if not value:
        return ""
    cleaned = _SCRIPT_RE.sub("", value)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = _CTRL_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


def sanitize_email(value: str) -> str:
    value = (value or "").strip().lower()
    if "@" not in value or len(value) > 320:
        raise ValueError("Invalid email")
    return value
