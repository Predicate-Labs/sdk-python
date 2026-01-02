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
        self.screenshot_count = 0  # Track number of screenshots extracted
        self.index_file_size_bytes = 0  # Track index file size

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

        Extracts screenshots from trace events, uploads them separately,
        then removes screenshot_base64 from events before uploading trace.

        Args:
            on_progress: Optional callback(uploaded_bytes, total_bytes) for progress updates
        """
        try:
            # Step 1: Extract screenshots from trace events
            screenshots = self._extract_screenshots_from_trace()
            self.screenshot_count = len(screenshots)

            # Step 2: Upload screenshots separately
            if screenshots:
                self._upload_screenshots(screenshots, on_progress)

            # Step 3: Create cleaned trace file (without screenshot_base64)
            cleaned_trace_path = self._path.with_suffix(".cleaned.jsonl")
            self._create_cleaned_trace(cleaned_trace_path)

            # Step 4: Read and compress cleaned trace
            with open(cleaned_trace_path, "rb") as f:
                trace_data = f.read()

            compressed_data = gzip.compress(trace_data)
            compressed_size = len(compressed_data)

            # Measure trace file size
            self.trace_file_size_bytes = compressed_size

            # Log file sizes if logger is provided
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

            # Step 5: Upload cleaned trace to cloud
            if self.logger:
                self.logger.info(f"Uploading trace to cloud ({compressed_size} bytes)")

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
                if self.logger:
                    self.logger.info("Trace uploaded successfully")

                # Report progress: complete
                if on_progress:
                    on_progress(compressed_size, compressed_size)

                # Upload trace index file
                self._upload_index()

                # Call /v1/traces/complete to report file sizes
                self._complete_trace()

                # Delete files only on successful upload
                self._cleanup_files()

                # Clean up temporary cleaned trace file
                if cleaned_trace_path.exists():
                    cleaned_trace_path.unlink()
            else:
                self._upload_successful = False
                print(f"❌ [Sentience] Upload failed: HTTP {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                print(f"   Local trace preserved at: {self._path}")
                if self.logger:
                    self.logger.error(
                        f"Upload failed: HTTP {response.status_code}, Response: {response.text[:200]}"
                    )

        except Exception as e:
            self._upload_successful = False
            print(f"❌ [Sentience] Error uploading trace: {e}")
            print(f"   Local trace preserved at: {self._path}")
            if self.logger:
                self.logger.error(f"Error uploading trace: {e}")
            # Don't raise - preserve trace locally even if upload fails

    def _generate_index(self) -> None:
        """Generate trace index file (automatic on close)."""
        try:
            from .trace_indexing import write_trace_index

            # Use frontend format to ensure 'step' field is present (1-based)
            # Frontend derives sequence from step.step - 1, so step must be valid
            index_path = Path(str(self._path).replace(".jsonl", ".index.json"))
            write_trace_index(str(self._path), str(index_path), frontend_format=True)
        except Exception as e:
            # Non-fatal: log but don't crash
            print(f"⚠️  Failed to generate trace index: {e}")
            if self.logger:
                self.logger.warning(f"Failed to generate trace index: {e}")

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

            # Read index file and update trace_file.path to cloud storage path
            with open(index_path, encoding="utf-8") as f:
                index_json = json.load(f)

            # Extract cloud storage path from trace upload URL
            # upload_url format: https://...digitaloceanspaces.com/traces/{run_id}.jsonl.gz
            # Extract path: traces/{run_id}.jsonl.gz
            try:
                from urllib.parse import urlparse

                parsed_url = urlparse(self.upload_url)
                # Extract path after domain (e.g., /traces/run-123.jsonl.gz -> traces/run-123.jsonl.gz)
                cloud_trace_path = parsed_url.path.lstrip("/")
                # Update trace_file.path in index
                if "trace_file" in index_json and isinstance(index_json["trace_file"], dict):
                    index_json["trace_file"]["path"] = cloud_trace_path
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to extract cloud path from upload URL: {e}")

            # Serialize updated index to JSON
            index_data = json.dumps(index_json, indent=2).encode("utf-8")
            compressed_index = gzip.compress(index_data)
            index_size = len(compressed_index)
            self.index_file_size_bytes = index_size  # Track index file size

            if self.logger:
                self.logger.info(f"Index file size: {index_size / 1024:.2f} KB")
                self.logger.info(f"Uploading trace index ({index_size} bytes)")

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
                if self.logger:
                    self.logger.info("Trace index uploaded successfully")

                # Delete local index file after successful upload
                try:
                    os.remove(index_path)
                except Exception:
                    pass  # Ignore cleanup errors
            else:
                if self.logger:
                    self.logger.warning(f"Index upload failed: HTTP {index_response.status_code}")

        except Exception as e:
            # Non-fatal: log but don't crash
            if self.logger:
                self.logger.warning(f"Error uploading trace index: {e}")

    def _infer_final_status_from_trace(self) -> str:
        """
        Infer final status from trace events by reading the trace file.

        Returns:
            Final status: "success", "failure", "partial", or "unknown"
        """
        try:
            # Read trace file to analyze events
            with open(self._path, encoding="utf-8") as f:
                events = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError:
                        continue

            if not events:
                return "unknown"

            # Check for run_end event with status
            for event in reversed(events):
                if event.get("type") == "run_end":
                    status = event.get("data", {}).get("status")
                    if status in ("success", "failure", "partial", "unknown"):
                        return status

            # Infer from error events
            has_errors = any(e.get("type") == "error" for e in events)
            if has_errors:
                # Check if there are successful steps too (partial success)
                step_ends = [e for e in events if e.get("type") == "step_end"]
                if step_ends:
                    return "partial"
                return "failure"

            # If we have step_end events and no errors, likely success
            step_ends = [e for e in events if e.get("type") == "step_end"]
            if step_ends:
                return "success"

            return "unknown"

        except Exception:
            # If we can't read the trace, default to unknown
            return "unknown"

    def _extract_stats_from_trace(self) -> dict[str, Any]:
        """
        Extract execution statistics from trace file.

        Returns:
            Dictionary with stats fields for /v1/traces/complete
        """
        try:
            # Read trace file to extract stats
            with open(self._path, encoding="utf-8") as f:
                events = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError:
                        continue

            if not events:
                return {
                    "total_steps": 0,
                    "total_events": 0,
                    "duration_ms": None,
                    "final_status": "unknown",
                    "started_at": None,
                    "ended_at": None,
                }

            # Find run_start and run_end events
            run_start = next((e for e in events if e.get("type") == "run_start"), None)
            run_end = next((e for e in events if e.get("type") == "run_end"), None)

            # Extract timestamps
            started_at: str | None = None
            ended_at: str | None = None
            if run_start:
                started_at = run_start.get("ts")
            if run_end:
                ended_at = run_end.get("ts")

            # Calculate duration
            duration_ms: int | None = None
            if started_at and ended_at:
                try:
                    from datetime import datetime

                    start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                    delta = end_dt - start_dt
                    duration_ms = int(delta.total_seconds() * 1000)
                except Exception:
                    pass

            # Count steps (from step_start events, only first attempt)
            step_indices = set()
            for event in events:
                if event.get("type") == "step_start":
                    step_index = event.get("data", {}).get("step_index")
                    if step_index is not None:
                        step_indices.add(step_index)
            total_steps = len(step_indices) if step_indices else 0

            # If run_end has steps count, use that (more accurate)
            if run_end:
                steps_from_end = run_end.get("data", {}).get("steps")
                if steps_from_end is not None:
                    total_steps = max(total_steps, steps_from_end)

            # Count total events
            total_events = len(events)

            # Infer final status
            final_status = self._infer_final_status_from_trace()

            return {
                "total_steps": total_steps,
                "total_events": total_events,
                "duration_ms": duration_ms,
                "final_status": final_status,
                "started_at": started_at,
                "ended_at": ended_at,
            }

        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error extracting stats from trace: {e}")
            return {
                "total_steps": 0,
                "total_events": 0,
                "duration_ms": None,
                "final_status": "unknown",
                "started_at": None,
                "ended_at": None,
            }

    def _complete_trace(self) -> None:
        """
        Call /v1/traces/complete to report file sizes and stats to gateway.

        This is a best-effort call - failures are logged but don't affect upload success.
        """
        if not self.api_key:
            # No API key - skip complete call
            return

        try:
            # Extract stats from trace file
            stats = self._extract_stats_from_trace()

            # Add file size fields
            stats.update(
                {
                    "trace_file_size_bytes": self.trace_file_size_bytes,
                    "screenshot_total_size_bytes": self.screenshot_total_size_bytes,
                    "screenshot_count": self.screenshot_count,
                    "index_file_size_bytes": self.index_file_size_bytes,
                }
            )

            response = requests.post(
                f"{self.api_url}/v1/traces/complete",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "run_id": self.run_id,
                    "stats": stats,
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

    def _extract_screenshots_from_trace(self) -> dict[int, dict[str, Any]]:
        """
        Extract screenshots from trace events.

        Returns:
            dict mapping sequence number to screenshot data:
            {seq: {"base64": str, "format": str, "step_id": str}}
        """
        screenshots: dict[int, dict[str, Any]] = {}
        sequence = 0

        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                        # Check if this is a snapshot event with screenshot
                        if event.get("type") == "snapshot":
                            data = event.get("data", {})
                            screenshot_base64 = data.get("screenshot_base64")

                            if screenshot_base64:
                                sequence += 1
                                screenshots[sequence] = {
                                    "base64": screenshot_base64,
                                    "format": data.get("screenshot_format", "jpeg"),
                                    "step_id": event.get("step_id"),
                                }
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error extracting screenshots: {e}")

        return screenshots

    def _create_cleaned_trace(self, output_path: Path) -> None:
        """
        Create trace file without screenshot_base64 fields.

        Args:
            output_path: Path to write cleaned trace file
        """
        try:
            with (
                open(self._path, encoding="utf-8") as infile,
                open(output_path, "w", encoding="utf-8") as outfile,
            ):
                for line in infile:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                        # Remove screenshot_base64 from snapshot events
                        if event.get("type") == "snapshot":
                            data = event.get("data", {})
                            if "screenshot_base64" in data:
                                # Create copy without screenshot fields
                                cleaned_data = {
                                    k: v
                                    for k, v in data.items()
                                    if k not in ("screenshot_base64", "screenshot_format")
                                }
                                event["data"] = cleaned_data

                        # Write cleaned event
                        outfile.write(json.dumps(event, ensure_ascii=False) + "\n")
                    except json.JSONDecodeError:
                        # Skip invalid lines
                        continue
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error creating cleaned trace: {e}")
            raise

    def _request_screenshot_urls(self, sequences: list[int]) -> dict[int, str]:
        """
        Request pre-signed upload URLs for screenshots from gateway.

        Args:
            sequences: List of screenshot sequence numbers

        Returns:
            dict mapping sequence number to upload URL
        """
        if not self.api_key or not sequences:
            return {}

        try:
            response = requests.post(
                f"{self.api_url}/v1/screenshots/init",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "run_id": self.run_id,
                    "sequences": sequences,
                },
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                # Gateway returns sequences as strings in JSON, convert to int keys
                upload_urls = data.get("upload_urls", {})
                result = {int(k): v for k, v in upload_urls.items()}
                if self.logger:
                    self.logger.info(f"Received {len(result)} screenshot upload URLs")
                return result
            else:
                error_msg = f"Failed to get screenshot URLs: HTTP {response.status_code}"
                if self.logger:
                    # Try to get error details
                    try:
                        error_data = response.json()
                        error_detail = error_data.get("error") or error_data.get("message", "")
                        if error_detail:
                            self.logger.warning(f"{error_msg}: {error_detail}")
                        else:
                            self.logger.warning(f"{error_msg}: {response.text[:200]}")
                    except Exception:
                        self.logger.warning(f"{error_msg}: {response.text[:200]}")
                return {}
        except Exception as e:
            error_msg = f"Error requesting screenshot URLs: {e}"
            if self.logger:
                self.logger.warning(error_msg)
            return {}

    def _upload_screenshots(
        self,
        screenshots: dict[int, dict[str, Any]],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """
        Upload screenshots extracted from trace events.

        Steps:
        1. Request pre-signed URLs from gateway (/v1/screenshots/init)
        2. Decode base64 to image bytes
        3. Upload screenshots in parallel (10 concurrent workers)
        4. Track upload progress

        Args:
            screenshots: dict mapping sequence to screenshot data
            on_progress: Optional callback(uploaded_count, total_count)
        """
        if not screenshots:
            return

        # 1. Request pre-signed URLs from gateway
        sequences = sorted(screenshots.keys())
        if self.logger:
            self.logger.info(f"Requesting upload URLs for {len(sequences)} screenshot(s)")
        upload_urls = self._request_screenshot_urls(sequences)

        if not upload_urls:
            if self.logger:
                self.logger.warning(
                    "No screenshot upload URLs received, skipping upload. "
                    "This may indicate API key permission issue, gateway error, or network problem."
                )
            return

        # 2. Upload screenshots in parallel
        uploaded_count = 0
        total_count = len(upload_urls)
        failed_sequences: list[int] = []

        def upload_one(seq: int, url: str) -> bool:
            """Upload a single screenshot. Returns True if successful."""
            try:
                screenshot_data = screenshots[seq]
                base64_str = screenshot_data["base64"]
                format_str = screenshot_data.get("format", "jpeg")

                # Decode base64 to image bytes
                image_bytes = base64.b64decode(base64_str)
                image_size = len(image_bytes)

                # Update total size
                self.screenshot_total_size_bytes += image_size

                # Upload to pre-signed URL
                response = requests.put(
                    url,
                    data=image_bytes,  # Binary image data
                    headers={
                        "Content-Type": f"image/{format_str}",
                    },
                    timeout=30,  # 30 second timeout per screenshot
                )

                if response.status_code == 200:
                    if self.logger:
                        self.logger.info(
                            f"Screenshot {seq} uploaded successfully ({image_size / 1024:.1f} KB)"
                        )
                    return True
                else:
                    error_msg = f"Screenshot {seq} upload failed: HTTP {response.status_code}"
                    if self.logger:
                        try:
                            error_detail = response.text[:200]
                            if error_detail:
                                self.logger.warning(f"{error_msg}: {error_detail}")
                            else:
                                self.logger.warning(error_msg)
                        except Exception:
                            self.logger.warning(error_msg)
                    return False
            except Exception as e:
                error_msg = f"Screenshot {seq} upload error: {e}"
                if self.logger:
                    self.logger.warning(error_msg)
                return False

        # Upload in parallel (max 10 concurrent)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(upload_one, seq, url): seq for seq, url in upload_urls.items()
            }

            for future in as_completed(futures):
                seq = futures[future]
                if future.result():
                    uploaded_count += 1
                    if on_progress:
                        on_progress(uploaded_count, total_count)
                else:
                    failed_sequences.append(seq)

        # 3. Report results
        if uploaded_count == total_count:
            total_size_mb = self.screenshot_total_size_bytes / 1024 / 1024
            if self.logger:
                self.logger.info(
                    f"All {total_count} screenshots uploaded successfully "
                    f"(total size: {total_size_mb:.2f} MB)"
                )
        else:
            if self.logger:
                self.logger.warning(
                    f"Uploaded {uploaded_count}/{total_count} screenshots. "
                    f"Failed sequences: {failed_sequences if failed_sequences else 'none'}"
                )

    def _cleanup_files(self) -> None:
        """Delete local files after successful upload."""
        # Delete trace file
        if os.path.exists(self._path):
            try:
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
