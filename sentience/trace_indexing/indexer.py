"""
Trace indexing for fast timeline rendering and step drill-down.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .index_schema import (
    TraceIndex,
    StepIndex,
    TraceSummary,
    TraceFileInfo,
    SnapshotInfo,
    ActionInfo,
    StepCounters,
)


def _normalize_text(text: str | None, max_len: int = 80) -> str:
    """Normalize text for digest: trim, collapse whitespace, lowercase, cap length."""
    if not text:
        return ""
    # Trim and collapse whitespace
    normalized = " ".join(text.split())
    # Lowercase
    normalized = normalized.lower()
    # Cap length
    if len(normalized) > max_len:
        normalized = normalized[:max_len]
    return normalized


def _round_bbox(bbox: Dict[str, float], precision: int = 2) -> Dict[str, int]:
    """Round bbox coordinates to reduce noise (default: 2px precision)."""
    return {
        "x": round(bbox.get("x", 0) / precision) * precision,
        "y": round(bbox.get("y", 0) / precision) * precision,
        "width": round(bbox.get("width", 0) / precision) * precision,
        "height": round(bbox.get("height", 0) / precision) * precision,
    }


def _compute_snapshot_digest(snapshot_data: Dict[str, Any]) -> str:
    """
    Compute stable digest of snapshot for diffing.

    Includes: url, viewport, canonicalized elements (id, role, text_norm, bbox_rounded).
    Excludes: importance, style fields, transient attributes.
    """
    url = snapshot_data.get("url", "")
    viewport = snapshot_data.get("viewport", {})
    elements = snapshot_data.get("elements", [])

    # Canonicalize elements
    canonical_elements = []
    for elem in elements:
        canonical_elem = {
            "id": elem.get("id"),
            "role": elem.get("role", ""),
            "text_norm": _normalize_text(elem.get("text")),
            "bbox": _round_bbox(
                elem.get("bbox", {"x": 0, "y": 0, "width": 0, "height": 0})
            ),
            "is_primary": elem.get("is_primary", False),
            "is_clickable": elem.get("is_clickable", False),
        }
        canonical_elements.append(canonical_elem)

    # Sort by element id for determinism
    canonical_elements.sort(key=lambda e: e.get("id", 0))

    # Build canonical object
    canonical = {
        "url": url,
        "viewport": {
            "width": viewport.get("width", 0),
            "height": viewport.get("height", 0),
        },
        "elements": canonical_elements,
    }

    # Hash
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _compute_action_digest(action_data: Dict[str, Any]) -> str:
    """
    Compute digest of action args for privacy + determinism.

    For TYPE: includes text_len + text_sha256 (not raw text)
    For CLICK/PRESS: includes only non-sensitive fields
    """
    action_type = action_data.get("type", "")
    target_id = action_data.get("target_element_id")

    canonical = {
        "type": action_type,
        "target_element_id": target_id,
    }

    # Type-specific canonicalization
    if action_type == "TYPE":
        text = action_data.get("text", "")
        canonical["text_len"] = len(text)
        canonical["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    elif action_type == "PRESS":
        canonical["key"] = action_data.get("key", "")
    # CLICK has no extra args

    # Hash
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _compute_file_sha256(file_path: str) -> str:
    """Compute SHA256 hash of entire file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def build_trace_index(trace_path: str) -> TraceIndex:
    """
    Build trace index from JSONL file in single streaming pass.

    Args:
        trace_path: Path to trace JSONL file

    Returns:
        Complete TraceIndex object
    """
    trace_path_obj = Path(trace_path)
    if not trace_path_obj.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    # Extract run_id from filename
    run_id = trace_path_obj.stem

    # Initialize summary
    first_ts = ""
    last_ts = ""
    event_count = 0
    error_count = 0
    final_url = None

    steps_by_id: Dict[str, StepIndex] = {}
    step_order: List[str] = []  # Track order of first appearance

    # Stream through file, tracking byte offsets
    with open(trace_path, "rb") as f:
        byte_offset = 0

        for line_bytes in f:
            line_len = len(line_bytes)

            try:
                event = json.loads(line_bytes.decode("utf-8"))
            except json.JSONDecodeError:
                # Skip malformed lines
                byte_offset += line_len
                continue

            # Extract event metadata
            event_type = event.get("type", "")
            ts = event.get("ts") or event.get("timestamp", "")
            step_id = event.get("step_id", "step-0")  # Default synthetic step
            data = event.get("data", {})

            # Update summary
            event_count += 1
            if not first_ts:
                first_ts = ts
            last_ts = ts

            if event_type == "error":
                error_count += 1

            # Initialize step if first time seeing this step_id
            if step_id not in steps_by_id:
                step_order.append(step_id)
                steps_by_id[step_id] = StepIndex(
                    step_index=len(step_order),
                    step_id=step_id,
                    goal=None,
                    status="partial",
                    ts_start=ts,
                    ts_end=ts,
                    offset_start=byte_offset,
                    offset_end=byte_offset + line_len,
                    url_before=None,
                    url_after=None,
                    snapshot_before=SnapshotInfo(),
                    snapshot_after=SnapshotInfo(),
                    action=ActionInfo(),
                    counters=StepCounters(),
                )

            step = steps_by_id[step_id]

            # Update step metadata
            step.ts_end = ts
            step.offset_end = byte_offset + line_len
            step.counters.events += 1

            # Handle specific event types
            if event_type == "step_start":
                step.goal = data.get("goal")
                step.url_before = data.get("pre_url")

            elif event_type == "snapshot":
                snapshot_id = data.get("snapshot_id")
                url = data.get("url")
                digest = _compute_snapshot_digest(data)

                # First snapshot = before, last snapshot = after
                if step.snapshot_before.snapshot_id is None:
                    step.snapshot_before = SnapshotInfo(
                        snapshot_id=snapshot_id, digest=digest, url=url
                    )
                    step.url_before = step.url_before or url

                step.snapshot_after = SnapshotInfo(
                    snapshot_id=snapshot_id, digest=digest, url=url
                )
                step.url_after = url
                step.counters.snapshots += 1
                final_url = url

            elif event_type == "action":
                step.action = ActionInfo(
                    type=data.get("type"),
                    target_element_id=data.get("target_element_id"),
                    args_digest=_compute_action_digest(data),
                    success=data.get("success", True),
                )
                step.counters.actions += 1

            elif event_type == "llm_response":
                step.counters.llm_calls += 1

            elif event_type == "error":
                step.status = "error"

            elif event_type == "step_end":
                if step.status != "error":
                    step.status = "ok"

            byte_offset += line_len

    # Build summary
    summary = TraceSummary(
        first_ts=first_ts,
        last_ts=last_ts,
        event_count=event_count,
        step_count=len(steps_by_id),
        error_count=error_count,
        final_url=final_url,
    )

    # Build steps list in order
    steps_list = [steps_by_id[sid] for sid in step_order]

    # Build trace file info
    trace_file = TraceFileInfo(
        path=str(trace_path),
        size_bytes=os.path.getsize(trace_path),
        sha256=_compute_file_sha256(str(trace_path)),
    )

    # Build final index
    index = TraceIndex(
        version=1,
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        trace_file=trace_file,
        summary=summary,
        steps=steps_list,
    )

    return index


