"""
Digest utilities for snapshot canonicalization and hashing.

Provides functions to compute stable digests of snapshots for determinism diff.
Two digest strategies:
- strict: includes structure + normalized text
- loose: structure only (no text) - detects layout changes vs content changes
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


@dataclass
class BBox:
    """Bounding box with normalized coordinates."""

    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_dict(cls, bbox_dict: dict[str, Any]) -> "BBox":
        """Create BBox from dictionary."""
        return cls(
            x=int(bbox_dict.get("x", 0)),
            y=int(bbox_dict.get("y", 0)),
            width=int(bbox_dict.get("width", 0)),
            height=int(bbox_dict.get("height", 0)),
        )

    def to_normalized(self, bucket_size: int = 2) -> list[int]:
        """
        Normalize bbox to fixed-size buckets to ignore minor jitter.

        Args:
            bucket_size: Pixel bucket size (default 2px)

        Returns:
            List of [x, y, width, height] rounded to buckets
        """
        return [
            round(self.x / bucket_size) * bucket_size,
            round(self.y / bucket_size) * bucket_size,
            round(self.width / bucket_size) * bucket_size,
            round(self.height / bucket_size) * bucket_size,
        ]


@dataclass
class ElementFingerprint:
    """Normalized element data for digest computation."""

    id: int
    role: str
    bbox: list[int]  # Normalized
    clickable: int  # 0 or 1
    primary: int  # 0 or 1
    text: str = ""  # Empty for loose digest

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            "id": self.id,
            "role": self.role,
            "bbox": self.bbox,
            "clickable": self.clickable,
            "primary": self.primary,
        }
        if self.text:  # Only include text if non-empty
            data["text"] = self.text
        return data


def normalize_text_strict(text: str | None, max_length: int = 80) -> str:
    """
    Normalize text for strict digest (structure + content).

    Rules:
    - Lowercase
    - Trim and collapse whitespace
    - Cap length at max_length
    - Replace digit runs with '#'
    - Normalize currency: $79.99 -> $#
    - Normalize time patterns: 12:34 -> #:#

    Args:
        text: Input text
        max_length: Maximum text length (default 80)

    Returns:
        Normalized text string
    """
    if not text:
        return ""

    # Lowercase and trim
    text = text.strip().lower()

    # Collapse whitespace
    text = " ".join(text.split())

    # Cap length
    text = text[:max_length]

    # Replace digit runs with #
    text = re.sub(r"\d+", "#", text)

    # Normalize currency
    text = re.sub(r"\$\s*#", "$#", text)

    # Normalize time patterns (HH:MM or similar)
    text = re.sub(r"#:#", "#:#", text)

    # Normalize date patterns (YYYY-MM-DD or similar)
    text = re.sub(r"#-#-#", "#-#-#", text)

    return text


def normalize_bbox(bbox: dict[str, Any] | BBox, bucket_size: int = 2) -> list[int]:
    """
    Round bbox to fixed-size buckets to ignore jitter.

    Args:
        bbox: BBox object or dict with x, y, width, height
        bucket_size: Pixel bucket size (default 2px)

    Returns:
        List of [x, y, width, height] rounded to buckets
    """
    if isinstance(bbox, BBox):
        return bbox.to_normalized(bucket_size)

    bbox_obj = BBox.from_dict(bbox)
    return bbox_obj.to_normalized(bucket_size)


def extract_element_fingerprint(
    element: dict[str, Any],
    include_text: bool = True,
) -> ElementFingerprint:
    """
    Extract normalized fingerprint from element dict.

    Args:
        element: Element dict from snapshot
        include_text: Whether to include normalized text (False for loose digest)

    Returns:
        ElementFingerprint with normalized data
    """
    # Extract basic fields
    element_id = element.get("id", 0)
    role = element.get("role", "unknown")

    # Extract and normalize bbox
    bbox_data = element.get("bbox", {})
    bbox_normalized = normalize_bbox(bbox_data)

    # Extract visual cues
    visual_cues = element.get("visual_cues", {})
    clickable = 1 if visual_cues.get("is_clickable", False) else 0
    primary = 1 if visual_cues.get("is_primary", False) else 0

    # Extract and normalize text (if requested)
    text = ""
    if include_text:
        raw_text = element.get("text", "")
        text = normalize_text_strict(raw_text)

    return ElementFingerprint(
        id=element_id,
        role=role,
        bbox=bbox_normalized,
        clickable=clickable,
        primary=primary,
        text=text,
    )


def canonical_snapshot_strict(elements: list[dict[str, Any]]) -> str:
    """
    Create strict snapshot digest (structure + normalized text).

    Args:
        elements: List of element dicts from snapshot

    Returns:
        Canonical JSON string for hashing
    """
    fingerprints = []

    for element in sorted(elements, key=lambda e: e.get("id", 0)):
        fingerprint = extract_element_fingerprint(element, include_text=True)
        fingerprints.append(fingerprint.to_dict())

    return json.dumps(fingerprints, sort_keys=True, ensure_ascii=False)


def canonical_snapshot_loose(elements: list[dict[str, Any]]) -> str:
    """
    Create loose snapshot digest (structure only, no text).

    This is more resistant to content churn (prices, ads, timestamps).
    Use for detecting structural changes vs content changes.

    Args:
        elements: List of element dicts from snapshot

    Returns:
        Canonical JSON string for hashing
    """
    fingerprints = []

    for element in sorted(elements, key=lambda e: e.get("id", 0)):
        fingerprint = extract_element_fingerprint(element, include_text=False)
        fingerprints.append(fingerprint.to_dict())

    return json.dumps(fingerprints, sort_keys=True, ensure_ascii=False)


def sha256_digest(canonical_str: str) -> str:
    """
    Compute SHA256 hash with 'sha256:' prefix.

    Args:
        canonical_str: Canonical string to hash

    Returns:
        Hash string with format: "sha256:<hex>"
    """
    hash_obj = hashlib.sha256(canonical_str.encode("utf-8"))
    return f"sha256:{hash_obj.hexdigest()}"


def compute_snapshot_digests(elements: list[dict[str, Any]]) -> dict[str, str]:
    """
    Compute both strict and loose digests for a snapshot.

    Args:
        elements: List of element dicts from snapshot

    Returns:
        Dict with 'strict' and 'loose' digest strings
    """
    canonical_strict = canonical_snapshot_strict(elements)
    canonical_loose = canonical_snapshot_loose(elements)

    return {
        "strict": sha256_digest(canonical_strict),
        "loose": sha256_digest(canonical_loose),
    }
