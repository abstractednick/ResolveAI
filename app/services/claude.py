"""LLM client backed by Anthropic, with local rule-based responses when no API key is set."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


class ClaudeClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        if self.settings.anthropic_api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
            except Exception as exc:  # pragma: no cover
                logger.warning("Anthropic client init failed: %s", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        if not self._client:
            return self._local_response(system, user)
        try:
            message = self._client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            parts = []
            for block in message.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
            return "\n".join(parts).strip()
        except Exception as exc:
            logger.exception("Anthropic API error: %s", exc)
            return self._local_response(system, user)

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        fallback: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        raw = self.complete(
            system=system + "\nRespond with valid JSON only.",
            user=user,
            max_tokens=800,
        )
        try:
            return _extract_json(raw)
        except Exception:
            return fallback or {}

    def _local_response(self, system: str, user: str) -> str:
        """Keyword heuristics used when ANTHROPIC_API_KEY is unset."""
        lower = (system + " " + user).lower()
        if "classif" in lower:
            priority = "urgent" if any(w in lower for w in ("urgent", "asap", "down", "outage")) else "medium"
            if any(w in lower for w in ("password", "login", "reset")):
                category, team = "account_access", "identity"
            elif any(w in lower for w in ("order", "shipping", "refund")):
                category, team = "orders", "commerce"
            elif any(w in lower for w in ("bill", "invoice", "payment", "subscription")):
                category, team = "billing", "billing"
            else:
                category, team = "general", "support"
            return json.dumps(
                {
                    "category": category,
                    "priority": priority,
                    "suggested_team": team,
                    "confidence": 0.55,
                    "reasoning": "local classifier",
                }
            )
        if "sentiment" in lower:
            if any(w in lower for w in ("angry", "furious", "lawsuit", "terrible")):
                tone, score = "angry", 0.9
            elif any(w in lower for w in ("frustrated", "annoyed", "again", "still waiting")):
                tone, score = "frustrated", 0.65
            else:
                tone, score = "neutral", 0.2
            return json.dumps({"sentiment": tone, "sentiment_score": score})
        if "translat" in lower and "detect" in lower:
            return json.dumps({"language": "en", "confidence": 0.5})
        if "summar" in lower:
            return (
                "Customer reported an account or service issue. Key details are in the latest message. "
                "Confirm resolution steps and remaining open questions before closing."
            )
        if "csat" in lower:
            return json.dumps({"predicted_csat": 0.7, "reason": "local estimate"})
        if "kb article" in lower or "knowledge base" in lower:
            return json.dumps(
                {
                    "title": "Draft: Common support issue",
                    "content": "Draft article from recurring tickets. Review and publish after verification.",
                    "category": "general",
                    "tags": ["auto-draft"],
                }
            )
        if "reply" in lower or "response" in lower:
            return (
                "Thanks for reaching out. We've received your request and are looking into it. "
                "We'll follow up shortly with next steps."
            )
        if "widget" in lower or "answer the customer" in lower:
            return json.dumps(
                {
                    "answered": False,
                    "answer": None,
                    "confidence": 0.3,
                }
            )
        return json.dumps({"ok": True, "message": "local response"})


_claude: Optional[ClaudeClient] = None


def get_claude() -> ClaudeClient:
    global _claude
    if _claude is None:
        _claude = ClaudeClient()
    return _claude
