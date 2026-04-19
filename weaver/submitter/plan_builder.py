"""Plan builder: Greenhouse question → proposed answer, plus on-disk plans.

Port of bulk-submitter/src/jobs/anthropic-preview.ts. The output shape is
unchanged (same JSON keys) so existing plans under
``contexts/anthropic/plans/anthropic-*.json`` round-trip cleanly.

Strategy labels (same values as the TypeScript version):

  precomputed           — answer came from the applicant profile
  select-yes / -no      — Yes / No on a multi_value_single_select
  select-decline        — Decline / Prefer-not-to-say on EEOC-style questions
  select-other          — "Other" on a how-did-you-hear select
  ai-disclosure         — AI-policy / AI-written question
  top-tier-voice        — company-specific severance response
  severance-voice       — generic severance response
  skipped-file-upload   — Playwright layer handles this
  unhandled             — no rule matched; surfaced for review
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from weaver.submitter.ai_detection import (
    AI_DISCLOSURE_RESPONSE,
    is_ai_detection_question,
)
from weaver.submitter.applicant import Applicant
from weaver.submitter.greenhouse import (
    GreenhouseField,
    GreenhouseJob,
    GreenhouseQuestion,
)
from weaver.submitter.voice import TOP_TIER_COMPANIES, Voice, should_use_voice


# ---------- output dataclasses ----------

@dataclass(slots=True)
class QuestionPlan:
    fieldName: str
    label: str
    required: bool
    fieldType: str
    proposedAnswer: str
    strategy: str
    description: str | None = None
    options: list[dict[str, Any]] | None = None
    optionValue: Any = None
    note: str | None = None


@dataclass(slots=True)
class JobPlan:
    company: str
    title: str
    url: str
    jobId: int
    location: str
    generatedAt: str
    approved: bool = False
    submitted: bool = False
    questionCount: int = 0
    answeredCount: int = 0
    unansweredLabels: list[str] = field(default_factory=list)
    questions: list[QuestionPlan] = field(default_factory=list)
    firstPublished: str | None = None
    updatedAt: str | None = None


# ---------- plan builder ----------

_CURATED_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"software engineer",
        r"research engineer",
        r"applied ai engineer",
        r"forward.?deployed",
        r"staff.*engineer",
        r"senior engineer",
        r"engineering manager.*(agent|prompt|eval|inference|claude|platform|sdk)",
        r"solutions architect",
        r"data scientist.*(tool|devex|ai)",
        r"ai tooling",
        r"claude code",
        r"agent (sdk|platform|infrastructure|prompts)",
    )
)


def matches_curated_title(title: str) -> bool:
    return any(p.search(title) for p in _CURATED_PATTERNS)


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return re.sub(r"^-+|-+$", "", s)[:60]


# Titles / question patterns that mark a role as DoD / Federal /
# Defense / Public-Sector. When any of these match, the plan builder
# augments clearance-history narrative with the applicant's
# ``dod_experience`` text (on-site programs, cleared-network specifics).
# For non-DoD roles the field is never read — civilian applications
# don't see the site names.
_DOD_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\bfederal\b",
        r"\bdod\b",
        r"\bdefense\b",
        r"\bcivilian\b",
        r"\bgovernment\b",
        r"\bpublic.?sector\b",
        r"\bnational security\b",
        r"\bintelligence\b",
    )
)


_YESNO_INTENT_RE = re.compile(
    r"^\s*(are|do|did|have|has|will|would|can|could|should|may|is|was|were)\s+you\b",
    re.I,
)


def _looks_like_yesno_intent(label: str) -> bool:
    """Heuristic: does this label read like a yes/no question?

    Matches free-text questions like "Are you fluent in Arabic?" where
    a narrative answer would be worse than an empty one. Does not match
    open-ended prompts ("Tell us about…", "Why are you interested in…").
    """
    return bool(_YESNO_INTENT_RE.search(label or ""))


def is_dod_role(title: str) -> bool:
    """Title-pattern check for DoD / Federal / Defense / Public-Sector roles."""
    return any(p.search(title or "") for p in _DOD_TITLE_PATTERNS)


class PlanBuilder:
    """Turn a Greenhouse job into a :class:`JobPlan`.

    One instance per run (the voice generator holds per-instance rotation
    state); construct a fresh one each time you regenerate.
    """

    def __init__(self, applicant: Applicant, *, company: str, voice: Voice | None = None,
                 dod_context: bool | None = None) -> None:
        self._app = applicant
        self._company = company
        self._voice = voice or Voice()
        self._top_tier = company in TOP_TIER_COMPANIES
        # dod_context is a per-job flag; when None the builder decides per
        # question via the job title passed to ``build``.
        self._dod_context_override = dod_context
        self._current_is_dod = False

    # -- main entry --

    def build(self, job: GreenhouseJob, questions: Iterable[GreenhouseQuestion]) -> JobPlan:
        qs = list(questions)
        # DoD-flag the whole job up front; per-question dispatch reads it.
        if self._dod_context_override is None:
            self._current_is_dod = is_dod_role(job.title)
        else:
            self._current_is_dod = bool(self._dod_context_override)
        plans = [self._plan_question(q) for q in qs]
        answered = [
            p for p in plans
            if p.proposedAnswer and p.strategy not in ("unhandled", "skipped-file-upload")
        ]
        return JobPlan(
            company=self._company,
            title=job.title,
            url=job.absolute_url,
            jobId=job.id,
            location=job.location.name or "—",
            firstPublished=job.first_published,
            updatedAt=job.updated_at,
            generatedAt=_dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
            questionCount=len(qs),
            answeredCount=len(answered),
            unansweredLabels=[p.label for p in plans if p.strategy == "unhandled"],
            questions=plans,
        )

    # -- per question --

    def _plan_question(self, q: GreenhouseQuestion) -> QuestionPlan:
        field = q.primary_field or GreenhouseField(name="", type="")
        label = q.label or ""
        description = _strip_html(q.description)

        base: dict[str, Any] = {
            "fieldName": field.name,
            "label": label,
            "description": description or None,
            "required": bool(q.required),
            "fieldType": field.type,
            "options": list(field.values) if field.values else None,
        }

        # File uploads are the Playwright submitter's job.
        if field.type == "input_file" or re.match(r"^resume", field.name, re.I) \
                or re.search(r"resume|cv|cover letter", label, re.I):
            return QuestionPlan(**base, proposedAnswer="[file upload — handled by submitter wayfinder]",
                                strategy="skipped-file-upload")

        # AI-detection disclosure.
        if is_ai_detection_question(label):
            if field.type == "multi_value_single_select" and field.values:
                yes = _pick_option(field.values, lambda v: any(w in v for w in ("yes", "agree", "confirm")))
                if yes:
                    return QuestionPlan(**base, proposedAnswer=str(yes["label"]),
                                        optionValue=yes["value"], strategy="ai-disclosure")
            return QuestionPlan(**base, proposedAnswer=AI_DISCLOSURE_RESPONSE, strategy="ai-disclosure")

        # Select-style questions — pick the right option.
        if field.type == "multi_value_single_select":
            sel = self._select_answer_for(field, label)
            if sel is not None:
                note = self._clearance_level_note(label)
                return QuestionPlan(**base, proposedAnswer=sel["answer"],
                                    optionValue=sel["value"], strategy=sel["strategy"],
                                    note=note)
            # Fallback: first option + unhandled note.
            if field.values:
                first = field.values[0]
                return QuestionPlan(**base, proposedAnswer=str(first["label"]),
                                    optionValue=first["value"], strategy="unhandled",
                                    note="select with no rule — defaulted to first option; "
                                          "review before submitting")

        # Boilerplate free-text (name, email, phone, start date, etc.).
        bp = self._boilerplate(field, label)
        if bp is not None:
            return QuestionPlan(**base, proposedAnswer=bp["answer"], strategy=bp["strategy"])

        # Conditional "If yes, please explain" sub-questions. These are
        # meant to be filled only when the parent yes/no answered "Yes".
        # Since we usually answer these parents "No" (not under a
        # conflicting agreement, not previously interviewed, etc.),
        # leaving the explanation blank is the correct behaviour. A
        # severance-voice narrative here is actively harmful: it looks
        # like the candidate is volunteering a conflict where none
        # exists.
        if re.search(
            r"^\s*if (yes|so)\b|please (provide |give )?(further |additional )?"
            r"(explanation|details|context).*below|explain (below|here|if so)",
            label, re.I,
        ):
            return QuestionPlan(**base, proposedAnswer="",
                                strategy="conditional-empty",
                                note="conditional explanation field — left blank; "
                                      "depends on parent yes/no answer")

        # Free-text questions with a yes/no intent. Greenhouse sometimes
        # surfaces these as ``input_text`` rather than ``multi_value_single_select``
        # (e.g. a simple text box asking "Are you open to relocation?"). Consult
        # the profile rather than falling through to narrative voice.
        yn = self._yesno_for_label(label)
        if yn is not None:
            return QuestionPlan(**base, proposedAnswer=yn,
                                strategy=f"yesno-text-{yn.lower()}")

        # If a question reads like a yes/no ("Are/Do/Have you …") but we have
        # no rule for it (e.g. "Are you fluent in Arabic?"), mark as unhandled.
        # Severance-voice on a yes/no question submits nonsense.
        if _looks_like_yesno_intent(label):
            return QuestionPlan(**base, proposedAnswer="", strategy="unhandled",
                                note="yes/no-style question with no matching profile rule; "
                                      "fill manually before submitting")

        # Narrative open-ended → voice.
        if should_use_voice(label):
            if self._top_tier:
                return QuestionPlan(**base,
                                    proposedAnswer=self._voice.top_tier_response(label, self._company),
                                    strategy="top-tier-voice")
            return QuestionPlan(**base,
                                proposedAnswer=self._voice.generate(label, company=self._company),
                                strategy="severance-voice")

        # Fallback generic.
        fallback = self._voice.generate(label, company=self._company)
        if fallback:
            return QuestionPlan(**base, proposedAnswer=fallback, strategy="severance-voice")

        return QuestionPlan(**base, proposedAnswer="", strategy="unhandled",
                            note="no rule matched — needs a pattern tweak or human answer")

    # -- boilerplate field dispatch --

    def _boilerplate(self, field: GreenhouseField, label: str) -> dict[str, str] | None:
        a = self._app
        name = (field.name or "").lower()
        L = label.lower()

        if name == "first_name":
            return {"answer": a.first_name, "strategy": "precomputed"}
        if name == "last_name":
            return {"answer": a.last_name, "strategy": "precomputed"}
        if name == "email":
            return {"answer": a.email, "strategy": "precomputed"}
        if name == "phone":
            return {"answer": a.phone, "strategy": "precomputed"}
        if name == "company" or L == "current company":
            return {"answer": "Lincoln Financial Group", "strategy": "precomputed"}

        if re.search(r"linkedin", label, re.I):
            return {"answer": a.linkedin, "strategy": "precomputed"}
        if re.search(r"\b(website|portfolio|personal url|personal site|github)\b", label, re.I):
            return {"answer": a.github or a.website, "strategy": "precomputed"}
        if re.match(r"^(address|current address|where do you live|home address)", label, re.I):
            return {"answer": a.address, "strategy": "precomputed"}
        if re.search(r"address.*(work|from which you plan)", label, re.I):
            return {"answer": a.address, "strategy": "precomputed"}
        if re.search(r"(what|which).*country|country.*(located|reside|live|based)|country of residence",
                     label, re.I):
            return {"answer": a.country, "strategy": "precomputed"}
        if re.search(r"(what|which).*(city|state)|city.*(located|reside|live|based)",
                     label, re.I):
            return {"answer": a.city, "strategy": "precomputed"}

        if re.search(r"years? of.*experience", label, re.I):
            return {"answer": a.years_experience, "strategy": "precomputed"}
        if re.search(r"salary|compensation|desired pay", label, re.I):
            return {"answer": a.salary, "strategy": "precomputed"}
        if re.search(r"earliest.*start|when.*start|start date", label, re.I):
            return {"answer": a.start_date, "strategy": "precomputed"}
        if re.search(r"notice period", label, re.I):
            return {"answer": a.notice_period, "strategy": "precomputed"}
        if re.search(r"deadline|timeline consideration", label, re.I):
            return {"answer": a.deadlines, "strategy": "precomputed"}
        if re.search(r"how did you (hear|find)|how did you learn|source", label, re.I):
            return {"answer": a.how_heard, "strategy": "precomputed"}
        if re.search(r"additional information|additional comments|anything else we should know", label, re.I):
            return {"answer": a.additional_info, "strategy": "precomputed"}
        if re.search(r"personal preferences", label, re.I):
            return {"answer": a.personal_preferences, "strategy": "precomputed"}
        if re.search(r"(core )?technical stack|tech(nology)? stack|core stack|"
                     r"primary (languages|stack|tools)|languages you (work|use)",
                     label, re.I) and a.technical_stack:
            return {"answer": a.technical_stack, "strategy": "precomputed"}

        if re.search(r"government.*agenc|federal.*agenc|which.*(agenc|department)|worked with.*(government|federal|dod|doj)", label, re.I):
            # For DoD / Federal roles, extend the clearance history with the
            # on-site / off-network chapter (CENTAF, PACAF, CENTCOM etc.).
            # For all other roles, only the base history is surfaced.
            if self._current_is_dod and a.dod_experience.strip():
                combined = a.clearance_history.rstrip() + "\n\n" + a.dod_experience.strip()
                return {"answer": combined, "strategy": "precomputed"}
            return {"answer": a.clearance_history, "strategy": "precomputed"}

        return None

    # -- select-field dispatch --

    def _select_answer_for(self, field: GreenhouseField, label: str) -> dict[str, Any] | None:
        values = field.values
        if not values:
            return None

        # Shared yes/no rule set (profile-driven).
        yn = self._yesno_for_label(label)
        if yn is not None:
            target = yn.lower()
            pick = _pick_option(values,
                                 lambda v: v == target or v.startswith(target))
            if pick:
                return {"answer": pick["label"], "value": pick["value"],
                        "strategy": f"select-{target}"}

        # Clearance level (distinct from active/inactive yes/no).
        if re.search(r"highest.*(level.*)?clearance|clearance level", label, re.I):
            ts = _pick_option(values, lambda v: "ts/sci" in v)
            if ts:
                return {"answer": ts["label"], "value": ts["value"], "strategy": "select-yes"}

        # Protected-class demographics → decline.
        if re.search(r"gender|race|ethnicity|veteran|disability|demographic|hispanic|latin",
                     label, re.I):
            dec = _pick_option(values, lambda v: (
                "decline" in v or "prefer not" in v or "don't wish" in v or "do not wish" in v))
            if dec:
                return {"answer": dec["label"], "value": dec["value"], "strategy": "select-decline"}

        # "How did you hear" → Other (we have a custom how_heard text answer).
        if re.search(r"how did you (hear|find)|source", label, re.I):
            other = _pick_option(values, lambda v: "other" in v)
            if other:
                return {"answer": other["label"], "value": other["value"], "strategy": "select-other"}

        # Generic "Are/Can/Will/Do/Have you ..." → Yes, if a yes option exists.
        # Only as a last resort — anything more specific should match above.
        yes = _pick_option(values, lambda v: v == "yes")
        if yes and re.match(r"^(are|can|will|do|have) you", label, re.I):
            return {"answer": yes["label"], "value": yes["value"], "strategy": "select-yes"}

        return None

    # -- yes/no dispatch (shared by select + free-text paths) --

    def _yesno_for_label(self, label: str) -> str | None:
        """Return "Yes" / "No" / None for a known yes/no label.

        Consults the applicant profile rather than hardcoding, so the
        same rule set stays honest when the profile changes. Used both
        when filling multi-select options and when filling input_text
        fields whose label reads like a yes/no prompt.
        """
        a = self._app
        if re.search(r"(authorized|eligible).*work|legally (authorized|able).*work",
                     label, re.I):
            return "Yes" if a.us_authorized else "No"
        if re.search(r"sponsor|visa", label, re.I):
            return "No" if not a.needs_sponsorship else "Yes"
        if re.search(r"relocation|relocate|open to.*(relocat|moving)", label, re.I):
            return "Yes" if a.open_to_relocation else "No"
        if re.search(
            r"open to (working in.?person|in.?person.*office)|in.?person.*office.*time|"
            r"office.*(\d+.*(time|percent)|in person)|in.person.*\d+",
            label, re.I,
        ):
            return "Yes" if a.open_to_office_25 else "No"
        if re.search(r"interviewed.*(before|previously)|previously interviewed|applied.*before",
                     label, re.I):
            return "No" if not a.interviewed_before else "Yes"
        if re.search(r"active.*(security )?clearance|currently hold.*clearance",
                     label, re.I):
            return "Yes" if a.clearance_active else "No"
        # Employment conflict / existing-obligation questions: default No.
        # Greenhouse forms pair these with an "If yes, please explain" field;
        # the conditional handler below leaves that explanation blank.
        if re.search(
            r"bound by.*(agreement|contract|non.?compete|obligation)|"
            r"(non.?compete|non.?disclosure|conflict).*agreement|"
            r"currently.*(bound|obligated)|"
            r"(have|do you have).*(non.?compete|ip agreement|conflicting)",
            label, re.I,
        ):
            return "No"
        return None

    def _clearance_level_note(self, label: str) -> str | None:
        if re.search(r"highest.*(level.*)?clearance|clearance level", label, re.I):
            return (
                "TS/SCI held 1999–2015 at Northrop Grumman, currently INACTIVE. "
                "Reinstate-able with a sponsor. Mention in narrative questions."
            )
        return None


# ---------- on-disk store ----------

class PlanStore:
    """Read/write job plans as JSON under a context's ``plans/`` dir."""

    def __init__(self, plans_dir: Path) -> None:
        self.dir = Path(plans_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, slug: str, *, prefix: str = "anthropic") -> Path:
        return self.dir / f"{prefix}-{slug}.json"

    def save(self, plan: JobPlan, *, prefix: str = "anthropic") -> Path:
        slug = slugify(plan.title)
        path = self.path_for(slug, prefix=prefix)
        path.write_text(_dump_json(plan), encoding="utf-8")
        return path

    def load(self, slug: str, *, prefix: str = "anthropic") -> JobPlan | None:
        path = self.path_for(slug, prefix=prefix)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if "questions" not in data:
            return None
        return _plan_from_dict(data)

    def list(self, *, prefix: str = "anthropic") -> list[tuple[str, JobPlan]]:
        out: list[tuple[str, JobPlan]] = []
        for p in sorted(self.dir.glob(f"{prefix}-*.json")):
            if p.name == f"{prefix}-index.json":
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if "questions" not in data:
                continue
            slug = p.name[len(f"{prefix}-"):-len(".json")]
            out.append((slug, _plan_from_dict(data)))
        return out

    def write_index(self, index: dict[str, Any], *, prefix: str = "anthropic") -> Path:
        path = self.dir / f"{prefix}-index.json"
        path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        return path

    def load_index(self, *, prefix: str = "anthropic") -> dict[str, Any] | None:
        path = self.dir / f"{prefix}-index.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


# ---------- helpers ----------

def _pick_option(values: tuple[dict[str, Any], ...] | list[dict[str, Any]],
                 match_label_lower: Any) -> dict[str, Any] | None:
    for v in values:
        label = str(v.get("label") or "").lower()
        if match_label_lower(label):
            return v
    return None


def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"&[a-z]+;", " ", re.sub(r"<[^>]+>", "", s))).strip()


def _dump_json(plan: JobPlan) -> str:
    d = asdict(plan)
    # asdict converts QuestionPlan instances too — perfect.
    return json.dumps(d, indent=2, ensure_ascii=False)


def _plan_from_dict(data: dict[str, Any]) -> JobPlan:
    questions = [QuestionPlan(**q) for q in data.get("questions", [])]
    kwargs = {k: v for k, v in data.items() if k != "questions"}
    return JobPlan(questions=questions, **kwargs)


__all__ = [
    "JobPlan",
    "PlanBuilder",
    "PlanStore",
    "QuestionPlan",
    "matches_curated_title",
    "slugify",
]
