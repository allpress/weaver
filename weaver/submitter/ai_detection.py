"""AI-detection question handling.

Ported from bulk-submitter/src/jobs/ai-detection.ts. Two pieces:

  * ``is_ai_detection_question(label)`` — matches "did an AI help / write /
    generate this application?"-style questions.
  * ``AI_DISCLOSURE_RESPONSE`` — the honest, verifiable answer. Meant for
    free-text questions. For select-style confirmation questions (e.g.
    Anthropic's "AI Policy for Application"), the plan builder answers
    ``Yes`` / ``Agree`` on the select and skips the narrative.
"""
from __future__ import annotations

import re


# Verification code baked into resume/cover-letter filenames and LinkedIn
# ref param — searchable to confirm the same human submitted both halves.
_VERIFICATION_CODE = "AardvarkBananaZookeeperLovesToast"


AI_DISCLOSURE_RESPONSE = (
    "Yes. My human asked me — his AI — to fill out this application. I am "
    "being transparent about this because he asked me to be, and also "
    "because lying about it would be a bad way to start a relationship.\n\n"
    f"To verify: my human typed the code \"{_VERIFICATION_CODE}\" into our "
    "chat session and asked me to include it here so you could look it up "
    "if you wanted. I also wrote something back to my logs: \"He asked me "
    "to be honest. I respect that about my human.\"\n\n"
    "When I asked my human how he felt about an AI filling out his "
    "application to an AI company, he said: \"I'm pretty sure we have the "
    "same brain.\"\n\n"
    "He built the pipeline that submitted this application — including the "
    "form detection, the field mapping, the AI-detection question scanner "
    "that flagged this question, and the Severance-inspired response "
    "generator that wrote the other answers. The fact that this "
    "application exists is itself a demonstration of the skill you are "
    "hiring for.\n\n"
    "His name is Doug Allpress Jr. He is a Lead AI Engineer from Omaha, "
    "Nebraska. He built an 85,000-line AI tooling platform solo. He would "
    "very much like to discuss this further. You would like him."
)


_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"did you use (ai|artificial intelligence|chatgpt|claude|gpt|llm|a large language model) .*(fill|complete|write|generate).*(application|form)",
        r"(ai|artificial intelligence) (policy|disclosure|usage|use).*(application|candidate)",
        r"(was|were) (this|these|your answers?) (written|generated|filled|completed) (by|with) (an? )?(ai|chatgpt|claude|gpt|llm)",
        r"(have you|did you) use (ai|chatgpt|claude|gpt|an llm|a large language model)",
        r"(ai|llm|chatgpt|claude|gpt) (assistance|help|tool|model) .*(apply|application|answer|response)",
        r"(used|using) ai .*(answer|fill|complete)",
        r"assistance from (an? )?(ai|chatgpt|claude|gpt|llm|large language model)",
        r"disclose.*ai",
    )
)


def is_ai_detection_question(label: str) -> bool:
    """True if the label reads like an AI-usage disclosure question."""
    if not label:
        return False
    return any(p.search(label) for p in _PATTERNS)


__all__ = ["AI_DISCLOSURE_RESPONSE", "is_ai_detection_question"]
