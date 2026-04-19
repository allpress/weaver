"""Applicant profile loader.

The applicant profile is the human's side of the application — name,
contact, work-authorization status, salary expectations, paths to
resume/cover-letter files, clearance status, narrative responses for
common questions — stored as YAML at
``<context>/applicant/profile.yaml``.

The profile.yaml file is **gitignored** (see top-level .gitignore) and
must be supplied by the person running the tool. See
``profile.yaml.example`` in the repo root for the expected shape.

All defaults below are placeholders. Running ``weaver submit fetch``
without a real profile will produce placeholder answers — by design, so
a missing profile is visible rather than silently wrong.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields as dc_fields
from pathlib import Path
from typing import Any

try:
    from ruamel.yaml import YAML
    _yaml = YAML(typ="safe")
except ImportError:  # pragma: no cover
    import yaml as _pyyaml
    _yaml = None


@dataclass(slots=True)
class Applicant:
    # Identity
    first_name: str = "<first-name>"
    last_name: str = "<last-name>"
    full_name: str = "<full-name>"
    email: str = "<your-email@example.com>"
    phone: str = "<phone-number>"
    city: str = "<city, state>"
    state: str = ""
    country: str = "United States"
    address: str = ""

    # Online presence
    linkedin: str = ""
    website: str = ""
    github: str = ""

    # Work authorization + preferences
    us_authorized: bool = True
    needs_sponsorship: bool = False
    open_to_relocation: bool = True
    relocation_destinations: str = "Open to any location for the right role"
    open_to_office_25: bool = True

    # Experience + pay
    years_experience: str = ""
    salary: str = ""
    start_date: str = "2 weeks notice"
    notice_period: str = "2 weeks"

    # Clearance (narrative answers for roles that ask)
    clearance_level: str = ""
    clearance_active: bool = False
    clearance_history: str = ""

    # DoD / Federal-specific narrative — only populated for roles flagged
    # as DoD/Federal/Defense/Public-Sector. Left blank otherwise.
    dod_experience: str = ""

    # EEOC self-identification. Left blank by default → the plan-builder
    # picks a "Decline to self-identify" option where one exists. Fill
    # any of these in profile.yaml to have the builder answer truthfully.
    gender: str = ""             # e.g. "Male", "Female", "Non-binary"
    race: str = ""               # e.g. "White", "Asian", "Black or African American"
    hispanic_or_latino: str = "" # "Yes" / "No" (Hispanic/Latino is a separate question from race)
    veteran_status: str = ""     # "I am not a veteran" / "I am a protected veteran" etc.
    disability_status: str = ""  # left blank by default — most sensitive

    # Boilerplate free-text
    how_heard: str = ""
    interviewed_before: bool = False
    additional_info: str = ""
    personal_preferences: str = ""
    deadlines: str = "No hard deadlines; flexible for the right role."
    # Short technical-stack summary for "What's your core stack?" questions.
    # Kept terse on purpose — the long version lives in the résumé.
    technical_stack: str = ""

    # File paths (resolved against the context's applicant/ dir)
    resume_md: str = "resume.md"
    cover_letter_md: str = "cover-letter.md"
    resume_pdf: str = ""
    cover_letter_pdf: str = ""

    def resolve_path(self, base_dir: Path, key: str) -> Path:
        """Resolve a filename field (``resume_pdf`` etc.) against ``base_dir``."""
        fname = getattr(self, key, "")
        if not fname:
            return base_dir / ""
        return (base_dir / fname).resolve()

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in dc_fields(self)}


def load_applicant(applicant_dir: Path | str) -> Applicant:
    """Load applicant profile from ``<applicant_dir>/profile.yaml``.

    Missing file → returns a placeholder instance. Unknown YAML keys are
    ignored so adding fields stays backwards-compatible.
    """
    path = Path(applicant_dir) / "profile.yaml"
    if not path.exists():
        return Applicant()
    raw = path.read_text(encoding="utf-8")
    data = _parse_yaml(raw)
    if not isinstance(data, dict):
        return Applicant()
    valid = {f.name for f in dc_fields(Applicant)}
    kwargs = {k: v for k, v in data.items() if k in valid}
    return Applicant(**kwargs)


def _parse_yaml(text: str) -> Any:
    if _yaml is not None:
        return _yaml.load(text)
    return _pyyaml.safe_load(text)


__all__ = ["Applicant", "load_applicant"]
