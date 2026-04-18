"""Condense a fetched article into ExtractedArticle via a local LLM.

The extraction prompt is assembled from a stable base plus an optional
per-context "focus block" built from the context's manifest. Same schema,
different priorities per domain.
"""
from __future__ import annotations

import logging
from datetime import datetime

from weaver.contexts.manifest import FocusConfig
from weaver.indexer.llm_client import LLMClient, parse_json_with_retry
from weaver.indexer.models import ExtractedArticle

log = logging.getLogger(__name__)


_BASE_SYSTEM = """You are a structured extraction engine. Read an article and
emit a JSON object matching the schema below.

Schema (all fields required, use [] or null where nothing applies):

{
  "summary":        string,   // 2-4 paragraphs, information-dense. NO meta-commentary like "the article argues…". Summarize the substantive claims.
  "key_concepts":   string[], // up to 10 canonical concept names (prefer "retrieval-augmented generation" over "RAG-based retrieval")
  "people":         [{ "name": string, "role": string|null, "affiliation": string|null }],
  "projects":       [{ "name": string, "url": string|null, "description": string|null }],
  "technologies":   string[], // frameworks, libraries, tools, algorithms, or model names mentioned
  "references":     string[]  // URLs cited inline
}

Rules:
- Output ONLY the JSON object, no markdown fences, no prose.
- Use canonical names: "Andrej Karpathy" not "A. Karpathy" or "Karpathy, Andrej".
- Skip UI chrome, nav menus, comment sections, subscribe widgets, cookie banners.
- If the content is an index/listing page with no substantive article, return empty arrays and a one-sentence summary indicating that.
- Deduplicate people/projects across the article.
"""


def build_system_prompt(focus: FocusConfig | None = None) -> str:
    """Assemble the full system prompt, weaving in per-context focus guidance."""
    if focus is None or not _has_any_focus(focus):
        return _BASE_SYSTEM

    lines = [_BASE_SYSTEM.rstrip(), "", "FOCUS (this context):"]
    if focus.primary_topics:
        lines.append("Prioritize substance on these topics:")
        for t in focus.primary_topics:
            lines.append(f"  - {t}")
    if focus.exclude_topics:
        lines.append("")
        lines.append("De-emphasize or skip these topics:")
        for t in focus.exclude_topics:
            lines.append(f"  - {t}")
    if focus.entity_types:
        lines.append("")
        lines.append(
            "Entity types of interest (in addition to the schema's default "
            "people/projects/technologies):"
        )
        lines.append(f"  {', '.join(focus.entity_types)}")
        lines.append(
            "If an entity doesn't fit the schema (e.g. 'company' or 'institution'), "
            "record it under `projects` with a clarifying description."
        )
    if focus.extra_instruction:
        lines.append("")
        lines.append("Additional guidance:")
        lines.append(focus.extra_instruction.rstrip())

    return "\n".join(lines) + "\n"


def _has_any_focus(f: FocusConfig) -> bool:
    return bool(
        f.primary_topics or f.exclude_topics
        or f.entity_types or f.extra_instruction
    )

_USER_TEMPLATE = """Source: {source}
URL: {url}
Published: {published_at}
Title: {title}

---

{body}
"""


def condense_article(
    llm: LLMClient,
    *,
    source: str,
    url: str,
    title: str,
    body_text: str,
    published_at: datetime | None = None,
    focus: FocusConfig | None = None,
    max_body_chars: int = 24_000,
    max_retries: int = 1,
    timeout_s: float = 180.0,
) -> tuple[ExtractedArticle, dict[str, object]]:
    """Run the LLM extraction. Returns (extracted, telemetry)."""
    if len(body_text) > max_body_chars:
        body_text = body_text[:max_body_chars].rstrip() + "\n…[truncated]"

    user = _USER_TEMPLATE.format(
        source=source,
        url=url,
        published_at=published_at.isoformat() if published_at else "unknown",
        title=title or "(untitled)",
        body=body_text,
    )

    system_prompt = build_system_prompt(focus)

    extracted, completion = parse_json_with_retry(
        llm,
        system=system_prompt,
        user=user,
        validator=ExtractedArticle.model_validate,
        max_retries=max_retries,
        timeout_s=timeout_s,
    )
    telemetry = {
        "model": completion.model,
        "prompt_tokens": completion.prompt_tokens,
        "completion_tokens": completion.completion_tokens,
        "duration_ms": completion.total_duration_ms,
    }
    return extracted, telemetry
