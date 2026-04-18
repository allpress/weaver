from __future__ import annotations

from weaver.indexer.html_strip import html_to_text


def test_strips_nav_and_script() -> None:
    html = """
    <html><head><title>X</title><script>var a=1</script></head>
    <body>
      <nav><a href="/">home</a></nav>
      <article>
        <h1>The real article</h1>
        <p>Paragraph one.</p>
        <p>Paragraph two.</p>
      </article>
      <footer>&copy; 2025</footer>
    </body></html>
    """
    text = html_to_text(html)
    assert "home" not in text
    assert "2025" not in text
    assert "var a=1" not in text
    assert "Paragraph one" in text
    assert "Paragraph two" in text


def test_falls_back_to_body_when_no_article() -> None:
    html = "<html><body><p>just body</p></body></html>"
    text = html_to_text(html)
    assert "just body" in text


def test_handles_bytes() -> None:
    html = b"<html><body><p>bytes in</p></body></html>"
    assert "bytes in" in html_to_text(html)


def test_truncates_at_max() -> None:
    html = "<html><body>" + ("<p>word</p>" * 2000) + "</body></html>"
    text = html_to_text(html, max_chars=200)
    assert len(text) <= 300      # truncation marker adds a few chars
    assert "truncated" in text


def test_collapses_whitespace() -> None:
    html = "<html><body><p>a    b\n\n\n\nc</p></body></html>"
    text = html_to_text(html)
    assert "    " not in text
    assert "\n\n\n" not in text
