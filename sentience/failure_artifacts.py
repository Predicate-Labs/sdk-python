from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class ClipOptions:
    """Options for generating video clips from frames."""

    mode: Literal["off", "auto", "on"] = "auto"
    """Clip generation mode:
    - "off": Never generate clips
    - "auto": Generate only if ffmpeg is available on PATH
    - "on": Always attempt to generate (will warn if ffmpeg missing)
    """
    fps: int = 8
    """Frames per second for the generated video."""
    seconds: float | None = None
    """Duration of clip in seconds. If None, uses buffer_seconds."""


@dataclass
class FailureArtifactsOptions:
    buffer_seconds: float = 15.0
    capture_on_action: bool = True
    fps: float = 0.0
    persist_mode: Literal["onFail", "always"] = "onFail"
    output_dir: str = ".sentience/artifacts"
    on_before_persist: Callable[[RedactionContext], RedactionResult] | None = None
    redact_snapshot_values: bool = True
    clip: ClipOptions = field(default_factory=ClipOptions)


@dataclass
class RedactionContext:
    run_id: str
    reason: str | None
    status: Literal["failure", "success"]
    snapshot: Any | None
    diagnostics: Any | None
    frame_paths: list[str]
    metadata: dict[str, Any]


@dataclass
class RedactionResult:
    snapshot: Any | None = None
    diagnostics: Any | None = None
    frame_paths: list[str] | None = None
    drop_frames: bool = False


@dataclass
class _FrameRecord:
    ts: float
    file_name: str
    path: Path


