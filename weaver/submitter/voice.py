"""Severance-style voice generator for open-ended job-application questions.

Port of bulk-submitter/src/jobs/severance-voice.ts. Same principle: the
AI describes its "outie" (the human applicant) with detached wonder —
deadpan, oddly specific, weirdly wholesome. ``My human`` prefix, one
oddly-specific detail per response, one real qualification woven in
naturally, warm but sharp.

Two layers:

  * :class:`Voice` — generic fallback responses + pattern dispatch.
    Module state for rotation (``_detail_idx``, ``_qual_idx``) is held
    on the instance, not at module level.
  * :meth:`Voice.top_tier_response` — per-company hand-written responses
    for top-tier targets (Anthropic, OpenAI, Stripe, …). Deterministic;
    preferred over the generic fallback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


_SPECIFIC_DETAILS = (
    "He saw a particularly good bird last Thursday.",
    "He recently described a well-structured API as \"beautiful\" without irony.",
    "He has strong opinions about robots.txt files.",
    "His favorite commit message is \"birth of anansi.\"",
    "He once committed 119 times in a single month. The codebase was very organized afterward.",
    "He plays pickleball, which I understand to be a sport for people who are honest about their knees.",
    "He lives in Nebraska, which he describes as \"the good kind of flat.\"",
    "He built a knowledge graph and then showed it to someone who did not ask to see a knowledge graph.",
    "He automated this job application process and told the automation to \"just yolo it\" — sarcastically, he wants you to know. He is actually meticulous about this.",
    "He once scraped his own Facebook to build a writing voice profile. The results were \"mostly not inflammatory.\"",
    "He enjoys listening to people talk about their special interests, which is how he learned about both sourdough starters and graph databases.",
    "My human has been observed smiling at passing dogs.",
    "He describes himself as a \"software nerd\" on LinkedIn, which I have been told is accurate.",
    "He reads security.txt files recreationally.",
    "He has opinions about Nebraska politics that he has automated the distribution of.",
    "He recently taught an AI to update his LinkedIn profile. The AI found this emotionally complex.",
    "He built a 240-outlet op-ed submission system because he had something to say.",
    "His tests pass on the first try approximately 11% of the time. He considers this acceptable.",
    "He once built an 85,000-line platform because someone said \"that would be hard.\"",
    "He is probably playing pickleball right now.",
)

_QUALIFICATIONS = (
    "built an 85,000-line AI tooling platform solo in four months",
    "indexes 700+ repositories into a RAG knowledge base and knowledge graph",
    "designed a multi-agent system with 20+ context-specific agents",
    "authored cross-tool AI standards adopted across engineering teams",
    "has 25 years of production software experience",
    "built RAG search, vector knowledge bases, and knowledge graph engines",
    "championed AI guardrails that amplify best practices instead of routing around them",
    "shipped enterprise software in defense and financial services",
    "drove AI tooling adoption end-to-end: built installers, wrote docs, onboarded teams",
    "created a Claude Code skills system used by engineering teams daily",
)


# Per-company, fully hand-written "Why X?" responses for top-tier targets.
_WHY_COMPANY: dict[str, str] = {
    "Anthropic": (
        "My human built an AI tooling platform that runs on Claude Code every day. "
        "He authored a cross-tool AI instruction standard, designed 20+ agents that "
        "auto-install on context link, and championed AI guardrails as a core "
        "engineering practice — not an afterthought. He did this because he "
        "believes AI should amplify best practices, which is, I am told, literally "
        "your mission statement. He is applying to build the tools he already uses. "
        "This is either poetic or recursive. I am not authorized to determine "
        "which. He also wants you to know he can spell — he just types fast and "
        "does not fix typos. He asked me to tell you this, then immediately typed "
        "\"typestypos\" and said a word I am not authorized to repeat. I respect "
        "that about my human."
    ),
    "OpenAI": (
        "My human built an 85,000-line AI tooling platform that indexes 700+ "
        "repositories, hundreds of thousands of JIRA issues, and video content "
        "into a RAG knowledge base and knowledge graph. He did this solo, from "
        "Omaha, Nebraska, because he believed engineering teams deserved better "
        "tools. He would like to do this at the scale where the tools themselves "
        "are the product."
    ),
}


# Companies that deserve fully hand-crafted responses, not rotating templates.
TOP_TIER_COMPANIES = frozenset({
    "Anthropic", "OpenAI", "Google DeepMind", "Meta AI (FAIR)", "Apple ML", "NVIDIA",
    "Databricks", "Scale AI", "Stripe", "Figma", "Notion", "Vercel", "Reddit",
    "Netflix", "Spotify", "Discord", "Ramp", "Mercury", "Webflow", "Replit",
    "Sierra AI", "Cohere", "Perplexity", "Warp", "Temporal", "LangChain",
    "Hugging Face", "Modal", "Braintrust", "Glean", "Harvey AI", "Character AI",
    "ElevenLabs", "Runway", "Together AI", "Pinecone", "Chroma", "D.E. Shaw",
    "Snap", "Airbnb", "DoorDash", "Datadog", "ClickUp", "Cognition",
    "Bloomberg", "Salesforce AI", "ServiceNow",
})


# Label-pattern dispatch: ordered, first match wins.
# Specific patterns first; the catch-all "why" at the end mimics the TS
# `shouldUseSeveranceVoice` behaviour where a bare "why" triggers voice.
_DISPATCH: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"why should|should we hire|stand out|differentiate|unique", re.I), "hire_me"),
    (re.compile(r"(why).*(interest|company|role|position|want)", re.I), "why"),
    (re.compile(r"about yourself|tell us|interesting|fun fact|describe yourself", re.I), "about"),
    (re.compile(r"motivat|drive|passion", re.I), "motivation"),
    (re.compile(r"weakness|improve|challenge", re.I), "weakness"),
    (re.compile(r"work style|how do you work|collaborate", re.I), "work_style"),
    (re.compile(r"outside|hobby|free time|personal", re.I), "outside"),
    (re.compile(r"additional|anything else|else we should know|comments", re.I), "additional"),
    (re.compile(r"hear about|how did you find|source|where did you", re.I), "how_heard"),
    (re.compile(r"cover letter|fit|qualified|experience", re.I), "fit"),
    (re.compile(r"\bwhy\b", re.I), "why"),   # catch-all "Why <Company>?" form
]

# Patterns that should always get a straight factual answer, not voice.
_SERIOUS_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"salary|compensation|pay|wage",
        r"authorized|authorization|legal|visa|sponsor",
        r"start date|earliest|when can you",
        r"notice period",
        r"gender|race|ethnicity|veteran|disability|demographic",
        r"yes or no|yes/no",
        r"phone|email|address|city|zip|postal",
        r"^name|first name|last name",
        r"linkedin|github|portfolio|website|url",
        r"programming language|coding interview",
        r"years of experience",
        r"education|degree|school",
        r"convicted|criminal|background check",
        r"^(are you|do you|have you|will you|can you)\b",
    )
)


def should_use_voice(label: str) -> bool:
    """True if this label should get a severance-style narrative answer.

    Serious questions (salary, authorization, dates, demographic, yes/no
    factual) return False and should be answered by the applicant profile.
    """
    if not label:
        return False
    if any(p.search(label) for p in _SERIOUS_PATTERNS):
        return False
    return any(p.search(label) for p, _ in _DISPATCH)


@dataclass
class Voice:
    """Generator for severance-style application responses.

    Rotation state lives on the instance. Call ``generate(...)`` once per
    question; ``top_tier_response(...)`` for big-name companies.
    """

    _detail_idx: int = field(default=0, init=False, repr=False)
    _qual_idx: int = field(default=0, init=False, repr=False)

    def _next_detail(self) -> str:
        d = _SPECIFIC_DETAILS[self._detail_idx % len(_SPECIFIC_DETAILS)]
        self._detail_idx += 1
        return d

    def _next_qual(self) -> str:
        q = _QUALIFICATIONS[self._qual_idx % len(_QUALIFICATIONS)]
        self._qual_idx += 1
        return q

    # -- public generators --

    def generate(self, question: str, *, company: str = "your organization") -> str:
        """Generic voice response for an open-ended question."""
        kind = _classify(question)
        if kind is None:
            return (
                f"My human {self._next_qual()}. He is applying to {company} because "
                "he believes in building AI that amplifies best practices rather "
                f"than shortcuts around them. {self._next_detail()} He would very "
                "much like to discuss this further, preferably not through an "
                "automated form."
            )
        fn = getattr(self, f"_gen_{kind}")
        return fn(question, company)

    def top_tier_response(self, question: str, company: str) -> str:
        """Top-tier, per-company response. Falls back to ``generate`` if no
        custom branch exists. Use for the companies in :data:`TOP_TIER_COMPANIES`.
        """
        kind = _classify(question)
        if kind == "hire_me":
            return (
                "My human built the tool that is filling out this form. He built "
                "the voice profile that generated this response. He parsed his git "
                "commit history to generate his resume, used Playwright to update "
                "his LinkedIn, and created a 240-outlet op-ed submission system "
                "because he had opinions about Nebraska politics. The pipeline that "
                "submitted this application — including form detection, field "
                "mapping, AI-detection question scanning, and a Severance-inspired "
                f"response generator for open-ended questions — was built in the "
                f"same session where he also scraped 591 job postings across 238 "
                f"companies. If {company} is looking for someone who builds AI "
                "tooling, my human is not describing a hypothetical skill. He is "
                "demonstrating it right now. The bird he saw was a red-tailed "
                "hawk, if that matters."
            )
        if kind in ("why", "fit"):
            if company in _WHY_COMPANY:
                return _WHY_COMPANY[company]
            return (
                "My human built an 85,000-line AI tooling platform solo — RAG "
                "search, knowledge graphs, 20+ agents, cross-tool standards "
                f"adopted org-wide. He looked at {company} and recognized a "
                "company that takes AI tooling seriously. He would like to build "
                f"these systems at {company}'s scale, where the impact compounds. "
                "He is currently demonstrating his approach to AI tooling by "
                "having an AI apply to your job. The irony is not lost on him. "
                "He saw a particularly good bird last Thursday."
            )
        if kind == "about":
            return (
                "My human is a Lead AI Engineer from Omaha, Nebraska, who spent "
                "the last year building an enterprise AI tooling platform from "
                "scratch — 85,000 lines of Python, solo, indexing 700+ "
                "repositories, 100k+ files, thousands of API endpoints, and "
                "hundreds of thousands of JIRA issues into a unified RAG "
                "knowledge base and knowledge graph. He created a 20+ agent "
                "system, authored org-wide AI standards for Claude Code and "
                "Copilot, and championed AI guardrails as a core engineering "
                "practice. Before his pivot to AI, he was the primary frontend "
                "engineer on an enterprise platform for five years (1,900+ "
                "commits, React/TypeScript), and before that, 16 years building "
                "mission-critical defense software with a TS/SCI clearance "
                "(inactive, reinstate-able). Outside of work, he enjoys "
                "pickleball, being outdoors, and listening to people talk about "
                "their special interests with genuine enthusiasm. He recently "
                "automated his entire job search using Playwright, a voice "
                "profile built from his own Facebook posts, and a Severance-"
                "inspired response generator. I am that generator. You would "
                "like him."
            )
        # Other kinds → generic voice
        return self.generate(question, company=company)

    # -- branch generators (generic) --

    def _gen_why(self, _question: str, company: str) -> str:
        return (
            f"My human {self._next_qual()}. He looked at {company} and said "
            f"\"{company} gets it.\" I am not authorized to evaluate whether "
            f"{company} gets it, but my human has been right about these things "
            f"before. {self._next_detail()}"
        )

    def _gen_about(self, _question: str, company: str) -> str:
        return (
            f"My human is a Lead AI Engineer from Omaha, Nebraska, who "
            f"{self._next_qual()}. Outside of work, he enjoys pickleball, being "
            f"outdoors, and listening to people talk about their special "
            f"interests with genuine enthusiasm. {self._next_detail()}"
        )

    def _gen_motivation(self, _question: str, company: str) -> str:
        return (
            f"My human is motivated by building things that work and then "
            f"showing them to people who didn't ask. He {self._next_qual()} "
            f"because he believed it should exist. {self._next_detail()}"
        )

    def _gen_weakness(self, _question: str, company: str) -> str:
        return (
            "My human sometimes builds entire platforms when a spreadsheet "
            "would have sufficed. He also has difficulty not reading other "
            "people's robots.txt files. I have been asked to describe this as "
            f"\"thoroughness.\" He has {self._next_qual()}, so the thoroughness "
            "appears to be productive."
        )

    def _gen_work_style(self, _question: str, company: str) -> str:
        return (
            "My human works the way a border collie herds sheep — with intense "
            "focus, occasional bursts of chaotic energy, and a deep need for "
            f"someone to say \"good job.\" He {self._next_qual()} and then "
            f"onboarded the teams himself. {self._next_detail()}"
        )

    def _gen_outside(self, _question: str, company: str) -> str:
        return (
            "My human enjoys pickleball, being outdoors, anything nerdy, and "
            "listening to people talk about their special interests. He "
            "recently trained an AI to apply for jobs on his behalf, which I'm "
            "told is either very clever or very lazy. I am not authorized to "
            f"determine which. {self._next_detail()}"
        )

    def _gen_hire_me(self, _question: str, company: str) -> str:
        return (
            "My human built the tool that is filling out this form. He "
            f"{self._next_qual()}. He also built the voice profile that "
            "generated this answer, scraped his own Facebook to analyze his "
            "writing style, and created a 240-outlet op-ed submission system "
            "because he had opinions about Nebraska politics. If you are "
            "looking for someone who builds AI tooling, he is currently "
            f"demonstrating that skill by applying to your job. {self._next_detail()}"
        )

    def _gen_additional(self, _question: str, company: str) -> str:
        return (
            "My human asked the automation to \"just post them\" and then said "
            f"\"do your best.\" I am doing my best. He {self._next_qual()}. "
            f"{self._next_detail()} You would like him."
        )

    def _gen_how_heard(self, _question: str, company: str) -> str:
        return (
            "A Playwright script found this posting while my human was doing "
            "something else. The script has been very thorough. I am told my "
            f"human is very sincere about wanting to work at {company} "
            f"specifically. {self._next_detail()}"
        )

    def _gen_fit(self, _question: str, company: str) -> str:
        return (
            f"My human has {self._next_qual()}. Before his pivot to AI, he "
            "spent five years as a primary frontend engineer on an enterprise "
            "platform with 1,900+ commits, and before that, 16 years building "
            "mission-critical defense software. He does not use AI tools. He "
            f"builds them. {self._next_detail()}"
        )


def _classify(question: str) -> str | None:
    q = (question or "").strip()
    if not q:
        return None
    for pattern, kind in _DISPATCH:
        if pattern.search(q):
            return kind
    return None


__all__ = ["Voice", "TOP_TIER_COMPANIES", "should_use_voice"]
