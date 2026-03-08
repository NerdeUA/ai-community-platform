from app.services.crawler import _extract_article, _extract_links


def test_extract_article_uses_trafilatura_bare_extraction() -> None:
    html = (
        "<html><head><title>Test article</title></head>"
        "<body><article><h1>Test article</h1>"
        "<p>This is a long enough article body for extraction. "
        "It contains multiple sentences so text length clearly exceeds one hundred characters. "
        "The crawler should parse this content successfully.</p>"
        "</article></body></html>"
    )

    article = _extract_article(html, "https://example.org/article")

    assert article is not None
    assert "title" in article
    assert len(article["raw_text"]) >= 100


def test_extract_links_falls_back_to_html_anchors() -> None:
    source_html = (
        "<html><body>"
        '<a href="/post-1">post one</a>'
        '<a href="https://example.org/post-2">post two</a>'
        '<a href="#ignored">anchor</a>'
        "</body></html>"
    )

    links = _extract_links(source_html, "https://example.org/news")

    assert "https://example.org/post-1" in links
    assert "https://example.org/post-2" in links


def test_extract_links_filters_static_and_offsite_urls() -> None:
    source_html = (
        "<html><body>"
        '<a href="/article/one">article one</a>'
        '<a href="/assets/app.css">css asset</a>'
        '<a href="https://cdn.example.net/file.js">external js</a>'
        '<a href="https://example.org/">home</a>'
        "</body></html>"
    )

    links = _extract_links(source_html, "https://example.org/news")

    assert links == ["https://example.org/article/one"]


def test_extract_links_keeps_only_reddit_post_links() -> None:
    source_html = (
        "<html><body>"
        '<a href="/r/ClaudeAI/">subreddit root</a>'
        '<a href="/r/ClaudeAI/comments/abc123/good_post/">post</a>'
        '<a href="https://www.redditstatic.com/style.css">static css</a>'
        "</body></html>"
    )

    links = _extract_links(source_html, "https://www.reddit.com/r/ClaudeAI/")

    assert links == ["https://www.reddit.com/r/ClaudeAI/comments/abc123/good_post/"]
