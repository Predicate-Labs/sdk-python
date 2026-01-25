"""
Tests for read functionality
"""

from typing import Any

from sentience import SentienceBrowser, read


def test_read_text():
    """Test reading page as text"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = read(browser, output_format="text")

        assert result.status == "success"
        assert result.format == "text"
        assert result.content is not None
        assert result.length is not None
        assert len(result.content) > 0
        assert result.url == "https://example.com/"


def test_read_markdown():
    """Test reading page as markdown"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = read(browser, output_format="markdown")

        assert result.status == "success"
        assert result.format == "markdown"
        assert result.content is not None
        assert result.length is not None
        assert len(result.content) > 0
        assert result.url == "https://example.com/"


def test_read_markdown_enhanced():
    """Test reading page as markdown with enhancement"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Test with enhancement (default)
        result_enhanced = read(browser, output_format="markdown", enhance_markdown=True)

        assert result_enhanced.status == "success"
        assert result_enhanced.format == "markdown"
        assert len(result_enhanced.content) > 0

        # Test without enhancement
        result_basic = read(browser, output_format="markdown", enhance_markdown=False)

        assert result_basic.status == "success"
        assert result_basic.format == "markdown"
        assert len(result_basic.content) > 0

        # Enhanced markdown should be different (and likely better formatted)
        # Note: They might be similar for simple pages, but enhanced should handle more cases
        assert isinstance(result_enhanced.content, str)
        assert isinstance(result_basic.content, str)


def test_read_falls_back_when_extension_returns_success_but_empty(monkeypatch):
    """
    Regression test: some sites can produce extension-backed reads with
    status='success' but empty/near-empty content (e.g. '\\n').

    In that case, SDK should fall back to Playwright primitives (page.content()).
    """
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        def fake_evaluate(_script: Any, arg: Any = None):
            fmt = "raw"
            if isinstance(arg, dict) and "format" in arg:
                fmt = arg["format"]
            # Mimic buggy extension response: success but empty
            return {
                "status": "success",
                "url": browser.page.url,
                "format": fmt,
                "content": "\n",
                "length": 1,
                "error": None,
            }

        monkeypatch.setattr(browser.page, "evaluate", fake_evaluate)

        result = read(browser, output_format="raw", enhance_markdown=False)
        assert result.status == "success"
        assert result.format == "raw"
        assert result.length > 100
        assert "<html" in result.content.lower() or "<!doctype" in result.content.lower()
