"""
Browser-related utilities for Sentience SDK.

Provides functions for managing browser storage state (cookies, localStorage).
"""

import json
from pathlib import Path

from playwright.sync_api import BrowserContext


def save_storage_state(context: BrowserContext, file_path: str | Path) -> None:
    """
    Save current browser storage state (cookies + localStorage) to a file.

    This is useful for capturing a logged-in session to reuse later.

    Args:
        context: Playwright BrowserContext
        file_path: Path to save the storage state JSON file

    Example:
        ```python
        from predicate import SentienceBrowser, save_storage_state

        browser = SentienceBrowser()
        browser.start()

        # User logs in manually or via agent
        browser.goto("https://example.com")
        # ... login happens ...

        # Save session for later
        save_storage_state(browser.context, "auth.json")
        ```

    Raises:
        IOError: If file cannot be written
    """
    storage_state = context.storage_state()
    file_path_obj = Path(file_path)
    file_path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path_obj, "w") as f:
        json.dump(storage_state, f, indent=2)
    print(f"✅ [Sentience] Saved storage state to {file_path_obj}")
