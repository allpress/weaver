"""Pydantic schemas for LLM-extracted article metadata."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Person(BaseModel):
    name: str = Field(..., description="Canonical name, e.g. 'Andrej Karpathy'")
    role: str | None = Field(
        None, description="'author' | 'mentioned' | 'cited' | None if unclear"
    )
    affiliation: str | None = None


class Project(BaseModel):
    name: str = Field(..., description="Project/framework name")
    url: str | None = None
    description: str | None = None


class ExtractedArticle(BaseModel):
    summary: str = Field(..., description="2-4 paragraphs, information-dense prose, no meta-commentary")
    key_concepts: list[str] = Field(
        default_factory=list,
        description="Up to 10 canonical concept names (e.g. 'retrieval-augmented generation')",
    )
    people: list[Person] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    technologies: list[str] = Field(
        default_factory=list,
        description="Libraries, tools, algorithms, or model names referenced",
    )
    references: list[str] = Field(
        default_factory=list, description="URLs cited inline in the article"
    )


class ArticleFacts(BaseModel):
    """Durable per-article record written to the graph after extraction."""
    sha: str
    source: str
    url: str
    title: str
    author: str | None
    published_at: datetime | None
    extracted: ExtractedArticle
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
    model: str | None = None   # which LLM produced the extraction
