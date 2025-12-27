"""
Cloud trace sink with pre-signed URL upload.

Implements "Local Write, Batch Upload" pattern for enterprise cloud tracing.
"""

import gzip
import json
import os
import tempfile
from typing import Any

import requests

from sentience.tracing import TraceEvent, TraceSink


class CloudTraceSink(TraceSink):
    """
    Enterprise Cloud Sink: "Local Write, Batch Upload" pattern.

    Architecture:
    1. **Local Buffer**: Writes to temp file (zero latency, non-blocking)
    2. **Pre-signed URL**: Uses secure pre-signed PUT URL from backend API
    3. **Batch Upload**: Uploads complete file on close() or at intervals
    4. **Zero Credential Exposure**: Never embeds DigitalOcean credentials in SDK

    This design ensures:
    - Fast agent performance (microseconds per emit, not milliseconds)
    - Security (credentials stay on backend)
    - Reliability (network issues don't crash the agent)

    Tiered Access:
    - Free Tier: Falls back to JsonlTraceSink (local-only)
    - Pro/Enterprise: Uploads to cloud via pre-signed URLs

    Example:
        >>> from sentience.cloud_tracing import CloudTraceSink
        >>> from sentience.tracing import Tracer
        >>> # Get upload URL from API
        >>> upload_url = "https://sentience.nyc3.digitaloceanspaces.com/..."
        >>> sink = CloudTraceSink(upload_url)
        >>> tracer = Tracer(run_id="demo", sink=sink)
        >>> tracer.emit_run_start("SentienceAgent")
        >>> tracer.close()  # Uploads to cloud
    """

    def __init__(self, upload_url: str):
        """
        Initialize cloud trace sink.

        Args:
            upload_url: Pre-signed PUT URL from Sentience API
                        (e.g., "https://sentience.nyc3.digitaloceanspaces.com/...")
        """
        self.upload_url = upload_url

        # Create temporary file for buffering
        # delete=False so we can read it back before uploading
        self._temp_file = tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            suffix=".jsonl",
            delete=False,
        )
        self._path = self._temp_file.name
        self._closed = False

    def emit(self, event: dict[str, Any]) -> None:
        """
        Write event to local temp file (Fast, non-blocking).

        Performance: ~10 microseconds per write vs ~50ms for HTTP request

        Args:
            event: Event dictionary from TraceEvent.to_dict()
        """
        if self._closed:
            raise RuntimeError("CloudTraceSink is closed")

        json_str = json.dumps(event, ensure_ascii=False)
        self._temp_file.write(json_str + "\n")
        self._temp_file.flush()  # Ensure written to disk

    def close(self) -> None:
        """
        Upload buffered trace to cloud via pre-signed URL.

        This is the only network call - happens once at the end.
        """
        if self._closed:
            return

        self._closed = True

        try:
            # 1. Close temp file
            self._temp_file.close()

            # 2. Compress for upload
            with open(self._path, "rb") as f:
                trace_data = f.read()

            compressed_data = gzip.compress(trace_data)

            # 3. Upload to DigitalOcean Spaces via pre-signed URL
            print(f"📤 [Sentience] Uploading trace to cloud ({len(compressed_data)} bytes)...")

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
                print("✅ [Sentience] Trace uploaded successfully")
            else:
                print(f"❌ [Sentience] Upload failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                print(f"   Local trace preserved at: {self._path}")

        except Exception as e:
            print(f"❌ [Sentience] Error uploading trace: {e}")
            print(f"   Local trace preserved at: {self._path}")
            # Don't raise - preserve trace locally even if upload fails

        finally:
            # 4. Cleanup temp file (only if upload succeeded)
            if os.path.exists(self._path):
                try:
                    # Only delete if upload was successful
                    if hasattr(self, "_upload_successful") and self._upload_successful:
                        os.remove(self._path)
                except Exception:
                    pass  # Ignore cleanup errors

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
        return False
