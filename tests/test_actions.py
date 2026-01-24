"""
Tests for actions (click, type, press, click_rect)
"""

import pytest

from sentience import (
    AsyncSentienceBrowser,
    SentienceBrowser,
    back,
    check,
    clear,
    click,
    click_rect,
    find,
    press,
    scroll_to,
    search,
    search_async,
    select_option,
    send_keys,
    send_keys_async,
    snapshot,
    submit,
    type_text,
    uncheck,
    upload_file,
)


def test_click():
    """Test click action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        link = find(snap, "role=link")

        if link:
            result = click(browser, link.id)
            assert result.success is True
            assert result.duration_ms > 0
            assert result.outcome in ["navigated", "dom_updated"]


def test_type_text():
    """Test type action"""
    with SentienceBrowser() as browser:
        # Use a page with a text input
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Find textbox if available
        snap = snapshot(browser)
        textbox = find(snap, "role=textbox")

        if textbox:
            result = type_text(browser, textbox.id, "hello")
            assert result.success is True
            assert result.duration_ms > 0


def test_press():
    """Test press action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = press(browser, "Enter")
        assert result.success is True
        assert result.duration_ms > 0


def test_send_keys():
    """Test send_keys helper"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = send_keys(browser, "CTRL+L")
        assert result.success is True
        assert result.duration_ms > 0


def test_send_keys_empty_sequence() -> None:
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        with pytest.raises(ValueError, match="empty"):
            send_keys(browser, "")


def test_send_keys_braced_sequence() -> None:
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = send_keys(browser, "{CTRL+L}")
        assert result.success is True


def test_send_keys_multi_sequence_and_alias() -> None:
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = send_keys(browser, "Tab Tab Enter")
        assert result.success is True
        result = send_keys(browser, "CMD+C")
        assert result.success is True


def test_search_builds_url() -> None:
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = search(browser, "sentience sdk", engine="duckduckgo")
        assert result.success is True
        assert result.duration_ms > 0

        result = search(browser, "sentience sdk", engine="google")
        assert result.success is True

        result = search(browser, "sentience sdk", engine="bing")
        assert result.success is True

        result = search(browser, "sentience sdk", engine="google.com")
        assert result.success is True


def test_search_empty_query() -> None:
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        with pytest.raises(ValueError, match="empty"):
            search(browser, "")


def test_search_disallowed_domain() -> None:
    with SentienceBrowser(allowed_domains=["example.com"]) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        with pytest.raises(ValueError, match="domain not allowed"):
            search(browser, "sentience sdk", engine="duckduckgo")


@pytest.mark.asyncio
async def test_search_async() -> None:
    async with AsyncSentienceBrowser() as browser:
        await browser.page.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        result = await search_async(
            browser, "sentience sdk", engine="duckduckgo", take_snapshot=True
        )
        assert result.success is True
        assert result.snapshot_after is not None


@pytest.mark.asyncio
async def test_send_keys_async() -> None:
    async with AsyncSentienceBrowser() as browser:
        await browser.page.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        result = await send_keys_async(browser, "CTRL+L")
        assert result.success is True


def test_click_rect():
    """Test click_rect with rect dict"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Click at a specific rectangle (top-left area)
        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": 30})
        assert result.success is True
        assert result.duration_ms > 0
        assert result.outcome in ["navigated", "dom_updated"]


def test_click_rect_with_bbox():
    """Test click_rect with BBox object"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Get an element and click its bbox
        snap = snapshot(browser)
        link = find(snap, "role=link")

        if link:
            result = click_rect(
                browser,
                {
                    "x": link.bbox.x,
                    "y": link.bbox.y,
                    "w": link.bbox.width,
                    "h": link.bbox.height,
                },
            )
            assert result.success is True
            assert result.duration_ms > 0


def test_click_rect_without_highlight():
    """Test click_rect without visual highlight"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": 30}, highlight=False)
        assert result.success is True
        assert result.duration_ms > 0


def test_click_rect_invalid_rect():
    """Test click_rect with invalid rectangle dimensions"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Invalid: zero width
        result = click_rect(browser, {"x": 100, "y": 100, "w": 0, "h": 30})
        assert result.success is False
        assert result.error is not None
        assert result.error is not None
        assert result.error.get("code") == "invalid_rect"

        # Invalid: negative height
        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": -10})
        assert result.success is False
        assert result.error is not None
        assert result.error is not None
        assert result.error.get("code") == "invalid_rect"


def test_click_rect_with_snapshot():
    """Test click_rect with snapshot after action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": 30}, take_snapshot=True)
        assert result.success is True
        assert result.snapshot_after is not None
        assert result.snapshot_after.status == "success"
        assert len(result.snapshot_after.elements) > 0


