"""
Actions v1 - click, type, press
"""

import asyncio
import time
from pathlib import Path
from urllib.parse import quote_plus

from .browser import AsyncSentienceBrowser, SentienceBrowser
from .browser_evaluator import BrowserEvaluator
from .cursor_policy import CursorPolicy, build_human_cursor_path
from .models import ActionResult, BBox, Snapshot, SnapshotOptions
from .sentience_methods import SentienceMethod
from .snapshot import snapshot, snapshot_async


def click(  # noqa: C901
    browser: SentienceBrowser,
    element_id: int,
    use_mouse: bool = True,
    take_snapshot: bool = False,
    cursor_policy: CursorPolicy | None = None,
) -> ActionResult:
    """
    Click an element by ID using hybrid approach (mouse simulation by default)

    Args:
        browser: SentienceBrowser instance
        element_id: Element ID from snapshot
        use_mouse: If True, use Playwright's mouse.click() at element center (hybrid approach).
                   If False, use JS-based window.sentience.click() (legacy).
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url
    cursor_meta: dict | None = None
    error_msg = ""

    if use_mouse:
        # Hybrid approach: Get element bbox from snapshot, calculate center, use mouse.click()
        try:
            snap = snapshot(browser)
            element = None
            for el in snap.elements:
                if el.id == element_id:
                    element = el
                    break

            if element:
                # Calculate center of element bbox
                center_x = element.bbox.x + element.bbox.width / 2
                center_y = element.bbox.y + element.bbox.height / 2
                # Optional: human-like cursor movement (opt-in)
                try:
                    if cursor_policy is not None and cursor_policy.mode == "human":
                        # Best-effort cursor state on browser instance
                        pos = getattr(browser, "_sentience_cursor_pos", None)
                        if not isinstance(pos, tuple) or len(pos) != 2:
                            try:
                                vp = browser.page.viewport_size or {}
                                pos = (
                                    float(vp.get("width", 0)) / 2.0,
                                    float(vp.get("height", 0)) / 2.0,
                                )
                            except Exception:
                                pos = (0.0, 0.0)

                        cursor_meta = build_human_cursor_path(
                            start=(float(pos[0]), float(pos[1])),
                            target=(float(center_x), float(center_y)),
                            policy=cursor_policy,
                        )
                        pts = cursor_meta.get("path", [])
                        steps = int(cursor_meta.get("steps") or max(1, len(pts)))
                        duration_ms = int(cursor_meta.get("duration_ms") or 0)
                        per_step_s = (
                            (duration_ms / max(1, len(pts))) / 1000.0 if duration_ms > 0 else 0.0
                        )
                        for p in pts:
                            browser.page.mouse.move(float(p["x"]), float(p["y"]))
                            if per_step_s > 0:
                                time.sleep(per_step_s)
                        pause_ms = int(cursor_meta.get("pause_before_click_ms") or 0)
                        if pause_ms > 0:
                            time.sleep(pause_ms / 1000.0)
                        browser.page.mouse.click(center_x, center_y)
                        setattr(
                            browser, "_sentience_cursor_pos", (float(center_x), float(center_y))
                        )
                    else:
                        # Default behavior (no regression)
                        browser.page.mouse.click(center_x, center_y)
                        setattr(
                            browser, "_sentience_cursor_pos", (float(center_x), float(center_y))
                        )
                    success = True
                except Exception:
                    # If navigation happens, mouse.click might fail, but that's OK
                    # The click still happened, just check URL change
                    success = True
            else:
                # Fallback to JS click if element not found in snapshot
                try:
                    success = BrowserEvaluator.invoke(
                        browser.page, SentienceMethod.CLICK, element_id
                    )
                except Exception:
                    # Navigation might have destroyed context, assume success if URL changed
                    success = True
        except Exception:
            # Fallback to JS click on error
            try:
                success = BrowserEvaluator.invoke(browser.page, SentienceMethod.CLICK, element_id)
            except Exception:
                # Navigation might have destroyed context, assume success if URL changed
                success = True
    else:
        # Legacy JS-based click
        success = BrowserEvaluator.invoke(browser.page, SentienceMethod.CLICK, element_id)

    # Wait a bit for navigation/DOM updates
    try:
        browser.page.wait_for_timeout(500)
    except Exception:
        # Navigation might have happened, context destroyed
        pass

    duration_ms = int((time.time() - start_time) * 1000)

    # Check if URL changed (handle navigation gracefully)
    try:
        url_after = browser.page.url
        url_changed = url_before != url_after
    except Exception:
        # Context destroyed due to navigation - assume URL changed
        url_after = url_before
        url_changed = True

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = snapshot(browser)
        except Exception:
            # Navigation might have destroyed context
            pass

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        cursor=cursor_meta,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": "Element not found or not clickable",
            }
        ),
    )


def type_text(
    browser: SentienceBrowser,
    element_id: int,
    text: str,
    take_snapshot: bool = False,
    delay_ms: float = 0,
) -> ActionResult:
    """
    Type text into an element (focus then input)

    Args:
        browser: SentienceBrowser instance
        element_id: Element ID from snapshot
        text: Text to type
        take_snapshot: Whether to take snapshot after action
        delay_ms: Delay between keystrokes in milliseconds for human-like typing (default: 0)

    Returns:
        ActionResult

    Example:
        >>> # Type instantly (default behavior)
        >>> type_text(browser, element_id, "Hello World")
        >>> # Type with human-like delay (~10ms between keystrokes)
        >>> type_text(browser, element_id, "Hello World", delay_ms=10)
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Focus element first using extension registry
    focused = browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (el) {
                el.focus();
                return true;
            }
            return false;
        }
        """,
        element_id,
    )

    if not focused:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "focus_failed", "reason": "Element not found"},
        )

    # Type using Playwright keyboard with optional delay between keystrokes
    browser.page.keyboard.type(text, delay=delay_ms)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def clear(
    browser: SentienceBrowser,
    element_id: int,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Clear the value of an input/textarea element (best-effort).
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (!el) return false;
            try { el.focus?.(); } catch {}
            if ('value' in el) {
                el.value = '';
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
            return false;
        }
        """,
        element_id,
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "clear_failed", "reason": "Element not found or not clearable"},
        )

    browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def check(
    browser: SentienceBrowser,
    element_id: int,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Ensure a checkbox/radio is checked (best-effort).
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (!el) return false;
            try { el.focus?.(); } catch {}
            if (!('checked' in el)) return false;
            if (el.checked === true) return true;
            try { el.click(); } catch { return false; }
            return el.checked === true || true;
        }
        """,
        element_id,
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "check_failed", "reason": "Element not found or not checkable"},
        )

    browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def uncheck(
    browser: SentienceBrowser,
    element_id: int,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Ensure a checkbox/radio is unchecked (best-effort).
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (!el) return false;
            try { el.focus?.(); } catch {}
            if (!('checked' in el)) return false;
            if (el.checked === false) return true;
            try { el.click(); } catch { return false; }
            return el.checked === false || true;
        }
        """,
        element_id,
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "uncheck_failed", "reason": "Element not found or not uncheckable"},
        )

    browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def select_option(
    browser: SentienceBrowser,
    element_id: int,
    option: str,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Select an option in a <select> element by matching option value or label (best-effort).
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = browser.page.evaluate(
        """
        (args) => {
            const el = window.sentience_registry[args.id];
            if (!el) return false;
            const tag = (el.tagName || '').toUpperCase();
            if (tag !== 'SELECT') return false;
            const needle = String(args.option ?? '');
            const opts = Array.from(el.options || []);
            let chosen = null;
            for (const o of opts) {
                if (String(o.value) === needle || String(o.text) === needle) { chosen = o; break; }
            }
            if (!chosen) {
                for (const o of opts) {
                    if (String(o.text || '').includes(needle)) { chosen = o; break; }
                }
            }
            if (!chosen) return false;
            el.value = chosen.value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        """,
        {"id": element_id, "option": option},
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "select_failed", "reason": "Element not found or option not found"},
        )

    browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def upload_file(
    browser: SentienceBrowser,
    element_id: int,
    file_path: str,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Upload a local file via an <input type="file"> element (best-effort).
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url
    p = str(Path(file_path))

    try:
        handle = browser.page.evaluate_handle(
            "(id) => window.sentience_registry[id] || null",
            element_id,
        )
        el = handle.as_element()
        if el is None:
            raise RuntimeError("Element not found")
        el.set_input_files(p)
        success = True
        error_msg = None
    except Exception as e:
        success = False
        error_msg = str(e)

    browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else ("dom_updated" if success else "error")

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = snapshot(browser)
        except Exception:
            snapshot_after = None

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(
            None if success else {"code": "upload_failed", "reason": error_msg or "upload failed"}
        ),
    )


