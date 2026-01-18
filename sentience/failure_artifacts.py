from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass
class FailureArtifactsOptions:
    buffer_seconds: float = 15.0
    capture_on_action: bool = True
    fps: float = 0.0
    persist_mode: Literal["onFail", "always"] = "onFail"
    output_dir: str = ".sentience/artifacts"


@dataclass
class _FrameRecord:
    ts: float
    file_name: str
    path: Path


class FailureArtifactBuffer:
    """
    Ring buffer of screenshots with minimal persistence on failure.
    """

    def __init__(
        self,
        *,
        run_id: str,
        options: FailureArtifactsOptions,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self.run_id = run_id
        self.options = options
        self._time_fn = time_fn
        self._temp_dir = Path(tempfile.mkdtemp(prefix="sentience-artifacts-"))
        self._frames_dir = self._temp_dir / "frames"
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        self._frames: list[_FrameRecord] = []
        self._steps: list[dict] = []
        self._persisted = False

    @property
    def temp_dir(self) -> Path:
        return self._temp_dir

    def record_step(
        self,
        *,
        action: str,
        step_id: str | None,
        step_index: int | None,
        url: str | None,
    ) -> None:
        self._steps.append(
            {
                "ts": self._time_fn(),
                "action": action,
                "step_id": step_id,
                "step_index": step_index,
                "url": url,
            }
        )

    def add_frame(self, image_bytes: bytes, *, fmt: str = "png") -> None:
        ts = self._time_fn()
        file_name = f"frame_{int(ts * 1000)}.{fmt}"
        path = self._frames_dir / file_name
        path.write_bytes(image_bytes)
        self._frames.append(_FrameRecord(ts=ts, file_name=file_name, path=path))
        self._prune()

    def frame_count(self) -> int:
        return len(self._frames)

    def _prune(self) -> None:
        cutoff = self._time_fn() - max(0.0, self.options.buffer_seconds)
        keep: list[_FrameRecord] = []
        for frame in self._frames:
            if frame.ts >= cutoff:
                keep.append(frame)
            else:
                try:
                    frame.path.unlink(missing_ok=True)
                except Exception:
                    pass
        self._frames = keep

    def _write_json_atomic(self, path: Path, data: Any) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.replace(path)

    def persist(
        self,
        *,
        reason: str | None,
        status: Literal["failure", "success"],
        snapshot: Any | None = None,
        diagnostics: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path | None:
        if self._persisted:
            return None

        output_dir = Path(self.options.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = int(self._time_fn() * 1000)
        run_dir = output_dir / f"{self.run_id}-{ts}"
        frames_out = run_dir / "frames"
        frames_out.mkdir(parents=True, exist_ok=True)

        for frame in self._frames:
            shutil.copy2(frame.path, frames_out / frame.file_name)

        self._write_json_atomic(run_dir / "steps.json", self._steps)

        snapshot_payload = None
        if snapshot is not None:
            if hasattr(snapshot, "model_dump"):
                snapshot_payload = snapshot.model_dump()
            else:
                snapshot_payload = snapshot
            self._write_json_atomic(run_dir / "snapshot.json", snapshot_payload)

        diagnostics_payload = None
        if diagnostics is not None:
            if hasattr(diagnostics, "model_dump"):
                diagnostics_payload = diagnostics.model_dump()
            else:
                diagnostics_payload = diagnostics
            self._write_json_atomic(run_dir / "diagnostics.json", diagnostics_payload)

        manifest = {
            "run_id": self.run_id,
            "created_at_ms": ts,
            "status": status,
            "reason": reason,
            "buffer_seconds": self.options.buffer_seconds,
            "frame_count": len(self._frames),
            "frames": [{"file": frame.file_name, "ts": frame.ts} for frame in self._frames],
            "snapshot": "snapshot.json" if snapshot_payload is not None else None,
            "diagnostics": "diagnostics.json" if diagnostics_payload is not None else None,
            "metadata": metadata or {},
        }
        self._write_json_atomic(run_dir / "manifest.json", manifest)

        self._persisted = True
        return run_dir

    def cleanup(self) -> None:
        if self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
