"""Rule-based classifier for recruiter email.

Pure Python, no IO. Takes a message dict (as returned by the warden
``mail.check`` RPC) and returns a ``(category, confidence, signal)``
triple. Categories are intentionally small — we want a label that's
useful for tracking application state in the dashboard, not perfect
semantic understanding.

Categories:
    ack         — application received / thanks-for-applying
    rejection   — "unfortunately / not moving forward / we've decided"
    interview   — interview invite, scheduling request, phone screen
    followup    — recruiter asking for information / status
    auto        — automated noise (newsletters, marketing, job alerts)
    unknown     — couldn't decide; leave for a human or an LLM pass

Confidence is coarse (``high`` / ``medium`` / ``low``), signalling how
much we trust the rule set on this message. Downstream tools can show
low-confidence classifications with a question mark.

We deliberately look at subject + sender first (those carry most of the
signal) and fall back to the body only when needed. That keeps the
classifier fast enough to run across a full inbox.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---------- regex rules ----------

_ACK_SUBJECT = re.compile(
    r"\b(application received|thanks for applying|thank you for applying|"
    r"we('?|&#39;)?ve received|your application|application (to|for) .+ received|"
    r"application confirmation|next steps)\b",
    re.I,
)

_REJECTION_SUBJECT = re.compile(
    r"\b(update on your application|regarding your application|your application status)\b",
    re.I,
)
_REJECTION_BODY = re.compile(
    r"\b(unfortunately|we('?|&#39;)?ve decided|regret to inform|"
    r"not moving forward|not a (match|fit)|not proceeding|"
    r"decided not to (move|proceed)|position has been filled|"
    r"chosen (another|other) candidate|pursue other candidate|"
    r"we will not be (moving|proceeding)|will not be continuing)\b",
    re.I,
)

_INTERVIEW_SUBJECT = re.compile(
    r"\b(interview|phone screen|tech(nical)? screen|schedule a (call|chat)|"
    r"chat with|meet with|coding exercise|take.?home|assessment|"
    r"next round|onsite|panel)\b",
    re.I,
)

_FOLLOWUP_BODY = re.compile(
    r"\b(could you (share|send|provide)|do you have (a|any) "
    r"(availability|resume|cv|references)|when are you available|"
    r"please (share|send|provide|complete)|one more question|"
    r"quick question|can we chat)\b",
    re.I,
)

_AUTO_FROM = re.compile(
    r"(noreply|no-reply|donotreply|do-not-reply|newsletter|notifications?|"
    r"updates?|info|hello|team|marketing)@",
    re.I,
)
_AUTO_SUBJECT = re.compile(
    r"\b(jobs? (for you|alert|matches)|new (jobs?|roles?)|this week at|"
    r"weekly digest|newsletter|unsubscribe)\b",
    re.I,
)

_GREENHOUSE_NOREPLY = re.compile(r"@(greenhouse|mail\.greenhouse)\.io$", re.I)
_LEVER_NOREPLY = re.compile(r"@(hire\.)?lever\.co$", re.I)


# ---------- data ----------

@dataclass(slots=True, frozen=True)
class Classification:
    category: str
    confidence: str   # "high" | "medium" | "low"
    signal: str       # short human-readable reason

    def as_dict(self) -> dict[str, str]:
        return {"category": self.category, "confidence": self.confidence,
                "signal": self.signal}


# ---------- entry point ----------

def classify(message: dict) -> Classification:
    """Classify one message dict ``{from, subject, date, text_body, ...}``."""
    subject = str(message.get("subject") or "")
    from_addr = str(message.get("from") or "")
    body = str(message.get("text_body") or "")

    # Rejection wins over ack if both match — a rejection often opens
    # with "Thank you for applying" then pivots.
    if _REJECTION_BODY.search(body):
        return Classification("rejection", "high",
                               f"body matched rejection phrase")
    if _REJECTION_SUBJECT.search(subject) and _REJECTION_BODY.search(body):
        return Classification("rejection", "high",
                               f"subject+body rejection")

    # Interview invites are the highest-signal category for a human;
    # flag aggressively even on ambiguous matches.
    if _INTERVIEW_SUBJECT.search(subject):
        return Classification("interview", "high",
                               f"subject matched interview phrase")
    if re.search(r"\bschedule\b.*\b(interview|call|chat)\b", body, re.I):
        return Classification("interview", "medium",
                               "body mentions scheduling an interview/call")

    # Acknowledgements — Greenhouse/Lever noreply with ack wording.
    if _ACK_SUBJECT.search(subject):
        return Classification("ack", "high",
                               "subject matched application-received phrase")
    if _GREENHOUSE_NOREPLY.search(from_addr) or _LEVER_NOREPLY.search(from_addr):
        if re.search(r"\bapplication\b|\breceived\b|\bthank", subject, re.I):
            return Classification("ack", "medium",
                                   "ATS noreply sender with application subject")

    # Follow-up asks — human recruiter wanting a reply.
    if _FOLLOWUP_BODY.search(body) and not _AUTO_FROM.search(from_addr):
        return Classification("followup", "medium",
                               "recruiter appears to need a response")

    # Automated noise.
    if _AUTO_FROM.search(from_addr) or _AUTO_SUBJECT.search(subject):
        return Classification("auto", "high", "automated / marketing sender")

    return Classification("unknown", "low",
                           "no rule matched — review manually or feed to LLM")


__all__ = ["Classification", "classify"]
