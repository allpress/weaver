"""Plan-builder regression tests.

Covers the yes/no answer logic for both select fields and free-text
fields, the country/city boilerplate, and the "yes/no intent with no
rule" → unhandled fallback. These were all gaps found when running
``weaver submit fetch --context scale-ai`` against the Scale AI board
and seeing the severance-voice narrative land on questions like "Are
you fluent in Arabic?".
"""
from __future__ import annotations

from weaver.submitter.applicant import Applicant
from weaver.submitter.greenhouse import (
    GreenhouseField,
    GreenhouseJob,
    GreenhouseLocation,
    GreenhouseQuestion,
)
from weaver.submitter.plan_builder import (
    PlanBuilder,
    _looks_like_yesno_intent,
)
from weaver.submitter.voice import Voice


def _applicant(**overrides) -> Applicant:
    base = dict(
        first_name="Doug", last_name="Allpress Jr",
        email="allpress@example.com", phone="402-555-0100",
        city="Omaha, NE", state="NE", country="United States",
        address="Omaha, NE",
        linkedin="https://linkedin.com/in/x", website="", github="",
        us_authorized=True, needs_sponsorship=False,
        open_to_relocation=True, open_to_office_25=True,
        interviewed_before=False, clearance_active=False,
        gender="", race="", hispanic_or_latino="",
        veteran_status="", disability_status="",
    )
    base.update(overrides)
    return Applicant(**base)


def _q(label: str, ftype: str = "input_text",
       options: list[str] | None = None) -> GreenhouseQuestion:
    values = None
    if options is not None:
        values = [{"label": o, "value": i} for i, o in enumerate(options, 1)]
    f = GreenhouseField(name="", type=ftype,
                        values=tuple(values) if values else ())
    return GreenhouseQuestion(label=label, description="",
                               required=False, fields=(f,))


def _job() -> GreenhouseJob:
    return GreenhouseJob(id=1, title="Test Role",
                         url="https://example.test/jobs/1",
                         location=GreenhouseLocation(name="Anywhere"),
                         first_published="",
                         updated_at="", departments=(), offices=())


def _plan(app: Applicant, q: GreenhouseQuestion, *, company: str = "Test Co"):
    b = PlanBuilder(app, company=company, voice=Voice())
    # _plan_question is the method under test; use the private access path
    # the module itself uses.
    return b._plan_question(q)   # noqa: SLF001


# --- _looks_like_yesno_intent ---

def test_yesno_intent_detects_are_you():
    assert _looks_like_yesno_intent("Are you fluent in Arabic?")
    assert _looks_like_yesno_intent("Are you currently employed?")


def test_yesno_intent_detects_auxiliary_verbs():
    for lead in ("Do", "Did", "Have", "Has", "Will", "Would", "Can",
                 "Could", "Should", "May", "Is", "Was", "Were"):
        assert _looks_like_yesno_intent(f"{lead} you have experience?"), lead


def test_yesno_intent_ignores_open_ended():
    assert not _looks_like_yesno_intent("Tell us about a time you shipped")
    assert not _looks_like_yesno_intent("Why are you interested in this role?")
    assert not _looks_like_yesno_intent("Describe your approach")
    assert not _looks_like_yesno_intent("What is your favourite editor?")


# --- free-text yes/no driven by profile ---

def test_free_text_relocation_uses_profile_yes():
    app = _applicant(open_to_relocation=True)
    plan = _plan(app, _q("Are you open to relocation to the Middle East?"))
    assert plan.proposedAnswer == "Yes"
    assert plan.strategy == "yesno-text-yes"


def test_free_text_relocation_uses_profile_no():
    app = _applicant(open_to_relocation=False)
    plan = _plan(app, _q("Are you open to relocation to the UK?"))
    assert plan.proposedAnswer == "No"
    assert plan.strategy == "yesno-text-no"


def test_free_text_visa_uses_profile():
    plan = _plan(_applicant(needs_sponsorship=False),
                 _q("Do you require visa sponsorship?"))
    assert plan.proposedAnswer == "No"
    assert plan.strategy == "yesno-text-no"


def test_free_text_work_authorization_uses_profile():
    plan = _plan(_applicant(us_authorized=True),
                 _q("Are you legally authorized to work in the US?"))
    assert plan.proposedAnswer == "Yes"
    assert plan.strategy == "yesno-text-yes"


def test_free_text_interviewed_before_uses_profile():
    plan = _plan(_applicant(interviewed_before=False),
                 _q("Have you interviewed with us before?"))
    assert plan.proposedAnswer == "No"
    assert plan.strategy == "yesno-text-no"


# --- unknown yes/no → unhandled, NOT severance-voice ---

def test_unknown_yesno_is_unhandled_not_voice():
    """Reading from a Scale AI plan that tried 'severance-voice' on
    'Are you fluent in Arabic?'. The right answer is to surface the
    question for manual review, not to write a story about pickleball."""
    plan = _plan(_applicant(), _q("Are you fluent or proficient in Arabic?"))
    assert plan.strategy == "unhandled"
    assert plan.proposedAnswer == ""
    assert plan.note and "yes/no" in plan.note.lower()


# --- country / city boilerplate ---