def test_click_hybrid_approach():
    """Test that click() uses hybrid approach (mouse.click at center)"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        link = find(snap, "role=link")

        if link:
            # Test hybrid approach (mouse.click at center)
            result = click(browser, link.id, use_mouse=True)
            assert result.success is True
            assert result.duration_ms > 0
            # Navigation may happen, which is expected for links
            assert result.outcome in ["navigated", "dom_updated"]


def test_click_js_approach():
    """Test that click() can use JS-based approach (legacy)"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        link = find(snap, "role=link")

        if link:
            # Test JS-based click (legacy approach)
            result = click(browser, link.id, use_mouse=False)
            assert result.success is True
            assert result.duration_ms > 0
            # Navigation may happen, which is expected for links
            assert result.outcome in ["navigated", "dom_updated"]


def test_scroll_to():
    """Test scroll_to action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        # Find an element to scroll to (typically the last link or element)
        elements = [el for el in snap.elements if el.role == "link"]

        if elements:
            # Get the last element which might be out of viewport
            element = elements[-1] if len(elements) > 1 else elements[0]
            result = scroll_to(browser, element.id)
            assert result.success is True
            assert result.duration_ms > 0
            assert result.outcome in ["navigated", "dom_updated"]


def test_scroll_to_instant():
    """Test scroll_to with instant behavior"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        elements = [el for el in snap.elements if el.role == "link"]

        if elements:
            element = elements[0]
            result = scroll_to(browser, element.id, behavior="instant", block="start")
            assert result.success is True
            assert result.duration_ms > 0


def test_scroll_to_with_snapshot():
    """Test scroll_to with snapshot after action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        elements = [el for el in snap.elements if el.role == "link"]

        if elements:
            element = elements[0]
            result = scroll_to(browser, element.id, take_snapshot=True)
            assert result.success is True
            assert result.snapshot_after is not None
            assert result.snapshot_after.status == "success"


def test_scroll_to_invalid_element():
    """Test scroll_to with invalid element ID"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Try to scroll to non-existent element
        result = scroll_to(browser, 99999)
        assert result.success is False
        assert result.error is not None
        assert result.error is not None
        assert result.error.get("code") == "scroll_failed"


def _registry_find_id(browser: SentienceBrowser, predicate_js: str) -> int | None:
    """
    Find a sentience_registry id by running a predicate(el) in page context.
    Requires a snapshot() call before this, so registry is populated.
    """
    if not browser.page:
        return None
    return browser.page.evaluate(
        f"""
        () => {{
            const reg = window.sentience_registry || {{}};
            for (const [id, el] of Object.entries(reg)) {{
                try {{
                    if (({predicate_js})(el)) return Number(id);
                }} catch {{}}
            }}
            return null;
        }}
        """
    )


def test_form_crud_helpers(tmp_path):
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.set_content(
            """
            <html><body>
              <input id="t" value="hello" />
              <input id="cb" type="checkbox" />
              <select id="sel">
                <option value="a">Alpha</option>
                <option value="b">Beta</option>
              </select>
              <form id="f">
                <input id="file" type="file" />
                <button id="btn" type="submit">Submit</button>
              </form>
              <script>
                window._submitted = false;
                document.getElementById('f').addEventListener('submit', (e) => {
                  e.preventDefault();
                  window._submitted = true;
                });
              </script>
            </body></html>
            """
        )

        # Populate registry
        snapshot(browser)

        tid = _registry_find_id(browser, "(el) => el && el.id === 't'")
        cbid = _registry_find_id(browser, "(el) => el && el.id === 'cb'")
        selid = _registry_find_id(browser, "(el) => el && el.id === 'sel'")
        fileid = _registry_find_id(browser, "(el) => el && el.id === 'file'")
        btnid = _registry_find_id(browser, "(el) => el && el.id === 'btn'")
        assert tid and cbid and selid and fileid and btnid

        r1 = clear(browser, tid)
        assert r1.success is True
        assert browser.page.evaluate("() => document.getElementById('t').value") == ""

        r2 = check(browser, cbid)
        assert r2.success is True
        assert browser.page.evaluate("() => document.getElementById('cb').checked") is True

        r3 = uncheck(browser, cbid)
        assert r3.success is True
        assert browser.page.evaluate("() => document.getElementById('cb').checked") is False

        r4 = select_option(browser, selid, "b")
        assert r4.success is True
        assert browser.page.evaluate("() => document.getElementById('sel').value") == "b"

        p = tmp_path / "upload.txt"
        p.write_text("hi")
        r5 = upload_file(browser, fileid, str(p))
        assert r5.success is True
        assert (
            browser.page.evaluate("() => document.getElementById('file').files[0].name")
            == "upload.txt"
        )

        r6 = submit(browser, btnid)
        assert r6.success is True
        assert browser.page.evaluate("() => window._submitted") is True

        # back() is best-effort; just ensure it doesn't crash and returns ActionResult
        r7 = back(browser)
        assert r7.duration_ms >= 0


def test_type_text_with_delay():
    """Test type_text with human-like delay"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        textbox = find(snap, "role=textbox")

        if textbox:
            # Test with 10ms delay between keystrokes
            result = type_text(browser, textbox.id, "hello", delay_ms=10)
            assert result.success is True
            # Duration should be longer due to delays
            assert result.duration_ms >= 50  # At least 5 chars * 10ms