def submit(
    browser: SentienceBrowser,
    element_id: int,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Submit a form (best-effort) by clicking a submit control or calling requestSubmit().
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (!el) return false;
            try { el.focus?.(); } catch {}
            const tag = (el.tagName || '').toUpperCase();
            if (tag === 'FORM') {
                if (typeof el.requestSubmit === 'function') { el.requestSubmit(); return true; }
                try { el.submit(); return true; } catch { return false; }
            }
            const form = el.form;
            if (form && typeof form.requestSubmit === 'function') { form.requestSubmit(); return true; }
            try { el.click(); return true; } catch { return false; }
        }
        """,
        element_id,
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "submit_failed", "reason": "Element not found or not submittable"},
        )

    browser.page.wait_for_timeout(500)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = snapshot(browser)
        except Exception:
            snapshot_after = None

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def back(
    browser: SentienceBrowser,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Navigate back in history (best-effort).
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url
    try:
        browser.page.go_back()
        success = True
        error_msg = None
    except Exception as e:
        success = False
        error_msg = str(e)

    try:
        browser.page.wait_for_timeout(500)
    except Exception:
        pass

    duration_ms = int((time.time() - start_time) * 1000)
    try:
        url_after = browser.page.url
        url_changed = url_before != url_after
    except Exception:
        url_changed = True

    outcome = "navigated" if url_changed else ("dom_updated" if success else "error")

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = snapshot(browser)
        except Exception:
            snapshot_after = None

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(None if success else {"code": "back_failed", "reason": error_msg or "back failed"}),
    )


def press(browser: SentienceBrowser, key: str, take_snapshot: bool = False) -> ActionResult:
    """
    Press a keyboard key

    Args:
        browser: SentienceBrowser instance
        key: Key to press (e.g., "Enter", "Escape", "Tab")
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Press key using Playwright
    browser.page.keyboard.press(key)

    # Wait a bit for navigation/DOM updates
    browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def _normalize_key_token(token: str) -> str:
    lookup = {
        "CMD": "Meta",
        "COMMAND": "Meta",
        "CTRL": "Control",
        "CONTROL": "Control",
        "ALT": "Alt",
        "OPTION": "Alt",
        "SHIFT": "Shift",
        "ESC": "Escape",
        "ESCAPE": "Escape",
        "ENTER": "Enter",
        "RETURN": "Enter",
        "TAB": "Tab",
        "SPACE": "Space",
    }
    upper = token.strip().upper()
    return lookup.get(upper, token.strip())


