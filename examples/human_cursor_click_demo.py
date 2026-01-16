"""
Human-like cursor movement demo (Python SDK).

This example shows how to opt into human-like mouse movement before clicking,
and how to read the returned cursor metadata for tracing/debugging.
"""

from __future__ import annotations

from sentience import CursorPolicy, SentienceBrowser, click, find, snapshot


def main() -> None:
    # NOTE: This uses a real browser via Playwright.
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        link = find(snap, "role=link")
        if not link:
            raise RuntimeError("No link found on page")

        policy = CursorPolicy(
            mode="human",
            steps=18,  # more steps => smoother
            duration_ms=350,
            jitter_px=1.2,
            overshoot_px=6.0,
            pause_before_click_ms=30,
            seed=123,  # optional: makes motion deterministic for demos/tests
        )

        result = click(browser, link.id, use_mouse=True, cursor_policy=policy)
        print("clicked:", result.success, "outcome:", result.outcome)
        print("cursor meta:", result.cursor)


if __name__ == "__main__":
    main()
