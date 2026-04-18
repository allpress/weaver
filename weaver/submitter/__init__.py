"""Submitter — the weaver half of the "apply via wayfinder" pipeline.

The surface this module exposes to the rest of weaver:

- ``Applicant`` — loader + dataclass for the person's profile (from
  ``contexts/<ctx>/applicant/profile.yaml`` + ``resume.md``).
- ``Voice`` — the severance-style voice, top-tier per-company branches,
  generic fallback. Port of ``bulk-submitter/src/jobs/severance-voice.ts``.
- ``AIDisclosure`` — the honest-AI response + pattern matcher for
  AI-detection questions.
- ``GreenhouseClient`` — board listing + per-job question details.
- ``PlanBuilder`` — turns a Greenhouse job into a per-question plan using
  Voice + AIDisclosure + applicant precomputes.
- ``PlanStore`` — read/write per-job plan JSON under
  ``contexts/<ctx>/plans/``.

The actual Playwright submission lives in wayfinder's
``greenhouse_submitter`` walker — weaver hands a validated plan to it and
streams events back. Secrets for the submitter (cookies, SSO, etc.) are
resolved through warden as usual.
"""
from weaver.submitter.applicant import Applicant, load_applicant
from weaver.submitter.ai_detection import AI_DISCLOSURE_RESPONSE, is_ai_detection_question
from weaver.submitter.greenhouse import GreenhouseClient, GreenhouseJob, GreenhouseQuestion
from weaver.submitter.plan_builder import (
    JobPlan,
    PlanBuilder,
    PlanStore,
    QuestionPlan,
)
from weaver.submitter.voice import Voice

__all__ = [
    "AI_DISCLOSURE_RESPONSE",
    "Applicant",
    "GreenhouseClient",
    "GreenhouseJob",
    "GreenhouseQuestion",
    "JobPlan",
    "PlanBuilder",
    "PlanStore",
    "QuestionPlan",
    "Voice",
    "is_ai_detection_question",
    "load_applicant",
]