def write_trace_index(trace_path: str, index_path: str | None = None) -> str:
    """
    Build index and write to file.

    Args:
        trace_path: Path to trace JSONL file
        index_path: Optional custom path for index file (default: trace_path with .index.json)

    Returns:
        Path to written index file
    """
    if index_path is None:
        index_path = str(Path(trace_path).with_suffix("")) + ".index.json"

    index = build_trace_index(trace_path)

    with open(index_path, "w") as f:
        json.dump(index.to_dict(), f, indent=2)

    return index_path


def read_step_events(
    trace_path: str, offset_start: int, offset_end: int
) -> List[Dict[str, Any]]:
    """
    Read events for a specific step using byte offsets from index.

    Args:
        trace_path: Path to trace JSONL file
        offset_start: Byte offset where step starts
        offset_end: Byte offset where step ends

    Returns:
        List of event dictionaries for the step
    """
    events = []

    with open(trace_path, "rb") as f:
        f.seek(offset_start)
        bytes_to_read = offset_end - offset_start
        chunk = f.read(bytes_to_read)

    # Parse lines
    for line_bytes in chunk.split(b"\n"):
        if not line_bytes:
            continue
        try:
            event = json.loads(line_bytes.decode("utf-8"))
            events.append(event)
        except json.JSONDecodeError:
            continue

    return events


# CLI entrypoint
def main():
    """CLI tool for building trace index."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m sentience.tracing.indexer <trace.jsonl>")
        sys.exit(1)

    trace_path = sys.argv[1]
    index_path = write_trace_index(trace_path)
    print(f"✅ Index written to: {index_path}")


if __name__ == "__main__":
    main()
