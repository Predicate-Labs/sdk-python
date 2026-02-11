from __future__ import annotations

from predicate.browser import _domain_matches, _extract_host, _is_domain_allowed


def test_domain_matches_suffix() -> None:
    assert _domain_matches("sub.example.com", "example.com") is True
    assert _domain_matches("example.com", "example.com") is True
    assert _domain_matches("example.com", "*.example.com") is True
    assert _domain_matches("other.com", "example.com") is False
    assert _domain_matches("example.com", "https://example.com") is True
    assert _domain_matches("localhost", "http://localhost:3000") is True


def test_domain_allowlist_denylist() -> None:
    assert _is_domain_allowed("a.example.com", ["example.com"], []) is True
    assert _is_domain_allowed("a.example.com", ["example.com"], ["bad.com"]) is True
    assert _is_domain_allowed("bad.example.com", [], ["example.com"]) is False
    assert _is_domain_allowed("x.com", ["example.com"], []) is False
    assert _is_domain_allowed("example.com", ["https://example.com"], []) is True


def test_extract_host_handles_ports() -> None:
    assert _extract_host("http://localhost:3000") == "localhost"
    assert _extract_host("localhost:3000") == "localhost"


def test_keep_alive_skips_close() -> None:
    from predicate.browser import SentienceBrowser

    class Dummy:
        def __init__(self) -> None:
            self.closed = False

        def close(self):
            self.closed = True

        def stop(self):
            self.closed = True

    browser = SentienceBrowser()
    browser.keep_alive = True
    dummy_context = Dummy()
    dummy_playwright = Dummy()
    browser.context = dummy_context
    browser.playwright = dummy_playwright
    browser._extension_path = None

    browser.close()
    assert dummy_context.closed is False
    assert dummy_playwright.closed is False
