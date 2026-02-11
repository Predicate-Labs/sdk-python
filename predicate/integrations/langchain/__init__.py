"""
LangChain / LangGraph integration helpers (optional).

This package is designed so the base SDK can be imported without LangChain installed.
All LangChain imports are done lazily inside tool-builder functions.
"""

from .context import SentienceLangChainContext
from .core import SentienceLangChainCore
from .tools import build_sentience_langchain_tools

__all__ = ["SentienceLangChainContext", "SentienceLangChainCore", "build_sentience_langchain_tools"]
