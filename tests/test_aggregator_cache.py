from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from weaver.aggregator.cache import (
    CacheLayout,
    ItemMeta,
    cache_stats,
    compute_sha,
    item_exists,
    iter_cached_items,
    read_item,
    write_item,
)


def test_sha_is_stable() -> None:
    a = compute_sha("https://example.com/article-1")
    b = compute_sha("https://example.com/article-1")
    c = compute_sha("https://example.com/article-2")
    assert a == b
    assert a != c
    assert len(a) == 40


def test_layout_paths(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    # tmp_context fixture redirects paths.repo_root, so the path is under tmp.
    assert layout.root.name == "aggregator"
    assert layout.state_file.name == "state.json"
    assert layout.items_dir("src").name == "src"


def test_write_and_read_item(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)

    meta = ItemMeta(
        sha=compute_sha("https://example.com/post"),
        source="example",
        url="https://example.com/post",
        canonical_url="https://example.com/post",
        title="A Post",
        author="Author Name",
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        body_filename="body.html",
    )
    write_item(layout, meta=meta, body=b"<html>hi</html>")

    assert item_exists(layout, "example", meta.sha)
    loaded_meta, loaded_body = read_item(layout, "example", meta.sha)
    assert loaded_meta.title == "A Post"
    assert loaded_meta.sha == meta.sha
    assert loaded_body == b"<html>hi</html>"


def test_iter_cached_items(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        url = f"https://a.example/{i}"
        meta = ItemMeta(
            sha=compute_sha(url), source="src-a", url=url, canonical_url=url,
            title=f"t{i}", author=None, published_at=None,
        )
        write_item(layout, meta=meta, body=b"x")

    items = list(iter_cached_items(layout, source="src-a"))
    assert len(items) == 3
    assert {m.title for m in items} == {"t0", "t1", "t2"}


def test_cache_stats(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    for src, i in [("a", 0), ("b", 0), ("b", 1)]:
        url = f"https://{src}.example/item-{i}"
        meta = ItemMeta(
            sha=compute_sha(url), source=src, url=url, canonical_url=url,
            title="t", author=None, published_at=None,
        )
        write_item(layout, meta=meta, body=b"")
    stats = cache_stats(layout)
    assert stats["total"] == 3
    assert stats["per_source"] == {"a": 1, "b": 2}
