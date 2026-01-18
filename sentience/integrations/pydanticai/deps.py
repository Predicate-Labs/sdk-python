from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sentience.browser import AsyncSentienceBrowser
from sentience.tracing import Tracer


@dataclass
class SentiencePydanticDeps:
    """
    Dependencies passed into PydanticAI tools via ctx.deps.

    At minimum we carry the live `AsyncSentienceBrowser`.
    """

    browser: AsyncSentienceBrowser
    runtime: Any | None = None
    tracer: Tracer | None = None
