from __future__ import annotations

from pathlib import Path

import pytest

from weaver.aggregator.sources import Source, SourceConfigError, find_source, load_sources


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "sources.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_seed_packaged() -> None:
    """The packaged seed should parse and contain well-known sources."""
    sources = load_sources()
    assert len(sources) >= 5
    names = {s.name for s in sources}
    assert "martin-fowler" in names
    assert "simon-willison" in names


def test_load_user_path(tmp_path: Path) -> None:
    path = _write(tmp_path, """
sources:
  - name: only-one
    kind: rss
    url: https://example.com/feed
    author: Example
""")
    sources = load_sources(path)
    assert len(sources) == 1
    s = sources[0]
    assert s.name == "only-one"
    assert s.kind == "rss"
    assert s.throttle_seconds == 3600       # default
    assert s.fetch_article_bodies is True


def test_reject_missing_required(tmp_path: Path) -> None:
    path = _write(tmp_path, """
sources:
  - name: bad
    kind: rss
""")
    with pytest.raises(SourceConfigError, match="need name, kind, url"):
        load_sources(path)


def test_reject_bad_kind(tmp_path: Path) -> None:
    path = _write(tmp_path, """
sources:
  - name: x
    kind: ftp
    url: https://x/
""")
    with pytest.raises(SourceConfigError, match="not in"):
        load_sources(path)


def test_reject_duplicate_name(tmp_path: Path) -> None:
    path = _write(tmp_path, """
sources:
  - {name: a, kind: rss, url: https://a/}
  - {name: a, kind: atom, url: https://a2/}
""")
    with pytest.raises(SourceConfigError, match="duplicate"):
        load_sources(path)


def test_find_source_returns_none_for_unknown() -> None:
    sources = [Source(name="x", kind="rss", url="https://x/")]
    assert find_source(sources, "missing") is None
    assert find_source(sources, "x") is not None
