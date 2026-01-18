import pytest

from sentience.models import SnapshotOptions
from sentience.read import read
from sentience.snapshot import snapshot
from sentience.text_search import find_text_rect


class _FakePage:
    def __init__(self):
        self.evaluate_calls: list[tuple[str, object | None]] = []
        self.url = "https://example.com/"

    def evaluate(self, expression: str, arg=None):
        self.evaluate_calls.append((expression, arg))

        # Snapshot path: return a minimal successful snapshot payload
        if "window.sentience.snapshot" in expression:
            return {
                "status": "success",
                "url": self.url,
                "elements": [],
                "raw_elements": [],
            }

        # Read path: return a minimal successful read payload
        if "window.sentience.read" in expression:
            fmt = (arg or {}).get("format", "raw")
            return {
                "status": "success",
                "url": self.url,
                "format": fmt,
                "content": "<html></html>" if fmt == "raw" else "content",
                "length": 7,
            }

        # findTextRect availability check
        if "typeof window.sentience.findTextRect" in expression:
            return False

        raise AssertionError(f"Unexpected page.evaluate call: {expression!r}")


class _FakeBrowser:
    def __init__(self, page: _FakePage):
        self.page = page
        self.api_key = None
        self.api_url = None


def test_snapshot_default_limit_not_sent_to_extension(monkeypatch):
    """
    Contract: SnapshotOptions.limit defaults to 50 and the SDK avoids sending
    'limit' to the extension unless it differs from default.
    """
    # Avoid any real extension waiting logic
    from sentience.browser_evaluator import BrowserEvaluator

    monkeypatch.setattr(BrowserEvaluator, "wait_for_extension", lambda *args, **kwargs: None)

    page = _FakePage()
    browser = _FakeBrowser(page)

    snap = snapshot(browser)  # type: ignore[arg-type]
    assert snap.url == "https://example.com/"

    # Find the snapshot evaluate call and assert the options payload
    snap_calls = [(expr, arg) for (expr, arg) in page.evaluate_calls if "snapshot(" in expr]
    assert len(snap_calls) == 1
    _, options = snap_calls[0]
    assert isinstance(options, dict)
    assert "limit" not in options  # default should not be sent


def test_snapshot_non_default_limit_is_sent_to_extension(monkeypatch):
    from sentience.browser_evaluator import BrowserEvaluator

    monkeypatch.setattr(BrowserEvaluator, "wait_for_extension", lambda *args, **kwargs: None)

    page = _FakePage()
    browser = _FakeBrowser(page)

    snapshot(browser, SnapshotOptions(limit=10))  # type: ignore[arg-type]

    snap_calls = [(expr, arg) for (expr, arg) in page.evaluate_calls if "snapshot(" in expr]
    assert len(snap_calls) == 1
    _, options = snap_calls[0]
    assert options["limit"] == 10


def test_read_passes_requested_format():
    page = _FakePage()
    browser = _FakeBrowser(page)

    result = read(browser, output_format="text", enhance_markdown=False)  # type: ignore[arg-type]
    assert result.format == "text"

    read_calls = [
        (expr, arg) for (expr, arg) in page.evaluate_calls if "window.sentience.read" in expr
    ]
    assert len(read_calls) == 1
    _, options = read_calls[0]
    assert options == {"format": "text"}


def test_find_text_rect_unavailable_raises(monkeypatch):
    """
    Contract: if the extension doesn't expose findTextRect, the SDK surfaces a clear error.
    """
    # Avoid any real extension waiting logic (and avoid sync/async page detection details)
    from sentience.browser_evaluator import BrowserEvaluator

    monkeypatch.setattr(BrowserEvaluator, "wait_for_extension", lambda *args, **kwargs: None)

    page = _FakePage()
    browser = _FakeBrowser(page)

    with pytest.raises(RuntimeError) as e:
        find_text_rect(browser, "Sign In")  # type: ignore[arg-type]

    assert "window.sentience.findTextRect is not available" in str(e.value)
