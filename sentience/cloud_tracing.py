"""
Cloud trace sink with pre-signed URL upload.

Implements "Local Write, Batch Upload" pattern for enterprise cloud tracing.
"""

import base64
import gzip
import json
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Protocol

import requests

from sentience.models import ScreenshotMetadata
from sentience.tracing import TraceSink


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


class CloudTraceSink(TraceSink):
    """
    Enterprise Cloud Sink: "Local Write, Batch Upload" pattern.

    Architecture:
    1. **Local Buffer**: Writes to persistent cache directory (zero latency, non-blocking)
    2. **Pre-signed URL**: Uses secure pre-signed PUT URL from backend API
    3. **Batch Upload**: Uploads complete file on close() or at intervals
    4. **Zero Credential Exposure**: Never embeds DigitalOcean credentials in SDK
    5. **Crash Recovery**: Traces survive process crashes (stored in ~/.sentience/traces/pending/)

    This design ensures:
    - Fast agent performance (microseconds per emit, not milliseconds)
    - Security (credentials stay on backend)
    - Reliability (network issues don't crash the agent)
    - Data durability (traces survive crashes and can be recovered)

    Tiered Access:
    - Free Tier: Falls back to JsonlTraceSink (local-only)
    - Pro/Enterprise: Uploads to cloud via pre-signed URLs

    Example:
        >>> from sentience.cloud_tracing import CloudTraceSink
        >>> from sentience.tracing import Tracer
        >>> # Get upload URL from API
        >>> upload_url = "https://sentience.nyc3.digitaloceanspaces.com/..."
        >>> sink = CloudTraceSink(upload_url, run_id="demo")
        >>> tracer = Tracer(run_id="demo", sink=sink)
        >>> tracer.emit_run_start("SentienceAgent")
        >>> tracer.close()  # Uploads to cloud
        >>> # Or non-blocking:
        >>> tracer.close(blocking=False)  # Returns immediately
    """

    def __init__(
        self,
        upload_url: str,
        run_id: str,
        api_key: str | None = None,
        api_url: str | None = None,
        logger: SentienceLogger | None = None,
    ):
        """
        Initialize cloud trace sink.

        Args:
            upload_url: Pre-signed PUT URL from Sentience API
                        (e.g., "https://sentience.nyc3.digitaloceanspaces.com/...")
            run_id: Unique identifier for this agent run (used for persistent cache)
            api_key: Sentience API key for calling /v1/traces/complete
            api_url: Sentience API base URL (default: https://api.sentienceapi.com)
            logger: Optional logger instance for logging file sizes and errors
        """
        self.upload_url = upload_url
        self.run_id = run_id
        self.api_key = api_key
        self.api_url = api_url or "https://api.sentienceapi.com"
        self.logger = logger

        # Use persistent cache directory instead of temp file
        # This ensures traces survive process crashes
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Persistent file (survives process crash)
        self._path = cache_dir / f"{run_id}.jsonl"
        self._trace_file = open(self._path, "w", encoding="utf-8")
        self._closed = False
        self._upload_successful = False

        # File size tracking
        self.trace_file_size_bytes = 0
        self.screenshot_total_size_bytes = 0

        # Screenshot storage directory
        self._screenshot_dir = cache_dir / f"{run_id}_screenshots"
        self._screenshot_dir.mkdir(exist_ok=True)

        # Screenshot metadata tracking (sequence -> ScreenshotMetadata)
        self._screenshot_metadata: dict[int, ScreenshotMetadata] = {}

    def emit(self, event: dict[str, Any]) -> None:
        """
        Write event to local persistent file (Fast, non-blocking).

        Performance: ~10 microseconds per write vs ~50ms for HTTP request

        Args:
            event: Event dictionary from TraceEvent.to_dict()
        """
        if self._closed:
            raise RuntimeError("CloudTraceSink is closed")

        json_str = json.dumps(event, ensure_ascii=False)
        self._trace_file.write(json_str + "\n")
        self._trace_file.flush()  # Ensure written to disk

    def close(
        self,
        blocking: bool = True,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """
        Upload buffered trace to cloud via pre-signed URL.

        Args:
            blocking: If False, returns immediately and uploads in background thread
            on_progress: Optional callback(uploaded_bytes, total_bytes) for progress updates

        This is the only network call - happens once at the end.
        """
        if self._closed:
            return

        self._closed = True

        # Close file first
        self._trace_file.close()

        # Generate index after closing file
        self._generate_index()

        if not blocking:
            # Fire-and-forget background upload
            thread = threading.Thread(
                target=self._do_upload,
                args=(on_progress,),
                daemon=True,
            )
            thread.start()
            return  # Return immediately

        # Blocking mode
        self._do_upload(on_progress)

    def _do_upload(self, on_progress: Callable[[int, int], None] | None = None) -> None:
        """
        Internal upload method with progress tracking.

        Args:
            on_progress: Optional callback(uploaded_bytes, total_bytes) for progress updates
        """
        try:
            # Read and compress
            with open(self._path, "rb") as f:
                trace_data = f.read()

            compressed_data = gzip.compress(trace_data)
            compressed_size = len(compressed_data)

            # Measure trace file size (NEW)
            self.trace_file_size_bytes = compressed_size

            # Log file sizes if logger is provided (NEW)
            if self.logger:
                self.logger.info(
                    f"Trace file size: {self.trace_file_size_bytes / 1024 / 1024:.2f} MB"
                )
                self.logger.info(
                    f"Screenshot total: {self.screenshot_total_size_bytes / 1024 / 1024:.2f} MB"
                )

            # Report progress: start
            if on_progress:
                on_progress(0, compressed_size)

            # Upload to DigitalOcean Spaces via pre-signed URL
            print(f"📤 [Sentience] Uploading trace to cloud ({compressed_size} bytes)...")

            response = requests.put(
                self.upload_url,
                data=compressed_data,
                headers={
                    "Content-Type": "application/x-gzip",
                    "Content-Encoding": "gzip",
                },
                timeout=60,  # 1 minute timeout for large files
            )

            if response.status_code == 200:
                self._upload_successful = True
                print("✅ [Sentience] Trace uploaded successfully")

                # Report progress: complete
                if on_progress:
                    on_progress(compressed_size, compressed_size)

                # Upload screenshots after trace upload succeeds
                if self._screenshot_metadata:
                    print(
                        f"📸 [Sentience] Uploading {len(self._screenshot_metadata)} screenshots..."
                    )
                    self._upload_screenshots(on_progress)

                # Upload trace index file
                self._upload_index()

                # Call /v1/traces/complete to report file sizes
                self._complete_trace()

                # Delete files only on successful upload
                self._cleanup_files()
            else:
                self._upload_successful = False
                print(f"❌ [Sentience] Upload failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                print(f"   Local trace preserved at: {self._path}")

        except Exception as e:
            self._upload_successful = False
            print(f"❌ [Sentience] Error uploading trace: {e}")
            print(f"   Local trace preserved at: {self._path}")
            # Don't raise - preserve trace locally even if upload fails

    def _generate_index(self) -> None:
        """Generate trace index file (automatic on close)."""
        try:
            from .trace_indexing import write_trace_index

            write_trace_index(str(self._path))
        except Exception as e:
            # Non-fatal: log but don't crash
            print(f"⚠️  Failed to generate trace index: {e}")

    def _upload_index(self) -> None:
        """
        Upload trace index file to cloud storage.

        Called after successful trace upload to provide fast timeline rendering.
        The index file enables O(1) step lookups without parsing the entire trace.
        """
        # Construct index file path (same as trace file with .index.json extension)
        index_path = Path(str(self._path).replace(".jsonl", ".index.json"))

        if not index_path.exists():
            if self.logger:
                self.logger.warning("Index file not found, skipping index upload")
            return

        try:
            # Request index upload URL from API
            if not self.api_key:
                # No API key - skip index upload
                if self.logger:
                    self.logger.info("No API key provided, skipping index upload")
                return

            response = requests.post(
                f"{self.api_url}/v1/traces/index_upload",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"run_id": self.run_id},
                timeout=10,
            )

            if response.status_code != 200:
                if self.logger:
                    self.logger.warning(
                        f"Failed to get index upload URL: HTTP {response.status_code}"
                    )
                return

            upload_data = response.json()
            index_upload_url = upload_data.get("upload_url")

            if not index_upload_url:
                if self.logger:
                    self.logger.warning("No upload URL in index upload response")
                return

            # Read and compress index file
            with open(index_path, "rb") as f:
                index_data = f.read()

            compressed_index = gzip.compress(index_data)
            index_size = len(compressed_index)

            if self.logger:
                self.logger.info(f"Index file size: {index_size / 1024:.2f} KB")

            print(f"📤 [Sentience] Uploading trace index ({index_size} bytes)...")

            # Upload index to cloud storage
            index_response = requests.put(
                index_upload_url,
                data=compressed_index,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
                timeout=30,
            )

            if index_response.status_code == 200:
                print("✅ [Sentience] Trace index uploaded successfully")

                # Delete local index file after successful upload
                try:
                    os.remove(index_path)
                except Exception:
                    pass  # Ignore cleanup errors
            else:
                if self.logger:
                    self.logger.warning(f"Index upload failed: HTTP {index_response.status_code}")
                print(f"⚠️  [Sentience] Index upload failed: HTTP {index_response.status_code}")

        except Exception as e:
            # Non-fatal: log but don't crash
            if self.logger:
                self.logger.warning(f"Error uploading trace index: {e}")
            print(f"⚠️  [Sentience] Error uploading trace index: {e}")

    def _complete_trace(self) -> None:
        """
        Call /v1/traces/complete to report file sizes to gateway.

        This is a best-effort call - failures are logged but don't affect upload success.
        """
        if not self.api_key:
            # No API key - skip complete call
            return

        try:
            response = requests.post(
                f"{self.api_url}/v1/traces/complete",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "run_id": self.run_id,
                    "stats": {
                        "trace_file_size_bytes": self.trace_file_size_bytes,
                        "screenshot_total_size_bytes": self.screenshot_total_size_bytes,
                        "screenshot_count": len(self._screenshot_metadata),
                    },
                },
                timeout=10,
            )

            if response.status_code == 200:
                if self.logger:
                    self.logger.info("Trace completion reported to gateway")
            else:
                if self.logger:
                    self.logger.warning(
                        f"Failed to report trace completion: HTTP {response.status_code}"
                    )

        except Exception as e:
            # Best-effort - log but don't fail
            if self.logger:
                self.logger.warning(f"Error reporting trace completion: {e}")

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
        return False