def test_country_factual_is_precomputed():
    plan = _plan(_applicant(country="United States"),
                 _q("What country are you located in?"))
    assert plan.strategy == "precomputed"
    assert plan.proposedAnswer == "United States"


def test_city_factual_is_precomputed():
    plan = _plan(_applicant(city="Omaha, NE"),
                 _q("What city are you based in?"))
    assert plan.strategy == "precomputed"
    assert plan.proposedAnswer == "Omaha, NE"


# --- select-path still works and uses the shared rule ---

def test_select_relocation_uses_profile_yes():
    plan = _plan(
        _applicant(open_to_relocation=True),
        _q("Are you open to relocation?",
           ftype="multi_value_single_select", options=["Yes", "No"]),
    )
    assert plan.proposedAnswer == "Yes"
    assert plan.strategy == "select-yes"


def test_select_visa_uses_profile_no():
    plan = _plan(
        _applicant(needs_sponsorship=False),
        _q("Do you require visa sponsorship?",
           ftype="multi_value_single_select", options=["Yes", "No"]),
    )
    assert plan.proposedAnswer == "No"
    assert plan.strategy == "select-no"


# --- employment conflict / non-compete ---

def test_bound_by_agreements_defaults_no():
    """Scale AI asks: 'Are you currently bound by any agreements with
    a current or former employer?' The safe/accurate default for most
    candidates is No. A generic 'Are you ...' fallback was previously
    answering Yes, which is actively wrong."""
    plan = _plan(_applicant(),
                 _q("Are you currently bound by any agreements with a "
                    "current or former employer?"))
    assert plan.proposedAnswer == "No"
    assert plan.strategy == "yesno-text-no"


def test_noncompete_defaults_no():
    plan = _plan(_applicant(),
                 _q("Do you have a non-compete with your current employer?"))
    assert plan.proposedAnswer == "No"


# --- conditional "if yes, please explain" ---

def test_conditional_if_yes_left_blank():
    """Fields like 'If yes, please provide further explanation below'
    should never get a severance-voice narrative — they're meant to be
    filled only if the parent yes/no answered Yes. Left blank is
    correct when the parent (usually) answers No."""
    plan = _plan(_applicant(),
                 _q("If yes, please provide further explanation below."))
    assert plan.proposedAnswer == ""
    assert plan.strategy == "conditional-empty"
    assert plan.note and "conditional" in plan.note.lower()


def test_conditional_please_explain_left_blank():
    plan = _plan(_applicant(),
                 _q("Please explain below if so."))
    assert plan.proposedAnswer == ""
    assert plan.strategy == "conditional-empty"


# --- EEOC self-identification ---

def test_gender_uses_profile_when_disclosed():
    plan = _plan(
        _applicant(gender="Male"),
        _q("Gender", ftype="multi_value_single_select",
           options=["Male", "Female", "Decline to self-identify"]),
    )
    assert plan.strategy == "select-self-id-gender"
    assert plan.proposedAnswer == "Male"


def test_race_uses_profile_when_disclosed():
    plan = _plan(
        _applicant(race="White"),
        _q("What is your race?", ftype="multi_value_single_select",
           options=["White", "Black or African American", "Asian",
                    "Decline to self-identify"]),
    )
    assert plan.strategy == "select-self-id-race"
    assert plan.proposedAnswer == "White"


def test_veteran_status_uses_profile_when_disclosed():
    plan = _plan(
        _applicant(veteran_status="I am not a protected veteran"),
        _q("Are you a protected veteran?",
           ftype="multi_value_single_select",
           options=["I am a protected veteran", "I am not a protected veteran",
                    "I don't wish to answer"]),
    )
    assert plan.strategy == "select-self-id-veteran"
    assert plan.proposedAnswer == "I am not a protected veteran"


def test_hispanic_latino_uses_profile_when_disclosed():
    plan = _plan(
        _applicant(hispanic_or_latino="No"),
        _q("Are you Hispanic or Latino?",
           ftype="multi_value_single_select",
           options=["Yes", "No", "Decline to self-identify"]),
    )
    assert plan.strategy == "select-self-id-ethnicity"
    assert plan.proposedAnswer == "No"


def test_demographics_decline_when_profile_blank():
    """Profile fields empty → fall back to Decline where possible."""
    plan = _plan(
        _applicant(),   # all EEOC fields blank
        _q("Gender", ftype="multi_value_single_select",
           options=["Male", "Female", "Decline to self-identify"]),
    )
    assert plan.strategy == "select-decline"
    assert "decline" in plan.proposedAnswer.lower()


def test_disability_still_declines_by_default():
    """disability_status is blank by default — always declines."""
    plan = _plan(
        _applicant(),
        _q("Do you have a disability?",
           ftype="multi_value_single_select",
           options=["Yes, I have a disability",
                    "No, I do not have a disability",
                    "I don't wish to answer"]),
    )
    assert plan.strategy == "select-decline"


# --- narrative questions still go to voice ---

def test_narrative_question_still_voice():
    """'Why are you interested in X' is an open-ended prompt; we want
    the severance-voice path, not the new yes/no-unhandled path."""
    plan = _plan(_applicant(),
                 _q("Why are you interested in this role?"),
                 company="Scale AI")
    assert plan.strategy in ("severance-voice", "top-tier-voice")
    assert plan.proposedAnswer   # non-empty narrative
