"""Greenhouse Job Board API client.

Port of bulk-submitter/src/jobs/greenhouse-api.ts. Public unauthenticated
endpoints; no secret needed. Two methods used by the plan builder:

  * :meth:`GreenhouseClient.list_jobs(board)` — paginated job list
  * :meth:`GreenhouseClient.get_job(board, job_id)` — full job detail
    including the ``questions`` array (field names, types, options).

Greenhouse's question schema (confirmed against Anthropic, 2026-04):

    {
      "label":       str,
      "description": str | None,            # optional HTML
      "required":    bool,
      "fields": [
        {
          "name":   str,                    # "first_name" / "question_<id>"
          "type":   str,                    # input_text | textarea |
                                            # multi_value_single_select | input_file
          "values": [ {"label": str, "value": str | int}, ... ]
        },
        ...
      ]
    }

(The top-level ``q.id`` / ``q.type`` / ``q.values`` keys some other
documentation describes DO NOT exist on this endpoint. Trust ``fields``.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


BOARD_TOKENS: dict[str, str] = {
    # AI labs (kept together, rank-ordered roughly by research)
    "Anthropic": "anthropic",
    "Scale AI": "scaleai",
    "Glean": "gleanwork",
    "xAI": "xai",
    "Fireworks AI": "fireworksai",
    "Cresta": "cresta",
    "CoreWeave": "coreweave",
    "Together AI": "togetherai",
    # Non-AI companies that came up during earlier probes
    "Reddit": "reddit",
    "Webflow": "webflow",
    "Mercury": "mercury",
    "SmithRx": "smithrx",
    "ClickUp": "clickup",
    "Datadog": "datadoghq",
}


@dataclass(slots=True, frozen=True)
class GreenhouseLocation:
    name: str = ""


@dataclass(slots=True, frozen=True)
class GreenhouseJob:
    id: int
    title: str
    absolute_url: str
    location: GreenhouseLocation = field(default_factory=GreenhouseLocation)
    first_published: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> "GreenhouseJob":
        return cls(
            id=int(d["id"]),
            title=str(d.get("title", "")),
            absolute_url=str(d.get("absolute_url", "")),
            location=GreenhouseLocation(name=str((d.get("location") or {}).get("name", ""))),
            first_published=d.get("first_published"),
            updated_at=d.get("updated_at"),
        )


@dataclass(slots=True, frozen=True)
class GreenhouseField:
    name: str
    type: str
    values: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> "GreenhouseField":
        return cls(
            name=str(d.get("name", "")),
            type=str(d.get("type", "")),
            values=tuple(d.get("values") or ()),
        )


@dataclass(slots=True, frozen=True)
class GreenhouseQuestion:
    label: str
    required: bool
    description: str | None
    fields: tuple[GreenhouseField, ...]

    @property
    def primary_field(self) -> GreenhouseField | None:
        return self.fields[0] if self.fields else None

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> "GreenhouseQuestion":
        return cls(
            label=str(d.get("label", "")),
            required=bool(d.get("required", False)),
            description=d.get("description"),
            fields=tuple(GreenhouseField.from_api(f) for f in (d.get("fields") or ())),
        )


class GreenhouseClient:
    """Unauthenticated Greenhouse board client.

    One instance per board token is fine; re-uses a pooled httpx client.
    Caller is responsible for throttling if paginating across many jobs.
    """

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, board: str, *, timeout_s: float = 15.0) -> None:
        token = BOARD_TOKENS.get(board)
        if token is None:
            raise ValueError(f"unknown board: {board!r}. Known: {sorted(BOARD_TOKENS)}")
        self._board = board
        self._token = token
        self._client = httpx.Client(timeout=timeout_s, follow_redirects=True,
                                     headers={"User-Agent": "weaver-submitter/0.1"})

    def __enter__(self) -> "GreenhouseClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @property
    def board(self) -> str:
        return self._board

    def list_jobs(self, *, content: bool = False) -> list[GreenhouseJob]:
        """Every open posting on the board. ``content=True`` inlines description HTML."""
        url = f"{self.BASE_URL}/{self._token}/jobs"
        params = {"content": "true"} if content else {}
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json() or {}
        return [GreenhouseJob.from_api(j) for j in payload.get("jobs", [])]

    def get_job(self, job_id: int, *, questions: bool = True) -> dict[str, Any]:
        """Full job detail. ``questions=True`` (default) inlines the form schema."""
        url = f"{self.BASE_URL}/{self._token}/jobs/{job_id}"
        params = {"questions": "true"} if questions else {}
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json() or {}

    def get_questions(self, job_id: int) -> list[GreenhouseQuestion]:
        """Structured question list for a single job."""
        data = self.get_job(job_id, questions=True)
        return [GreenhouseQuestion.from_api(q) for q in data.get("questions", [])]


def extract_job_id(url: str) -> int | None:
    """Pull a numeric job id out of a Greenhouse URL (``/jobs/1234567008`` etc.)."""
    import re
    m = re.search(r"(?:jobs/|token=)(\d+)", url)
    return int(m.group(1)) if m else None


__all__ = [
    "BOARD_TOKENS",
    "GreenhouseClient",
    "GreenhouseField",
    "GreenhouseJob",
    "GreenhouseLocation",
    "GreenhouseQuestion",
    "extract_job_id",
]
