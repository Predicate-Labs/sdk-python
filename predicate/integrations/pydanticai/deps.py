from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from predicate.browser import AsyncSentienceBrowser
from predicate.tracing import Tracer


@dataclass
class SentiencePydanticDeps:
    """
    Dependencies passed into PydanticAI tools via ctx.deps.

    At minimum we carry the live `AsyncSentienceBrowser`.
    """

    browser: AsyncSentienceBrowser
    runtime: Any | None = None
    tracer: Tracer | None = None
