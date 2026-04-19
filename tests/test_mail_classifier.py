"""Unit tests for the rule-based mail classifier.

Tight coverage on the categories we actually want to act on —
``ack`` / ``rejection`` / ``interview`` — plus regressions for common
false-positive traps (rejections disguised as "thanks for applying",
recruiter job-alert noise in an applicant's inbox).
"""
from __future__ import annotations

from weaver.submitter.mail_classifier import Classification, classify


def _msg(**kw) -> dict:
    base = {"from": "", "subject": "", "text_body": "", "date": "2026-04-19"}
    base.update(kw)
    return base


# ---- ack ----

def test_ack_application_received():
    c = classify(_msg(
        from_="noreply@greenhouse.io",
        subject="Application received — Forward Deployed Engineer",
    ))
    # from_ is a reserved kwarg issue above; rebuild cleanly
    c = classify(_msg(**{"from": "noreply@greenhouse.io",
                          "subject": "Application received — Forward Deployed Engineer"}))
    assert c.category == "ack"
    assert c.confidence == "high"


def test_ack_thanks_for_applying_subject():
    c = classify(_msg(
        subject="Thanks for applying to Anthropic",
        text_body="We received your application.",
    ))
    c = classify({"from": "", "subject": "Thanks for applying to Anthropic",
                   "text_body": "We received your application.", "date": ""})
    assert c.category == "ack"


def test_ack_ats_noreply_with_application_subject():
    c = classify({
        "from": "no-reply@mail.greenhouse.io",
        "subject": "Your application to Scale AI",
        "text_body": "We have received your application.",
        "date": "",
    })
    assert c.category == "ack"


# ---- rejection ----

def test_rejection_unfortunately_body():
    c = classify({
        "from": "recruiting@example.com",
        "subject": "Update on your application",
        "text_body": (
            "Hi Doug,\n\nThank you for applying. Unfortunately, we have "
            "decided not to move forward with your application at this time."
        ),
        "date": "",
    })
    assert c.category == "rejection"
    assert c.confidence == "high"


def test_rejection_pursue_other_candidates():
    c = classify({
        "from": "talent@example.com",
        "subject": "Re: your application",
        "text_body": "We've decided to pursue other candidates.",
        "date": "",
    })
    assert c.category == "rejection"


def test_rejection_beats_ack_when_both_signals_present():
    """Rejections often open with "Thanks for applying" then pivot."""
    c = classify({
        "from": "recruiting@example.com",
        "subject": "Thanks for applying",
        "text_body": (
            "Thanks for your interest. Unfortunately, we won't be "
            "moving forward at this time."
        ),
        "date": "",
    })
    assert c.category == "rejection"


# ---- interview ----

def test_interview_subject_match():
    c = classify({
        "from": "recruiter@example.com",
        "subject": "Interview with Anthropic — please schedule",
        "text_body": "Please pick a time on this link.",
        "date": "",
    })
    assert c.category == "interview"
    assert c.confidence == "high"


def test_interview_phone_screen():
    c = classify({"from": "r@x.com", "subject": "Phone screen",
                   "text_body": "Are you free Tuesday?", "date": ""})
    assert c.category == "interview"


def test_interview_body_scheduling():
    c = classify({
        "from": "recruiter@example.com",
        "subject": "Re: next steps",
        "text_body": "I'd love to schedule a call this week.",
        "date": "",
    })
    assert c.category == "interview"


# ---- followup ----

def test_followup_recruiter_asks_for_availability():
    c = classify({
        "from": "real.human@example.com",
        "subject": "Quick question",
        "text_body": "Could you share your availability for next week?",
        "date": "",
    })
    assert c.category == "followup"


# ---- auto ----

def test_auto_from_noreply():
    c = classify({
        "from": "newsletter@linkedin.com",
        "subject": "This week at LinkedIn",
        "text_body": "...",
        "date": "",
    })
    assert c.category == "auto"


def test_auto_job_alert_subject():
    c = classify({
        "from": "alerts@example.com",
        "subject": "5 new jobs for you this week",
        "text_body": "...",
        "date": "",
    })
    assert c.category == "auto"


# ---- unknown fallback ----

def test_unknown_when_nothing_matches():
    c = classify({
        "from": "friend@example.com",
        "subject": "hey",
        "text_body": "want to grab coffee",
        "date": "",
    })
    assert c.category == "unknown"
    assert c.confidence == "low"


# ---- Classification helpers ----

def test_classification_as_dict_shape():
    c = Classification("ack", "high", "x")
    d = c.as_dict()
    assert set(d.keys()) == {"category", "confidence", "signal"}
    assert d["category"] == "ack"