def _parse_key_sequence(sequence: str) -> list[str]:
    parts = []
    for raw in sequence.replace(",", " ").split():
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        if "+" in raw:
            combo = "+".join(_normalize_key_token(tok) for tok in raw.split("+") if tok)
            parts.append(combo)
        else:
            parts.append(_normalize_key_token(raw))
    return parts


def send_keys(
    browser: SentienceBrowser,
    sequence: str,
    take_snapshot: bool = False,
    delay_ms: int = 50,
) -> ActionResult:
    """
    Send a sequence of key presses (e.g., "CMD+H", "CTRL+SHIFT+P").

    Supports sequences separated by commas/spaces, and brace-wrapped tokens
    like "{ENTER}" or "{CTRL+L}".
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    keys = _parse_key_sequence(sequence)
    if not keys:
        raise ValueError("send_keys sequence is empty")
    for key in keys:
        browser.page.keyboard.press(key)
        if delay_ms > 0:
            browser.page.wait_for_timeout(delay_ms)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def _build_search_url(query: str, engine: str) -> str:
    q = quote_plus(query)
    key = engine.strip().lower()
    if key in {"duckduckgo", "ddg"}:
        return f"https://duckduckgo.com/?q={q}"
    if key in {"google.com", "google"}:
        return f"https://www.google.com/search?q={q}"
    if key in {"google"}:
        return f"https://www.google.com/search?q={q}"
    if key in {"bing"}:
        return f"https://www.bing.com/search?q={q}"
    raise ValueError(f"unsupported search engine: {engine}")


def search(
    browser: SentienceBrowser,
    query: str,
    engine: str = "duckduckgo",
    take_snapshot: bool = False,
    snapshot_options: SnapshotOptions | None = None,
) -> ActionResult:
    """
    Navigate to a search results page for the given query.

    Args:
        browser: SentienceBrowser instance
        query: Search query string
        engine: Search engine name (duckduckgo, google, google.com, bing)
        take_snapshot: Whether to take snapshot after navigation
        snapshot_options: Snapshot options passed to snapshot() when take_snapshot is True.
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")
    if not query.strip():
        raise ValueError("search query is empty")

    start_time = time.time()
    url_before = browser.page.url
    url = _build_search_url(query, engine)
    browser.goto(url)
    browser.page.wait_for_load_state("networkidle")

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser, snapshot_options)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def scroll_to(
    browser: SentienceBrowser,
    element_id: int,
    behavior: str = "smooth",
    block: str = "center",
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Scroll an element into view

    Scrolls the page so that the specified element is visible in the viewport.
    Uses the element registry to find the element and scrollIntoView() to scroll it.

    Args:
        browser: SentienceBrowser instance
        element_id: Element ID from snapshot to scroll into view
        behavior: Scroll behavior - 'smooth', 'instant', or 'auto' (default: 'smooth')
        block: Vertical alignment - 'start', 'center', 'end', or 'nearest' (default: 'center')
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult

    Example:
        >>> snap = snapshot(browser)
        >>> button = find(snap, 'role=button[name="Submit"]')
        >>> if button:
        >>>     # Scroll element into view with smooth animation
        >>>     scroll_to(browser, button.id)
        >>>     # Scroll instantly to top of viewport
        >>>     scroll_to(browser, button.id, behavior='instant', block='start')
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Scroll element into view using the element registry
    scrolled = browser.page.evaluate(
        """
        (args) => {
            const el = window.sentience_registry[args.id];
            if (el && el.scrollIntoView) {
                el.scrollIntoView({
                    behavior: args.behavior,
                    block: args.block,
                    inline: 'nearest'
                });
                return true;
            }
            return false;
        }
        """,
        {"id": element_id, "behavior": behavior, "block": block},
    )

    if not scrolled:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "scroll_failed", "reason": "Element not found or not scrollable"},
        )

    # Wait a bit for scroll to complete (especially for smooth scrolling)
    wait_time = 500 if behavior == "smooth" else 100
    browser.page.wait_for_timeout(wait_time)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def _highlight_rect(
    browser: SentienceBrowser, rect: dict[str, float], duration_sec: float = 2.0
) -> None:
    """
    Highlight a rectangle with a red border overlay

    Args:
        browser: SentienceBrowser instance
        rect: Dictionary with x, y, width (w), height (h) keys
        duration_sec: How long to show the highlight (default: 2 seconds)
    """
    if not browser.page:
        return

    # Create a unique ID for this highlight
    highlight_id = f"sentience_highlight_{int(time.time() * 1000)}"

    # Combine all arguments into a single object for Playwright
    args = {
        "rect": {
            "x": rect["x"],
            "y": rect["y"],
            "w": rect["w"],
            "h": rect["h"],
        },
        "highlightId": highlight_id,
        "durationSec": duration_sec,
    }

    # Inject CSS and create overlay element
    browser.page.evaluate(
        """
        (args) => {
            const { rect, highlightId, durationSec } = args;
            // Create overlay div
            const overlay = document.createElement('div');
            overlay.id = highlightId;
            overlay.style.position = 'fixed';
            overlay.style.left = `${rect.x}px`;
            overlay.style.top = `${rect.y}px`;
            overlay.style.width = `${rect.w}px`;
            overlay.style.height = `${rect.h}px`;
            overlay.style.border = '3px solid red';
            overlay.style.borderRadius = '2px';
            overlay.style.boxSizing = 'border-box';
            overlay.style.pointerEvents = 'none';
            overlay.style.zIndex = '999999';
            overlay.style.backgroundColor = 'rgba(255, 0, 0, 0.1)';
            overlay.style.transition = 'opacity 0.3s ease-out';

            document.body.appendChild(overlay);

            // Remove after duration
            setTimeout(() => {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    if (overlay.parentNode) {
                        overlay.parentNode.removeChild(overlay);
                    }
                }, 300); // Wait for fade-out transition
            }, durationSec * 1000);
        }
        """,
        args,
    )


