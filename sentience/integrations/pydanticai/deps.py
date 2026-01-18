from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sentience.browser import AsyncSentienceBrowser


@dataclass
class SentiencePydanticDeps:
    """
    Dependencies passed into PydanticAI tools via ctx.deps.

    At minimum we carry the live `AsyncSentienceBrowser`.
    """

    browser: AsyncSentienceBrowser
    runtime: Any | None = None
    tracer: Any | None = None