def _is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _generate_clip_from_frames(
    frames_dir: Path,
    output_path: Path,
    fps: int = 8,
    frame_pattern: str = "frame_*.png",
) -> bool:
    """
    Generate an MP4 video clip from a directory of frames using ffmpeg.

    Args:
        frames_dir: Directory containing frame images
        output_path: Output path for the MP4 file
        fps: Frames per second for the output video
        frame_pattern: Glob pattern to match frame files

    Returns:
        True if clip was generated successfully, False otherwise
    """
    # Find all frames and sort by timestamp (extracted from filename)
    frame_files = sorted(frames_dir.glob(frame_pattern))
    if not frame_files:
        # Try jpeg pattern as well
        frame_files = sorted(frames_dir.glob("frame_*.jpeg"))
    if not frame_files:
        frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    if not frame_files:
        logger.warning("No frame files found for clip generation")
        return False

    # Create a temporary file list for ffmpeg concat demuxer
    # This approach handles arbitrary frame filenames and timing
    list_file = frames_dir / "frames_list.txt"
    try:
        # Calculate frame duration based on FPS
        frame_duration = 1.0 / fps

        with open(list_file, "w") as f:
            for frame_path in frame_files:
                # ffmpeg concat format: file 'path' + duration
                f.write(f"file '{frame_path.name}'\n")
                f.write(f"duration {frame_duration}\n")
            # Add last frame again (ffmpeg concat quirk)
            if frame_files:
                f.write(f"file '{frame_files[-1].name}'\n")

        # Run ffmpeg to generate the clip
        # -y: overwrite output file
        # -f concat: use concat demuxer
        # -safe 0: allow unsafe file paths
        # -i: input file list
        # -vsync vfr: variable frame rate
        # -pix_fmt yuv420p: compatibility with most players
        # -c:v libx264: H.264 codec
        # -crf 23: quality (lower = better, 23 is default)
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-vsync",
            "vfr",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-crf",
            "23",
            str(output_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60,  # 1 minute timeout
            cwd=str(frames_dir),  # Run from frames dir for relative paths
        )

        if result.returncode != 0:
            logger.warning(
                f"ffmpeg failed with return code {result.returncode}: "
                f"{result.stderr.decode('utf-8', errors='replace')[:500]}"
            )
            return False

        return output_path.exists()

    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg timed out during clip generation")
        return False
    except Exception as e:
        logger.warning(f"Error generating clip: {e}")
        return False
    finally:
        # Clean up the list file
        try:
            list_file.unlink(missing_ok=True)
        except Exception:
            pass


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

    def _redact_snapshot_defaults(self, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        elements = payload.get("elements")
        if not isinstance(elements, list):
            return payload
        redacted = []
        for el in elements:
            if not isinstance(el, dict):
                redacted.append(el)
                continue
            input_type = (el.get("input_type") or "").lower()
            if input_type in {"password", "email", "tel"} and "value" in el:
                el = dict(el)
                el["value"] = None
                el["value_redacted"] = True
            redacted.append(el)
        payload = dict(payload)
        payload["elements"] = redacted
        return payload

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

        snapshot_payload = None
        if snapshot is not None:
            if hasattr(snapshot, "model_dump"):
                snapshot_payload = snapshot.model_dump()
            else:
                snapshot_payload = snapshot
            if self.options.redact_snapshot_values:
                snapshot_payload = self._redact_snapshot_defaults(snapshot_payload)

        diagnostics_payload = None
        if diagnostics is not None:
            if hasattr(diagnostics, "model_dump"):
                diagnostics_payload = diagnostics.model_dump()
            else:
                diagnostics_payload = diagnostics

        frame_paths = [str(frame.path) for frame in self._frames]
        drop_frames = False

        if self.options.on_before_persist is not None:
            try:
                result = self.options.on_before_persist(
                    RedactionContext(
                        run_id=self.run_id,
                        reason=reason,
                        status=status,
                        snapshot=snapshot_payload,
                        diagnostics=diagnostics_payload,
                        frame_paths=frame_paths,
                        metadata=metadata or {},
                    )
                )
                if result.snapshot is not None:
                    snapshot_payload = result.snapshot
                if result.diagnostics is not None:
                    diagnostics_payload = result.diagnostics
                if result.frame_paths is not None:
                    frame_paths = result.frame_paths
                drop_frames = result.drop_frames
            except Exception:
                drop_frames = True

        if not drop_frames:
            for frame_path in frame_paths:
                src = Path(frame_path)
                if not src.exists():
                    continue
                shutil.copy2(src, frames_out / src.name)

        self._write_json_atomic(run_dir / "steps.json", self._steps)
        if snapshot_payload is not None:
            self._write_json_atomic(run_dir / "snapshot.json", snapshot_payload)
        if diagnostics_payload is not None:
            self._write_json_atomic(run_dir / "diagnostics.json", diagnostics_payload)

        # Generate video clip from frames (optional, requires ffmpeg)
        clip_generated = False
        clip_path: Path | None = None
        clip_options = self.options.clip

        if not drop_frames and len(frame_paths) > 0 and clip_options.mode != "off":
            should_generate = False

            if clip_options.mode == "auto":
                # Only generate if ffmpeg is available
                should_generate = _is_ffmpeg_available()
                if not should_generate:
                    logger.debug("ffmpeg not available, skipping clip generation (mode=auto)")
            elif clip_options.mode == "on":
                # Always attempt to generate
                should_generate = True
                if not _is_ffmpeg_available():
                    logger.warning(
                        "ffmpeg not found on PATH but clip.mode='on'. "
                        "Install ffmpeg to generate video clips."
                    )
                    should_generate = False

            if should_generate:
                clip_path = run_dir / "failure.mp4"
                clip_generated = _generate_clip_from_frames(
                    frames_dir=frames_out,
                    output_path=clip_path,
                    fps=clip_options.fps,
                )
                if clip_generated:
                    logger.info(f"Generated failure clip: {clip_path}")
                else:
                    logger.warning("Failed to generate video clip")
                    clip_path = None

        manifest = {
            "run_id": self.run_id,
            "created_at_ms": ts,
            "status": status,
            "reason": reason,
            "buffer_seconds": self.options.buffer_seconds,
            "frame_count": 0 if drop_frames else len(frame_paths),
            "frames": (
                [] if drop_frames else [{"file": Path(p).name, "ts": None} for p in frame_paths]
            ),
            "snapshot": "snapshot.json" if snapshot_payload is not None else None,
            "diagnostics": "diagnostics.json" if diagnostics_payload is not None else None,
            "clip": "failure.mp4" if clip_generated else None,
            "clip_fps": clip_options.fps if clip_generated else None,
            "metadata": metadata or {},
            "frames_redacted": not drop_frames and self.options.on_before_persist is not None,
            "frames_dropped": drop_frames,
        }
        self._write_json_atomic(run_dir / "manifest.json", manifest)

        self._persisted = True
        return run_dir

    def cleanup(self) -> None:
        if self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