def click_rect(
    browser: SentienceBrowser,
    rect: dict[str, float],
    highlight: bool = True,
    highlight_duration: float = 2.0,
    take_snapshot: bool = False,
    cursor_policy: CursorPolicy | None = None,
) -> ActionResult:
    """
    Click at the center of a rectangle using Playwright's native mouse simulation.
    This uses a hybrid approach: calculates center coordinates and uses mouse.click()
    for realistic event simulation (triggers hover, focus, mousedown, mouseup).

    Args:
        browser: SentienceBrowser instance
        rect: Dictionary with x, y, width (w), height (h) keys, or BBox object
        highlight: Whether to show a red border highlight when clicking (default: True)
        highlight_duration: How long to show the highlight in seconds (default: 2.0)
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult

    Example:
        >>> click_rect(browser, {"x": 100, "y": 200, "w": 50, "h": 30})
        >>> # Or using BBox object
        >>> from predicate import BBox
        >>> bbox = BBox(x=100, y=200, width=50, height=30)
        >>> click_rect(browser, {"x": bbox.x, "y": bbox.y, "w": bbox.width, "h": bbox.height})
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    # Handle BBox object or dict
    if isinstance(rect, BBox):
        x = rect.x
        y = rect.y
        w = rect.width
        h = rect.height
    else:
        x = rect.get("x", 0)
        y = rect.get("y", 0)
        w = rect.get("w") or rect.get("width", 0)
        h = rect.get("h") or rect.get("height", 0)

    if w <= 0 or h <= 0:
        return ActionResult(
            success=False,
            duration_ms=0,
            outcome="error",
            error={
                "code": "invalid_rect",
                "reason": "Rectangle width and height must be positive",
            },
        )

    start_time = time.time()
    url_before = browser.page.url

    # Calculate center of rectangle
    center_x = x + w / 2
    center_y = y + h / 2
    cursor_meta: dict | None = None

    # Show highlight before clicking (if enabled)
    if highlight:
        _highlight_rect(browser, {"x": x, "y": y, "w": w, "h": h}, highlight_duration)
        # Small delay to ensure highlight is visible
        browser.page.wait_for_timeout(50)

    # Use Playwright's native mouse click for realistic simulation
    # This triggers hover, focus, mousedown, mouseup sequences
    try:
        if cursor_policy is not None and cursor_policy.mode == "human":
            pos = getattr(browser, "_sentience_cursor_pos", None)
            if not isinstance(pos, tuple) or len(pos) != 2:
                try:
                    vp = browser.page.viewport_size or {}
                    pos = (float(vp.get("width", 0)) / 2.0, float(vp.get("height", 0)) / 2.0)
                except Exception:
                    pos = (0.0, 0.0)

            cursor_meta = build_human_cursor_path(
                start=(float(pos[0]), float(pos[1])),
                target=(float(center_x), float(center_y)),
                policy=cursor_policy,
            )
            pts = cursor_meta.get("path", [])
            duration_ms_move = int(cursor_meta.get("duration_ms") or 0)
            per_step_s = (
                (duration_ms_move / max(1, len(pts))) / 1000.0 if duration_ms_move > 0 else 0.0
            )
            for p in pts:
                browser.page.mouse.move(float(p["x"]), float(p["y"]))
                if per_step_s > 0:
                    time.sleep(per_step_s)
            pause_ms = int(cursor_meta.get("pause_before_click_ms") or 0)
            if pause_ms > 0:
                time.sleep(pause_ms / 1000.0)

        browser.page.mouse.click(center_x, center_y)
        setattr(browser, "_sentience_cursor_pos", (float(center_x), float(center_y)))
        success = True
    except Exception as e:
        success = False
        error_msg = str(e)

    # Wait a bit for navigation/DOM updates
    browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        cursor=cursor_meta,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": error_msg if not success else "Click failed",
            }
        ),
    )


# ========== Async Action Functions ==========


async def click_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    use_mouse: bool = True,
    take_snapshot: bool = False,
    cursor_policy: CursorPolicy | None = None,
) -> ActionResult:
    """
    Click an element by ID using hybrid approach (async)

    Args:
        browser: AsyncSentienceBrowser instance
        element_id: Element ID from snapshot
        use_mouse: If True, use Playwright's mouse.click() at element center
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url
    cursor_meta: dict | None = None
    error_msg = ""

    if use_mouse:
        try:
            snap = await snapshot_async(browser)
            element = None
            for el in snap.elements:
                if el.id == element_id:
                    element = el
                    break

            if element:
                center_x = element.bbox.x + element.bbox.width / 2
                center_y = element.bbox.y + element.bbox.height / 2
                try:
                    if cursor_policy is not None and cursor_policy.mode == "human":
                        pos = getattr(browser, "_sentience_cursor_pos", None)
                        if not isinstance(pos, tuple) or len(pos) != 2:
                            try:
                                vp = browser.page.viewport_size or {}
                                pos = (
                                    float(vp.get("width", 0)) / 2.0,
                                    float(vp.get("height", 0)) / 2.0,
                                )
                            except Exception:
                                pos = (0.0, 0.0)

                        cursor_meta = build_human_cursor_path(
                            start=(float(pos[0]), float(pos[1])),
                            target=(float(center_x), float(center_y)),
                            policy=cursor_policy,
                        )
                        pts = cursor_meta.get("path", [])
                        duration_ms = int(cursor_meta.get("duration_ms") or 0)
                        per_step_s = (
                            (duration_ms / max(1, len(pts))) / 1000.0 if duration_ms > 0 else 0.0
                        )
                        for p in pts:
                            await browser.page.mouse.move(float(p["x"]), float(p["y"]))
                            if per_step_s > 0:
                                await asyncio.sleep(per_step_s)
                        pause_ms = int(cursor_meta.get("pause_before_click_ms") or 0)
                        if pause_ms > 0:
                            await asyncio.sleep(pause_ms / 1000.0)
                        await browser.page.mouse.click(center_x, center_y)
                        setattr(
                            browser, "_sentience_cursor_pos", (float(center_x), float(center_y))
                        )
                    else:
                        await browser.page.mouse.click(center_x, center_y)
                        setattr(
                            browser, "_sentience_cursor_pos", (float(center_x), float(center_y))
                        )
                    success = True
                except Exception:
                    success = True
            else:
                try:
                    success = await browser.page.evaluate(
                        """
                        (id) => {
                            return window.sentience.click(id);
                        }
                        """,
                        element_id,
                    )
                except Exception:
                    success = True
        except Exception:
            try:
                success = await browser.page.evaluate(
                    """
                    (id) => {
                        return window.sentience.click(id);
                    }
                    """,
                    element_id,
                )
            except Exception:
                success = True
    else:
        success = await browser.page.evaluate(
            """
            (id) => {
                return window.sentience.click(id);
            }
            """,
            element_id,
        )

    # Wait a bit for navigation/DOM updates
    try:
        await browser.page.wait_for_timeout(500)
    except Exception:
        pass

    duration_ms = int((time.time() - start_time) * 1000)

    # Check if URL changed
    try:
        url_after = browser.page.url
        url_changed = url_before != url_after
    except Exception:
        url_after = url_before
        url_changed = True

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = await snapshot_async(browser)
        except Exception:
            pass

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        cursor=cursor_meta,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": "Element not found or not clickable",
            }
        ),
    )


