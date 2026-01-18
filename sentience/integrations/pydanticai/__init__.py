"""
PydanticAI integration helpers (optional).

This module does NOT import `pydantic_ai` at import time so the base SDK can be
installed without the optional dependency. Users should install:

    pip install sentienceapi[pydanticai]

and then use `register_sentience_tools(...)` with a PydanticAI `Agent`.
"""

from .deps import SentiencePydanticDeps
from .toolset import register_sentience_tools

__all__ = ["SentiencePydanticDeps", "register_sentience_tools"]
