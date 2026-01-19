from __future__ import annotations

import gzip
import json
import logging
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import requests

from sentience.constants import SENTIENCE_API_URL

logger = logging.getLogger(__name__)


class SentienceLogger(Protocol):
    """Protocol for optional logger interface."""

    def info(self, message: str) -> None:
        """Log info message."""
        ...

    def warning(self, message: str) -> None:
        """Log warning message."""
        ...

    def error(self, message: str) -> None:
        """Log error message."""
        ...


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

    def upload_to_cloud(
        self,
        *,
        api_key: str,
        api_url: str | None = None,
        persisted_dir: Path | None = None,
        ext_logger: SentienceLogger | None = None,
    ) -> str | None:
        """
        Upload persisted artifacts to cloud storage.

        This method uploads all artifacts from a persisted directory to cloud storage
        using presigned URLs from the gateway. It follows the same pattern as trace
        screenshot uploads.

        Args:
            api_key: Sentience API key for authentication
            api_url: Sentience API base URL (default: https://api.sentienceapi.com)
            persisted_dir: Path to persisted artifacts directory. If None, uses the
                          most recent persist() output directory.
            ext_logger: Optional logger for progress/error messages

        Returns:
            artifact_index_key on success, None on failure

        Example:
            >>> buf = FailureArtifactBuffer(run_id="run-123", options=options)
            >>> buf.add_frame(screenshot_bytes)
            >>> run_dir = buf.persist(reason="assertion failed", status="failure")
            >>> artifact_key = buf.upload_to_cloud(api_key="sk-...")
            >>> # artifact_key can be passed to /v1/traces/complete
        """
        base_url = api_url or SENTIENCE_API_URL

        # Determine which directory to upload
        if persisted_dir is None:
            # Find most recent persisted directory
            output_dir = Path(self.options.output_dir)
            if not output_dir.exists():
                if ext_logger:
                    ext_logger.warning("No artifacts directory found")
                return None

            # Look for directories matching run_id pattern
            matching_dirs = sorted(
                [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith(self.run_id)],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not matching_dirs:
                if ext_logger:
                    ext_logger.warning(f"No persisted artifacts found for run_id={self.run_id}")
                return None
            persisted_dir = matching_dirs[0]

        if not persisted_dir.exists():
            if ext_logger:
                ext_logger.warning(f"Artifacts directory not found: {persisted_dir}")
            return None

        # Read manifest to understand what files need uploading
        manifest_path = persisted_dir / "manifest.json"
        if not manifest_path.exists():
            if ext_logger:
                ext_logger.warning("manifest.json not found in artifacts directory")
            return None

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        # Build list of artifacts to upload
        artifacts = self._collect_artifacts_for_upload(persisted_dir, manifest)
        if not artifacts:
            if ext_logger:
                ext_logger.warning("No artifacts to upload")
            return None

        if ext_logger:
            ext_logger.info(f"Uploading {len(artifacts)} artifact(s) to cloud")

        # Request presigned URLs from gateway
        upload_urls = self._request_artifact_urls(
            api_key=api_key,
            api_url=base_url,
            artifacts=artifacts,
            ext_logger=ext_logger,
        )
        if not upload_urls:
            return None

        # Upload artifacts in parallel
        artifact_index_key = self._upload_artifacts(
            artifacts=artifacts,
            upload_urls=upload_urls,
            ext_logger=ext_logger,
        )

        if artifact_index_key:
            # Report completion to gateway
            self._complete_artifacts(
                api_key=api_key,
                api_url=base_url,
                artifact_index_key=artifact_index_key,
                artifacts=artifacts,
                ext_logger=ext_logger,
            )

        return artifact_index_key

    def _collect_artifacts_for_upload(
        self, persisted_dir: Path, manifest: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Collect list of artifacts with their metadata for upload."""
        artifacts: list[dict[str, Any]] = []

        # Core JSON artifacts
        json_files = ["manifest.json", "steps.json"]
        if manifest.get("snapshot"):
            json_files.append("snapshot.json")
        if manifest.get("diagnostics"):
            json_files.append("diagnostics.json")

        for filename in json_files:
            file_path = persisted_dir / filename
            if file_path.exists():
                artifacts.append(
                    {
                        "name": filename,
                        "size_bytes": file_path.stat().st_size,
                        "content_type": "application/json",
                        "path": file_path,
                    }
                )

        # Video clip
        if manifest.get("clip"):
            clip_path = persisted_dir / "failure.mp4"
            if clip_path.exists():
                artifacts.append(
                    {
                        "name": "failure.mp4",
                        "size_bytes": clip_path.stat().st_size,
                        "content_type": "video/mp4",
                        "path": clip_path,
                    }
                )

        # Frames
        frames_dir = persisted_dir / "frames"
        if frames_dir.exists():
            for frame_file in sorted(frames_dir.iterdir()):
                if frame_file.is_file() and frame_file.suffix in {".jpeg", ".jpg", ".png"}:
                    content_type = (
                        "image/jpeg" if frame_file.suffix in {".jpeg", ".jpg"} else "image/png"
                    )
                    artifacts.append(
                        {
                            "name": f"frames/{frame_file.name}",
                            "size_bytes": frame_file.stat().st_size,
                            "content_type": content_type,
                            "path": frame_file,
                        }
                    )

        return artifacts

    def _request_artifact_urls(
        self,
        *,
        api_key: str,
        api_url: str,
        artifacts: list[dict[str, Any]],
        ext_logger: SentienceLogger | None,
    ) -> dict[str, Any] | None:
        """Request presigned upload URLs from gateway."""
        try:
            # Prepare request payload (exclude local path)
            artifacts_payload = [
                {
                    "name": a["name"],
                    "size_bytes": a["size_bytes"],
                    "content_type": a["content_type"],
                }
                for a in artifacts
            ]

            response = requests.post(
                f"{api_url}/v1/traces/artifacts/init",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "run_id": self.run_id,
                    "artifacts": artifacts_payload,
                },
                timeout=30,
            )

            if response.status_code != 200:
                if ext_logger:
                    ext_logger.warning(
                        f"Failed to get artifact upload URLs: HTTP {response.status_code}"
                    )
                return None

            return response.json()

        except Exception as e:
            if ext_logger:
                ext_logger.error(f"Error requesting artifact upload URLs: {e}")
            return None

    def _upload_artifacts(
        self,
        *,
        artifacts: list[dict[str, Any]],
        upload_urls: dict[str, Any],
        ext_logger: SentienceLogger | None,
    ) -> str | None:
        """Upload artifacts to cloud storage using presigned URLs."""
        url_map = {item["name"]: item for item in upload_urls.get("upload_urls", [])}
        index_upload = upload_urls.get("artifact_index_upload")

        uploaded_count = 0
        failed_names: list[str] = []
        storage_keys: dict[str, str] = {}

        def upload_one(artifact: dict[str, Any]) -> bool:
            """Upload a single artifact. Returns True if successful."""
            name = artifact["name"]
            url_info = url_map.get(name)
            if not url_info:
                return False

            try:
                file_path = artifact["path"]
                with open(file_path, "rb") as f:
                    data = f.read()

                response = requests.put(
                    url_info["upload_url"],
                    data=data,
                    headers={"Content-Type": artifact["content_type"]},
                    timeout=60,
                )

                if response.status_code == 200:
                    storage_keys[name] = url_info.get("storage_key", "")
                    return True
                else:
                    if ext_logger:
                        ext_logger.warning(
                            f"Artifact {name} upload failed: HTTP {response.status_code}"
                        )
                    return False

            except Exception as e:
                if ext_logger:
                    ext_logger.warning(f"Artifact {name} upload error: {e}")
                return False

        # Upload in parallel (max 10 concurrent)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(upload_one, a): a["name"] for a in artifacts}

            for future in as_completed(futures):
                name = futures[future]
                if future.result():
                    uploaded_count += 1
                else:
                    failed_names.append(name)

        if ext_logger:
            if uploaded_count == len(artifacts):
                ext_logger.info(f"All {uploaded_count} artifacts uploaded successfully")
            else:
                ext_logger.warning(
                    f"Uploaded {uploaded_count}/{len(artifacts)} artifacts. "
                    f"Failed: {failed_names}"
                )

        # Upload artifact index file
        if index_upload and uploaded_count > 0:
            artifact_index_key = self._upload_artifact_index(
                artifacts=artifacts,
                storage_keys=storage_keys,
                index_upload=index_upload,
                ext_logger=ext_logger,
            )
            return artifact_index_key

        return None

    def _upload_artifact_index(
        self,
        *,
        artifacts: list[dict[str, Any]],
        storage_keys: dict[str, str],
        index_upload: dict[str, Any],
        ext_logger: SentienceLogger | None,
    ) -> str | None:
        """Create and upload artifact index file."""
        try:
            # Build index content
            index_data = {
                "run_id": self.run_id,
                "created_at_ms": int(time.time() * 1000),
                "artifacts": [
                    {
                        "name": a["name"],
                        "storage_key": storage_keys.get(a["name"], ""),
                        "content_type": a["content_type"],
                    }
                    for a in artifacts
                    if a["name"] in storage_keys
                ],
            }

            # Compress and upload
            index_json = json.dumps(index_data, indent=2).encode("utf-8")
            compressed = gzip.compress(index_json)

            response = requests.put(
                index_upload["upload_url"],
                data=compressed,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
                timeout=30,
            )

            if response.status_code == 200:
                artifact_index_key = index_upload.get("storage_key", "")
                if ext_logger:
                    ext_logger.info("Artifact index uploaded successfully")
                return artifact_index_key
            else:
                if ext_logger:
                    ext_logger.warning(f"Artifact index upload failed: HTTP {response.status_code}")
                return None

        except Exception as e:
            if ext_logger:
                ext_logger.warning(f"Error uploading artifact index: {e}")
            return None

    def _complete_artifacts(
        self,
        *,
        api_key: str,
        api_url: str,
        artifact_index_key: str,
        artifacts: list[dict[str, Any]],
        ext_logger: SentienceLogger | None,
    ) -> None:
        """Report artifact upload completion to gateway."""
        try:
            # Calculate stats
            total_size = sum(a["size_bytes"] for a in artifacts)
            frames_artifacts = [a for a in artifacts if a["name"].startswith("frames/")]
            frames_total = sum(a["size_bytes"] for a in frames_artifacts)

            # Get individual file sizes
            manifest_size = next(
                (a["size_bytes"] for a in artifacts if a["name"] == "manifest.json"), 0
            )
            snapshot_size = next(
                (a["size_bytes"] for a in artifacts if a["name"] == "snapshot.json"), 0
            )
            diagnostics_size = next(
                (a["size_bytes"] for a in artifacts if a["name"] == "diagnostics.json"), 0
            )
            steps_size = next((a["size_bytes"] for a in artifacts if a["name"] == "steps.json"), 0)
            clip_size = next((a["size_bytes"] for a in artifacts if a["name"] == "failure.mp4"), 0)

            response = requests.post(
                f"{api_url}/v1/traces/artifacts/complete",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "run_id": self.run_id,
                    "artifact_index_key": artifact_index_key,
                    "stats": {
                        "manifest_size_bytes": manifest_size,
                        "snapshot_size_bytes": snapshot_size,
                        "diagnostics_size_bytes": diagnostics_size,
                        "steps_size_bytes": steps_size,
                        "clip_size_bytes": clip_size,
                        "frames_total_size_bytes": frames_total,
                        "frames_count": len(frames_artifacts),
                        "total_artifact_size_bytes": total_size,
                    },
                },
                timeout=10,
            )

            if response.status_code == 200:
                if ext_logger:
                    ext_logger.info("Artifact completion reported to gateway")
            else:
                if ext_logger:
                    ext_logger.warning(
                        f"Failed to report artifact completion: HTTP {response.status_code}"
                    )

        except Exception as e:
            # Best-effort - log but don't fail
            if ext_logger:
                ext_logger.warning(f"Error reporting artifact completion: {e}")
