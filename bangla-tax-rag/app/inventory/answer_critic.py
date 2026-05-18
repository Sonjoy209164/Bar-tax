"""
Self-critique loop: the bot proofreads its own answer.

After the answer is generated, the critic asks the LLM:
  - Does this actually address the customer's question?
  - Are the prices, stock counts, and product names consistent with the
    catalog snippets we showed it?
  - Did we make up any claim not supported by the catalog?
  - Did we ignore a slot the customer cared about (budget, color, size)?

If any check fails, the critic returns suggested_fix text and the caller
can regenerate the answer once. We do at most ONE regenerate cycle —
infinite critique loops are how bots get stuck.

Failure mode: if the critic itself errors, treat the answer as "passes"
so we never block on critic infrastructure.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434"
_OLLAMA_MODEL = "qwen3:8b"
_OLLAMA_TIMEOUT = 10.0


@dataclass(frozen=True)
class CritiqueResult:
    passes: bool
    issues: list[str] = field(default_factory=list)
    suggested_fix: str = ""
    severity: str = "ok"  # ok | minor | major
    raw: dict[str, Any] = field(default_factory=dict)


_PROMPT = """\
You are a quality reviewer for a boutique chatbot's answers. Read the
customer's question, the bot's answer, and the product facts. Decide
whether the answer is acceptable.

Criteria (in order of importance):
  1. The answer must NOT claim anything not supported by the product facts.
     (e.g. saying "in stock" when stock=0 is a MAJOR issue.)
  2. The answer must address the customer's actual question, not a
     different question.
  3. The answer must respect explicit constraints the customer mentioned
     (budget, color, size, occasion).
  4. The answer should be in the same language the customer used.

Return ONLY a single JSON object — no preamble, no markdown.

JSON schema:
{
  "passes":         <true | false>,
  "severity":       <"ok" | "minor" | "major">,
  "issues":         [<short string>, ...],
  "suggested_fix":  <one short sentence — what should be different>
}

Mark `passes: true` for "ok" and "minor" severity. Mark `passes: false`
ONLY for "major" issues (factually wrong, hallucinated product, ignored
critical constraint).

Customer question: {question}

Product facts (the only ground truth — anything else is hallucination):
{products}

Bot's answer:
{answer}

Output:"""


def critique_answer(
    *,
    question: str,
    answer: str,
    product_snippets: list[dict[str, Any]],
    ollama_url: str = _OLLAMA_URL,
    model: str = _OLLAMA_MODEL,
    timeout: float = _OLLAMA_TIMEOUT,
) -> CritiqueResult:
    """
    Critique an answer. Returns CritiqueResult; on infrastructure failure,
    returns a passing result so we never block on the critic.
    """
    if not answer.strip():
        return CritiqueResult(
            passes=False,
            issues=["empty_answer"],
            suggested_fix="Generate an actual response.",
            severity="major",
        )

    prompt = (
        _PROMPT
        .replace("{question}", question)
        .replace("{products}", _render_products(product_snippets))
        .replace("{answer}", answer)
    )

    try:
        resp = httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 220},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw_text = resp.json().get("response", "").strip()
    except Exception as exc:
        logger.debug("Answer critic HTTP failure (treating as pass): %s", exc)
        return CritiqueResult(passes=True, severity="ok")

    parsed = _parse_json_lenient(raw_text)
    if not isinstance(parsed, dict):
        logger.debug("Critic non-dict output: %r", raw_text[:200])
        return CritiqueResult(passes=True, severity="ok")

    return _build_critique(parsed)


def _render_products(snippets: list[dict[str, Any]]) -> str:
    if not snippets:
        return "(no products — this is a policy/general question)"
    lines: list[str] = []
    for i, p in enumerate(snippets[:5], 1):
        name = p.get("name", "?")
        price = p.get("price")
        stock = p.get("stock")
        attrs = p.get("attributes", {}) or {}
        attr_parts = []
        for key in ("color", "fabric", "size", "occasion", "work_type"):
            v = attrs.get(key)
            if v:
                attr_parts.append(f"{key}={v}")
        price_str = f"BDT {price:,.0f}" if isinstance(price, (int, float)) else "Price N/A"
        lines.append(
            f"{i}. {name} | {price_str} | stock={stock} | {' | '.join(attr_parts) or '—'}"
        )
    return "\n".join(lines)


def _parse_json_lenient(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip("` \n")
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _build_critique(payload: dict[str, Any]) -> CritiqueResult:
    severity = str(payload.get("severity") or "ok").lower()
    if severity not in {"ok", "minor", "major"}:
        severity = "ok"

    raw_passes = payload.get("passes")
    if isinstance(raw_passes, bool):
        passes = raw_passes
    else:
        passes = severity in {"ok", "minor"}

    issues_raw = payload.get("issues") or []
    if not isinstance(issues_raw, list):
        issues_raw = []
    issues = [str(x) for x in issues_raw if x][:5]

    fix = str(payload.get("suggested_fix") or "").strip()

    return CritiqueResult(
        passes=passes,
        issues=issues,
        suggested_fix=fix,
        severity=severity,
        raw=payload,
    )
