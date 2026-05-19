"""
Layer 4 of the conversation entry point: reply rendering.

Loads `config/boundary_templates.yaml` once and exposes a single function:

    render_template(boundary_type, language, slots, categories) -> (answer, follow_up)

Detection logic does NOT live here. This file only turns a structured
BoundaryDecision payload into a human-language reply, with category and
event substitutions.
"""
from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

import yaml

_TEMPLATES_PATH = Path(__file__).resolve().parents[2] / "config" / "boundary_templates.yaml"

_cache: dict[str, Any] | None = None
_cache_lock = Lock()


def _load_templates() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    with _cache_lock:
        if _cache is not None:
            return _cache
        with _TEMPLATES_PATH.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise RuntimeError(f"{_TEMPLATES_PATH} did not parse to a mapping")
        _cache = data
        return _cache


def reload_templates() -> None:
    """Force-reload from disk. Useful for tests and hot edits."""
    global _cache
    with _cache_lock:
        _cache = None


def render_template(
    *,
    boundary_type: str,
    language: str,
    slots: dict[str, Any],
    categories: tuple[str, ...],
) -> tuple[str, str | None]:
    """Resolve the template for (boundary_type, language) and substitute slots.

    Falls back to the per-language `defaults` block when the boundary_type is
    not in the YAML. Occasion-style boundary types (`occasion_<event>`) all
    share the single `occasion` template; the event label is substituted via
    {event}.
    """
    data = _load_templates()
    templates: dict[str, Any] = data.get("templates", {})
    defaults_block: dict[str, Any] = data.get("defaults", {})

    template_key, event_key = _resolve_template_key(boundary_type, slots)
    block = templates.get(template_key)
    if not isinstance(block, dict):
        return _render_default(defaults_block, language)

    per_language = block.get(language) or block.get("english") or {}
    answer_tpl = per_language.get("answer") or ""
    follow_up_tpl = per_language.get("follow_up")

    substitutions = _build_substitutions(
        language=language,
        categories=categories,
        event_key=event_key,
        slots=slots,
        data=data,
    )
    answer = _safe_format(answer_tpl, substitutions)
    follow_up = _safe_format(follow_up_tpl, substitutions) if follow_up_tpl else None
    return answer, follow_up


def _resolve_template_key(boundary_type: str, slots: dict[str, Any]) -> tuple[str, str | None]:
    if boundary_type.startswith("occasion_"):
        return "occasion", boundary_type[len("occasion_"):]
    if boundary_type == "occasion":
        event = slots.get("occasion")
        return "occasion", event if isinstance(event, str) else None
    return boundary_type, None


def _render_default(defaults_block: dict[str, Any], language: str) -> tuple[str, str | None]:
    block = defaults_block.get(language) or defaults_block.get("english") or {}
    answer = block.get("answer") or ""
    follow_up = block.get("follow_up")
    return answer, follow_up


def _build_substitutions(
    *,
    language: str,
    categories: tuple[str, ...],
    event_key: str | None,
    slots: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, str]:
    subs = {
        "categories": _category_phrase(categories, language=language, data=data),
        "event": _event_label(event_key, language=language, data=data),
        "recipient": str(slots.get("recipient") or ""),
    }
    return subs


def _category_phrase(categories: tuple[str, ...], *, language: str, data: dict[str, Any]) -> str:
    if not categories:
        return "products" if language != "bangla" else "পণ্য"
    if language == "bangla":
        labels_map: dict[str, str] = (data.get("category_labels", {}) or {}).get("bangla", {})
        labels = [labels_map.get(cat, cat) for cat in categories[:5]]
    else:
        labels = [cat.replace("_", " ") for cat in categories[:5]]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + ", or " + labels[-1]


def _event_label(event_key: str | None, *, language: str, data: dict[str, Any]) -> str:
    if not event_key:
        return "this situation" if language == "english" else (
            "ei situation" if language == "banglish" else "এই অবস্থা"
        )
    labels: dict[str, dict[str, str]] = data.get("event_labels", {}) or {}
    entry = labels.get(event_key)
    if not isinstance(entry, dict):
        return event_key.replace("_", " ")
    return entry.get(language) or entry.get("english") or event_key


def _safe_format(template: str, substitutions: dict[str, str]) -> str:
    """`str.format_map` with a non-crashing default for unknown keys."""
    return template.format_map(_DefaultDict(substitutions))


class _DefaultDict(dict):
    def __missing__(self, key: str) -> str:  # noqa: D401
        return "{" + key + "}"


__all__ = ["render_template", "reload_templates"]
