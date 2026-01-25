"""
Debug helper: investigate empty `read_async()` results.

This script is meant to reproduce situations where the extension-backed `read_async()`
returns `status="success"` but `content` is empty / near-empty (e.g. length=1).

It prints the final `ReadResult` for:
- a stable control page (example.com)
- an AceHardware product details page (often triggers the empty-read symptom)

Tip:
  SENTIENCE_DEBUG_READ=1 python sdk-python/examples/debug_read_async_empty_content.py
"""

import asyncio
import os

from sentience.async_api import AsyncSentienceBrowser, read_async


ACE_PDP_URL = "https://www.acehardware.com/departments/tools/power-tools/combo-power-tool-sets/2026525"


async def dump_read(browser: AsyncSentienceBrowser, url: str) -> None:
    print(f"\n=== URL: {url} ===")
    await browser.goto(url, wait_until="domcontentloaded")

    res_md = await read_async(browser, output_format="markdown", enhance_markdown=True)
    print(
        f"[markdown] status={res_md.status!r} length={res_md.length} url={res_md.url!r} error={res_md.error!r}"
    )
    print(res_md.content[:400].strip() or "<empty>")

    res_raw = await read_async(browser, output_format="raw")
    print(
        f"[raw]     status={res_raw.status!r} length={res_raw.length} url={res_raw.url!r} error={res_raw.error!r}"
    )
    print(res_raw.content[:200].strip() or "<empty>")


async def main() -> None:
    api_key = os.environ.get("SENTIENCE_API_KEY")
    headless = os.environ.get("HEADLESS", "1").strip() not in {"0", "false", "False"}

    async with AsyncSentienceBrowser(api_key=api_key, headless=headless) as browser:
        await dump_read(browser, "https://example.com")
        await dump_read(browser, ACE_PDP_URL)


if __name__ == "__main__":
    asyncio.run(main())

