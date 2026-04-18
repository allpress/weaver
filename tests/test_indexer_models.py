from __future__ import annotations

import pytest

from weaver.indexer.models import ExtractedArticle, Person, Project


def test_roundtrip_minimal() -> None:
    a = ExtractedArticle(summary="hi")
    data = a.model_dump()
    b = ExtractedArticle.model_validate(data)
    assert b.summary == "hi"
    assert b.key_concepts == []


def test_accepts_full_shape() -> None:
    data = {
        "summary": "two paragraphs of technical prose",
        "key_concepts": ["retrieval-augmented generation", "agent loops"],
        "people": [
            {"name": "Andrej Karpathy", "role": "mentioned"},
            {"name": "Lilian Weng", "role": "author", "affiliation": "OpenAI"},
        ],
        "projects": [{"name": "LangChain", "url": "https://langchain.com"}],
        "technologies": ["PyTorch", "ChromaDB"],
        "references": ["https://arxiv.org/abs/2005.11401"],
    }
    a = ExtractedArticle.model_validate(data)
    assert len(a.people) == 2
    assert a.people[1].affiliation == "OpenAI"
    assert a.projects[0].url == "https://langchain.com"


def test_rejects_missing_summary() -> None:
    with pytest.raises(Exception):
        ExtractedArticle.model_validate({"summary": None})
