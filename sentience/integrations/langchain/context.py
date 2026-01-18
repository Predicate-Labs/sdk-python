from __future__ import annotations

from dataclasses import dataclass

from sentience.browser import AsyncSentienceBrowser
from sentience.tracing import Tracer


@dataclass
class SentienceLangChainContext:
    """
    Context for LangChain/LangGraph integrations.

    We keep this small and explicit; it mirrors the PydanticAI deps object.
    """

    browser: AsyncSentienceBrowser
    tracer: Tracer | None = None