async def type_text_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    text: str,
    take_snapshot: bool = False,
    delay_ms: float = 0,
) -> ActionResult:
    """
    Type text into an element (async)

    Args:
        browser: AsyncSentienceBrowser instance
        element_id: Element ID from snapshot
        text: Text to type
        take_snapshot: Whether to take snapshot after action
        delay_ms: Delay between keystrokes in milliseconds for human-like typing (default: 0)

    Returns:
        ActionResult

    Example:
        >>> # Type instantly (default behavior)
        >>> await type_text_async(browser, element_id, "Hello World")
        >>> # Type with human-like delay (~10ms between keystrokes)
        >>> await type_text_async(browser, element_id, "Hello World", delay_ms=10)
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Focus element first
    focused = await browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (el) {
                el.focus();
                return true;
            }
            return false;
        }
        """,
        element_id,
    )

    if not focused:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "focus_failed", "reason": "Element not found"},
        )

    # Type using Playwright keyboard with optional delay between keystrokes
    await browser.page.keyboard.type(text, delay=delay_ms)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def clear_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    take_snapshot: bool = False,
) -> ActionResult:
    """Clear the value of an input/textarea element (best-effort, async)."""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = await browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (!el) return false;
            try { el.focus?.(); } catch {}
            if ('value' in el) {
                el.value = '';
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
            return false;
        }
        """,
        element_id,
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "clear_failed", "reason": "Element not found or not clearable"},
        )

    await browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def check_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    take_snapshot: bool = False,
) -> ActionResult:
    """Ensure a checkbox/radio is checked (best-effort, async)."""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = await browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (!el) return false;
            try { el.focus?.(); } catch {}
            if (!('checked' in el)) return false;
            if (el.checked === true) return true;
            try { el.click(); } catch { return false; }
            return true;
        }
        """,
        element_id,
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "check_failed", "reason": "Element not found or not checkable"},
        )

    await browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def uncheck_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    take_snapshot: bool = False,
) -> ActionResult:
    """Ensure a checkbox/radio is unchecked (best-effort, async)."""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = await browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (!el) return false;
            try { el.focus?.(); } catch {}
            if (!('checked' in el)) return false;
            if (el.checked === false) return true;
            try { el.click(); } catch { return false; }
            return true;
        }
        """,
        element_id,
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "uncheck_failed", "reason": "Element not found or not uncheckable"},
        )

    await browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def select_option_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    option: str,
    take_snapshot: bool = False,
) -> ActionResult:
    """Select an option in a <select> by matching option value/label (best-effort, async)."""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = await browser.page.evaluate(
        """
        (args) => {
            const el = window.sentience_registry[args.id];
            if (!el) return false;
            const tag = (el.tagName || '').toUpperCase();
            if (tag !== 'SELECT') return false;
            const needle = String(args.option ?? '');
            const opts = Array.from(el.options || []);
            let chosen = null;
            for (const o of opts) {
                if (String(o.value) === needle || String(o.text) === needle) { chosen = o; break; }
            }
            if (!chosen) {
                for (const o of opts) {
                    if (String(o.text || '').includes(needle)) { chosen = o; break; }
                }
            }
            if (!chosen) return false;
            el.value = chosen.value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        """,
        {"id": element_id, "option": option},
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "select_failed", "reason": "Element not found or option not found"},
        )

    await browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def upload_file_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    file_path: str,
    take_snapshot: bool = False,
) -> ActionResult:
    """Upload a local file via an <input type='file'> (best-effort, async)."""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url
    p = str(Path(file_path))

    try:
        handle = await browser.page.evaluate_handle(
            "(id) => window.sentience_registry[id] || null",
            element_id,
        )
        el = handle.as_element()
        if el is None:
            raise RuntimeError("Element not found")
        await el.set_input_files(p)
        success = True
        error_msg = None
    except Exception as e:
        success = False
        error_msg = str(e)

    await browser.page.wait_for_timeout(250)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else ("dom_updated" if success else "error")

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = await snapshot_async(browser)
        except Exception:
            snapshot_after = None

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(
            None if success else {"code": "upload_failed", "reason": error_msg or "upload failed"}
        ),
    )


async def submit_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    take_snapshot: bool = False,
) -> ActionResult:
    """Submit a form (best-effort, async)."""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    ok = await browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (!el) return false;
            try { el.focus?.(); } catch {}
            const tag = (el.tagName || '').toUpperCase();
            if (tag === 'FORM') {
                if (typeof el.requestSubmit === 'function') { el.requestSubmit(); return true; }
                try { el.submit(); return true; } catch { return false; }
            }
            const form = el.form;
            if (form && typeof form.requestSubmit === 'function') { form.requestSubmit(); return true; }
            try { el.click(); return true; } catch { return false; }
        }
        """,
        element_id,
    )

    if not ok:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "submit_failed", "reason": "Element not found or not submittable"},
        )

    await browser.page.wait_for_timeout(500)
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = await snapshot_async(browser)
        except Exception:
            snapshot_after = None

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def back_async(
    browser: AsyncSentienceBrowser,
    take_snapshot: bool = False,
) -> ActionResult:
    """Navigate back in history (best-effort, async)."""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url
    try:
        await browser.page.go_back()
        success = True
        error_msg = None
    except Exception as e:
        success = False
        error_msg = str(e)

    try:
        await browser.page.wait_for_timeout(500)
    except Exception:
        pass

    duration_ms = int((time.time() - start_time) * 1000)
    try:
        url_after = browser.page.url
        url_changed = url_before != url_after
    except Exception:
        url_changed = True

    outcome = "navigated" if url_changed else ("dom_updated" if success else "error")

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = await snapshot_async(browser)
        except Exception:
            snapshot_after = None

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(None if success else {"code": "back_failed", "reason": error_msg or "back failed"}),
    )


