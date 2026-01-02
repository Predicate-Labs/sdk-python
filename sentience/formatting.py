"""
Snapshot formatting utilities for LLM prompts.

DEPRECATED: This module is maintained for backward compatibility only.
New code should import from sentience.utils.formatting or sentience directly:

    from sentience.utils.formatting import format_snapshot_for_llm
    # or
    from sentience import format_snapshot_for_llm
"""

# Re-export from new location for backward compatibility
from .utils.formatting import format_snapshot_for_llm

__all__ = ["format_snapshot_for_llm"]
