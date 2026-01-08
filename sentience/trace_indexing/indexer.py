"""
Trace indexing for fast timeline rendering and step drill-down.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..canonicalization import canonicalize_element
from .index_schema import (
    ActionInfo,
    SnapshotInfo,
    StepCounters,
    StepIndex,
    TraceFileInfo,
    TraceIndex,
    TraceSummary,
)


def _compute_snapshot_digest(snapshot_data: dict[str, Any]) -> str:
    """
    Compute stable digest of snapshot for diffing.

    Includes: url, viewport, canonicalized elements (id, role, text_norm, bbox_rounded).
    Excludes: importance, style fields, transient attributes.
    """
    url = snapshot_data.get("url", "")
    viewport = snapshot_data.get("viewport", {})
    elements = snapshot_data.get("elements", [])

    # Canonicalize elements using shared helper
    canonical_elements = [canonicalize_element(elem) for elem in elements]

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


def _compute_action_digest(action_data: dict[str, Any]) -> str:
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
    run_end_status = None  # Track status from run_end event
    agent_name = None  # Extract from run_start event
    line_count = 0  # Track total line count

    steps_by_id: dict[str, StepIndex] = {}
    step_order: list[str] = []  # Track order of first appearance

    # Stream through file, tracking byte offsets and line numbers
    with open(trace_path, "rb") as f:
        byte_offset = 0
        line_number = 0  # Track line number for each event

        for line_bytes in f:
            line_number += 1
            line_count += 1
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

            # Extract agent_name from run_start event
            if event_type == "run_start":
                agent_name = data.get("agent")

            # Initialize step if first time seeing this step_id
            if step_id not in steps_by_id:
                step_order.append(step_id)
                steps_by_id[step_id] = StepIndex(
                    step_index=len(step_order),
                    step_id=step_id,
                    goal=None,
                    status="failure",  # Default to failure (will be updated by step_end event)
                    ts_start=ts,
                    ts_end=ts,
                    offset_start=byte_offset,
                    offset_end=byte_offset + line_len,
                    line_number=line_number,  # Track line number
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
            step.line_number = line_number  # Update line number on each event
            step.counters.events += 1

            # Handle specific event types
            if event_type == "step_start":
                step.goal = data.get("goal")
                step.url_before = data.get("pre_url")

            elif event_type == "snapshot" or event_type == "snapshot_taken":
                # Handle both "snapshot" (current) and "snapshot_taken" (schema) for backward compatibility
                snapshot_id = data.get("snapshot_id")
                url = data.get("url")
                digest = _compute_snapshot_digest(data)

                # First snapshot = before, last snapshot = after
                if step.snapshot_before.snapshot_id is None:
                    step.snapshot_before = SnapshotInfo(
                        snapshot_id=snapshot_id, digest=digest, url=url
                    )
                    step.url_before = step.url_before or url

                step.snapshot_after = SnapshotInfo(snapshot_id=snapshot_id, digest=digest, url=url)
                step.url_after = url
                step.counters.snapshots += 1
                final_url = url

            elif event_type == "action" or event_type == "action_executed":
                # Handle both "action" (current) and "action_executed" (schema) for backward compatibility
                step.action = ActionInfo(
                    type=data.get("type"),
                    target_element_id=data.get("target_element_id"),
                    args_digest=_compute_action_digest(data),
                    success=data.get("success", True),
                )
                step.counters.actions += 1

            elif event_type == "llm_response" or event_type == "llm_called":
                # Handle both "llm_response" (current) and "llm_called" (schema) for backward compatibility
                step.counters.llm_calls += 1

            elif event_type == "error":
                step.status = "failure"

            elif event_type == "step_end":
                # Determine status from step_end event data
                # Frontend expects: success, failure, or partial
                # Logic: success = exec.success && verify.passed
                #        partial = exec.success && !verify.passed
                #        failure = !exec.success
                exec_data = data.get("exec", {})
                verify_data = data.get("verify", {})

                exec_success = exec_data.get("success", False)
                verify_passed = verify_data.get("passed", False)

                if exec_success and verify_passed:
                    step.status = "success"
                elif exec_success and not verify_passed:
                    step.status = "partial"
                elif not exec_success:
                    step.status = "failure"
                else:
                    # Fallback: if step_end exists but no exec/verify data, default to failure
                    step.status = "failure"

            elif event_type == "run_end":
                # Extract status from run_end event
                run_end_status = data.get("status")
                # Validate status value
                if run_end_status not in ["success", "failure", "partial", "unknown"]:
                    run_end_status = None

            byte_offset += line_len

    # Use run_end status if available, otherwise infer from step statuses
    if run_end_status is None:
        step_statuses = [step.status for step in steps_by_id.values()]
        if step_statuses:
            # Infer overall status from step statuses
            if all(s == "success" for s in step_statuses):
                run_end_status = "success"
            elif any(s == "failure" for s in step_statuses):
                # If any failure and no successes, it's failure; otherwise partial
                if any(s == "success" for s in step_statuses):
                    run_end_status = "partial"
                else:
                    run_end_status = "failure"
            elif any(s == "partial" for s in step_statuses):
                run_end_status = "partial"
            else:
                run_end_status = "failure"  # Default to failure instead of unknown
        else:
            run_end_status = "failure"  # Default to failure instead of unknown

    # Calculate duration
    duration_ms = None
    if first_ts and last_ts:
        try:
            start = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            end = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            duration_ms = int((end - start).total_seconds() * 1000)
        except (ValueError, AttributeError):
            duration_ms = None

    # Aggregate counters
    snapshot_count = sum(step.counters.snapshots for step in steps_by_id.values())
    action_count = sum(step.counters.actions for step in steps_by_id.values())
    counters = {
        "snapshot_count": snapshot_count,
        "action_count": action_count,
        "error_count": error_count,
    }

    # Build summary
    summary = TraceSummary(
        first_ts=first_ts,
        last_ts=last_ts,
        event_count=event_count,
        step_count=len(steps_by_id),
        error_count=error_count,
        final_url=final_url,
        status=run_end_status,
        agent_name=agent_name,
        duration_ms=duration_ms,
        counters=counters,
    )

    # Build steps list in order
    steps_list = [steps_by_id[sid] for sid in step_order]

    # Build trace file info
    trace_file = TraceFileInfo(
        path=str(trace_path),
        size_bytes=os.path.getsize(trace_path),
        sha256=_compute_file_sha256(str(trace_path)),
        line_count=line_count,
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


def write_trace_index(
    trace_path: str, index_path: str | None = None, frontend_format: bool = False
) -> str:
    """
    Build index and write to file.

    Args:
        trace_path: Path to trace JSONL file
        index_path: Optional custom path for index file (default: trace_path with .index.json)
        frontend_format: If True, write in frontend-compatible format (default: False)

    Returns:
        Path to written index file
    """
    if index_path is None:
        index_path = str(Path(trace_path).with_suffix("")) + ".index.json"

    index = build_trace_index(trace_path)

    with open(index_path, "w", encoding="utf-8") as f:
        if frontend_format:
            json.dump(index.to_sentience_studio_dict(), f, indent=2)
        else:
            json.dump(index.to_dict(), f, indent=2)

    return index_path


def read_step_events(trace_path: str, offset_start: int, offset_end: int) -> list[dict[str, Any]]:
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