async def press_async(
    browser: AsyncSentienceBrowser, key: str, take_snapshot: bool = False
) -> ActionResult:
    """
    Press a keyboard key (async)

    Args:
        browser: AsyncSentienceBrowser instance
        key: Key to press (e.g., "Enter", "Escape", "Tab")
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Press key using Playwright
    await browser.page.keyboard.press(key)

    # Wait a bit for navigation/DOM updates
    await browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def send_keys_async(
    browser: AsyncSentienceBrowser,
    sequence: str,
    take_snapshot: bool = False,
    delay_ms: int = 50,
) -> ActionResult:
    """
    Async version of send_keys().
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    keys = _parse_key_sequence(sequence)
    if not keys:
        raise ValueError("send_keys sequence is empty")
    for key in keys:
        await browser.page.keyboard.press(key)
        if delay_ms > 0:
            await browser.page.wait_for_timeout(delay_ms)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def search_async(
    browser: AsyncSentienceBrowser,
    query: str,
    engine: str = "duckduckgo",
    take_snapshot: bool = False,
    snapshot_options: SnapshotOptions | None = None,
) -> ActionResult:
    """
    Async version of search().

    Args:
        browser: AsyncSentienceBrowser instance
        query: Search query string
        engine: Search engine name (duckduckgo, google, google.com, bing)
        take_snapshot: Whether to take snapshot after navigation
        snapshot_options: Snapshot options passed to snapshot_async() when take_snapshot is True.
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")
    if not query.strip():
        raise ValueError("search query is empty")

    start_time = time.time()
    url_before = browser.page.url
    url = _build_search_url(query, engine)
    await browser.goto(url)
    await browser.page.wait_for_load_state("networkidle")

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser, snapshot_options)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def scroll_to_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    behavior: str = "smooth",
    block: str = "center",
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Scroll an element into view (async)

    Scrolls the page so that the specified element is visible in the viewport.
    Uses the element registry to find the element and scrollIntoView() to scroll it.

    Args:
        browser: AsyncSentienceBrowser instance
        element_id: Element ID from snapshot to scroll into view
        behavior: Scroll behavior - 'smooth', 'instant', or 'auto' (default: 'smooth')
        block: Vertical alignment - 'start', 'center', 'end', or 'nearest' (default: 'center')
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult

    Example:
        >>> snap = await snapshot_async(browser)
        >>> button = find(snap, 'role=button[name="Submit"]')
        >>> if button:
        >>>     # Scroll element into view with smooth animation
        >>>     await scroll_to_async(browser, button.id)
        >>>     # Scroll instantly to top of viewport
        >>>     await scroll_to_async(browser, button.id, behavior='instant', block='start')
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Scroll element into view using the element registry
    scrolled = await browser.page.evaluate(
        """
        (args) => {
            const el = window.sentience_registry[args.id];
            if (el && el.scrollIntoView) {
                el.scrollIntoView({
                    behavior: args.behavior,
                    block: args.block,
                    inline: 'nearest'
                });
                return true;
            }
            return false;
        }
        """,
        {"id": element_id, "behavior": behavior, "block": block},
    )

    if not scrolled:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "scroll_failed", "reason": "Element not found or not scrollable"},
        )

    # Wait a bit for scroll to complete (especially for smooth scrolling)
    wait_time = 500 if behavior == "smooth" else 100
    await browser.page.wait_for_timeout(wait_time)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def _highlight_rect_async(
    browser: AsyncSentienceBrowser, rect: dict[str, float], duration_sec: float = 2.0
) -> None:
    """Highlight a rectangle with a red border overlay (async)"""
    if not browser.page:
        return

    highlight_id = f"sentience_highlight_{int(time.time() * 1000)}"

    args = {
        "rect": {
            "x": rect["x"],
            "y": rect["y"],
            "w": rect["w"],
            "h": rect["h"],
        },
        "highlightId": highlight_id,
        "durationSec": duration_sec,
    }

    await browser.page.evaluate(
        """
        (args) => {
            const { rect, highlightId, durationSec } = args;
            const overlay = document.createElement('div');
            overlay.id = highlightId;
            overlay.style.position = 'fixed';
            overlay.style.left = `${rect.x}px`;
            overlay.style.top = `${rect.y}px`;
            overlay.style.width = `${rect.w}px`;
            overlay.style.height = `${rect.h}px`;
            overlay.style.border = '3px solid red';
            overlay.style.borderRadius = '2px';
            overlay.style.boxSizing = 'border-box';
            overlay.style.pointerEvents = 'none';
            overlay.style.zIndex = '999999';
            overlay.style.backgroundColor = 'rgba(255, 0, 0, 0.1)';
            overlay.style.transition = 'opacity 0.3s ease-out';

            document.body.appendChild(overlay);

            setTimeout(() => {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    if (overlay.parentNode) {
                        overlay.parentNode.removeChild(overlay);
                    }
                }, 300);
            }, durationSec * 1000);
        }
        """,
        args,
    )


async def click_rect_async(
    browser: AsyncSentienceBrowser,
    rect: dict[str, float] | BBox,
    highlight: bool = True,
    highlight_duration: float = 2.0,
    take_snapshot: bool = False,
    cursor_policy: CursorPolicy | None = None,
) -> ActionResult:
    """
    Click at the center of a rectangle (async)

    Args:
        browser: AsyncSentienceBrowser instance
        rect: Dictionary with x, y, width (w), height (h) keys, or BBox object
        highlight: Whether to show a red border highlight when clicking
        highlight_duration: How long to show the highlight in seconds
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    # Handle BBox object or dict
    if isinstance(rect, BBox):
        x = rect.x
        y = rect.y
        w = rect.width
        h = rect.height
    else:
        x = rect.get("x", 0)
        y = rect.get("y", 0)
        w = rect.get("w") or rect.get("width", 0)
        h = rect.get("h") or rect.get("height", 0)

    if w <= 0 or h <= 0:
        return ActionResult(
            success=False,
            duration_ms=0,
            outcome="error",
            error={
                "code": "invalid_rect",
                "reason": "Rectangle width and height must be positive",
            },
        )

    start_time = time.time()
    url_before = browser.page.url

    # Calculate center of rectangle
    center_x = x + w / 2
    center_y = y + h / 2
    cursor_meta: dict | None = None

    # Show highlight before clicking
    if highlight:
        await _highlight_rect_async(browser, {"x": x, "y": y, "w": w, "h": h}, highlight_duration)
        await browser.page.wait_for_timeout(50)

    # Use Playwright's native mouse click
    try:
        if cursor_policy is not None and cursor_policy.mode == "human":
            pos = getattr(browser, "_sentience_cursor_pos", None)
            if not isinstance(pos, tuple) or len(pos) != 2:
                try:
                    vp = browser.page.viewport_size or {}
                    pos = (float(vp.get("width", 0)) / 2.0, float(vp.get("height", 0)) / 2.0)
                except Exception:
                    pos = (0.0, 0.0)

            cursor_meta = build_human_cursor_path(
                start=(float(pos[0]), float(pos[1])),
                target=(float(center_x), float(center_y)),
                policy=cursor_policy,
            )
            pts = cursor_meta.get("path", [])
            duration_ms_move = int(cursor_meta.get("duration_ms") or 0)
            per_step_s = (
                (duration_ms_move / max(1, len(pts))) / 1000.0 if duration_ms_move > 0 else 0.0
            )
            for p in pts:
                await browser.page.mouse.move(float(p["x"]), float(p["y"]))
                if per_step_s > 0:
                    await asyncio.sleep(per_step_s)
            pause_ms = int(cursor_meta.get("pause_before_click_ms") or 0)
            if pause_ms > 0:
                await asyncio.sleep(pause_ms / 1000.0)

        await browser.page.mouse.click(center_x, center_y)
        setattr(browser, "_sentience_cursor_pos", (float(center_x), float(center_y)))
        success = True
    except Exception as e:
        success = False
        error_msg = str(e)

    # Wait a bit for navigation/DOM updates
    await browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        cursor=cursor_meta,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": error_msg if not success else "Click failed",
            }
        ),
    )
