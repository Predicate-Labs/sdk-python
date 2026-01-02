"""
Utility functions for Sentience SDK.

This module re-exports all utility functions from submodules for backward compatibility.
Users can continue using:
    from sentience.utils import compute_snapshot_digests, canonical_snapshot_strict
    from sentience import canonical_snapshot_strict, format_snapshot_for_llm
"""

# Re-export all functions from submodules for backward compatibility
from .browser import save_storage_state
from .element import (
    BBox,
    ElementFingerprint,
    canonical_snapshot_loose,
    canonical_snapshot_strict,
    compute_snapshot_digests,
    extract_element_fingerprint,
    normalize_bbox,
    normalize_text_strict,
    sha256_digest,
)
from .formatting import format_snapshot_for_llm

__all__ = [
    # Browser utilities
    "save_storage_state",
    # Element/digest utilities
    "BBox",
    "ElementFingerprint",
    "canonical_snapshot_loose",
    "canonical_snapshot_strict",
    "compute_snapshot_digests",
    "extract_element_fingerprint",
    "normalize_bbox",
    "normalize_text_strict",
    "sha256_digest",
    # Formatting utilities
    "format_snapshot_for_llm",
]

