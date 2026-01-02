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
                        "screenshot_count": self.screenshot_count,
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
            else:
                print(f"⚠️  [Sentience] Error extracting screenshots: {e}")

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
            else:
                print(f"⚠️  [Sentience] Error creating cleaned trace: {e}")
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
                    self.logger.warning(error_msg)
                else:
                    print(f"   ⚠️  {error_msg}")
                # Try to get error details
                try:
                    error_data = response.json()
                    error_detail = error_data.get("error") or error_data.get("message", "")
                    if error_detail:
                        print(f"      Error: {error_detail}")
                except Exception:
                    print(f"      Response: {response.text[:200]}")
                return {}
        except Exception as e:
            error_msg = f"Error requesting screenshot URLs: {e}"
            if self.logger:
                self.logger.warning(error_msg)
            else:
                print(f"   ⚠️  {error_msg}")
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
        print(f"   Requesting upload URLs for {len(sequences)} screenshot(s)...")
        upload_urls = self._request_screenshot_urls(sequences)

        if not upload_urls:
            print("⚠️  [Sentience] No screenshot upload URLs received, skipping upload")
            print("   This may indicate:")
            print("   - API key doesn't have permission for screenshot uploads")
            print("   - Gateway endpoint /v1/screenshots/init returned an error")
            print("   - Network issue connecting to gateway")
            return
        
        print(f"   ✅ Received {len(upload_urls)} upload URL(s) from gateway")

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
                # Extract the base URL for logging (without query params)
                upload_base_url = url.split('?')[0] if '?' in url else url
                if self.verbose if hasattr(self, 'verbose') else False:
                    print(f"   📤 Uploading screenshot {seq} ({image_size / 1024:.1f} KB) to: {upload_base_url[:80]}...")
                
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
                        self.logger.info(f"Screenshot {seq} uploaded successfully ({image_size / 1024:.1f} KB)")
                    else:
                        # Extract base URL for logging (without query params for security)
                        upload_base = url.split('?')[0] if '?' in url else url
                        upload_base_short = upload_base[:80] + "..." if len(upload_base) > 80 else upload_base
                        print(f"   ✅ Screenshot {seq} uploaded: {image_size / 1024:.1f} KB, format={format_str}, URL={upload_base_short}")
                    return True
                else:
                    error_msg = f"Screenshot {seq} upload failed: HTTP {response.status_code}"
                    if self.logger:
                        self.logger.warning(error_msg)
                    else:
                        print(f"   ⚠️  {error_msg}")
                    # Try to get error details from response
                    try:
                        error_detail = response.text[:200]
                        if error_detail:
                            print(f"      Response: {error_detail}")
                    except Exception:
                        pass
                    return False
            except Exception as e:
                error_msg = f"Screenshot {seq} upload error: {e}"
                if self.logger:
                    self.logger.warning(error_msg)
                else:
                    print(f"   ⚠️  {error_msg}")
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
            print(f"✅ [Sentience] All {total_count} screenshots uploaded successfully!")
            print(f"   📊 Total screenshot size: {total_size_mb:.2f} MB")
            print(f"   📸 Screenshots are now available in cloud storage")
        else:
            print(f"⚠️  [Sentience] Uploaded {uploaded_count}/{total_count} screenshots")
            if failed_sequences:
                print(f"   Failed sequences: {failed_sequences}")

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
