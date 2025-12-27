"""
Cloud trace sink with pre-signed URL upload.

Implements "Local Write, Batch Upload" pattern for enterprise cloud tracing.
"""

import gzip
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from sentience.tracing import TraceSink


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

    def __init__(self, upload_url: str, run_id: str):
        """
        Initialize cloud trace sink.

        Args:
            upload_url: Pre-signed PUT URL from Sentience API
                        (e.g., "https://sentience.nyc3.digitaloceanspaces.com/...")
            run_id: Unique identifier for this agent run (used for persistent cache)
        """
        self.upload_url = upload_url
        self.run_id = run_id

        # Use persistent cache directory instead of temp file
        # This ensures traces survive process crashes
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Persistent file (survives process crash)
        self._path = cache_dir / f"{run_id}.jsonl"
        self._trace_file = open(self._path, "w", encoding="utf-8")
        self._closed = False
        self._upload_successful = False

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

                # Delete file only on successful upload
                if os.path.exists(self._path):
                    try:
                        os.remove(self._path)
                    except Exception:
                        pass  # Ignore cleanup errors
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

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
        return False
