"""
Tracer factory with automatic tier detection.

Provides convenient factory function for creating tracers with cloud upload support.
"""

import gzip
import os
import uuid
from pathlib import Path

import requests

from sentience.cloud_tracing import CloudTraceSink, SentienceLogger
from sentience.tracing import JsonlTraceSink, Tracer

# Sentience API base URL (constant)
SENTIENCE_API_URL = "https://api.sentienceapi.com"


def create_tracer(
    api_key: str | None = None,
    run_id: str | None = None,
    api_url: str | None = None,
    logger: SentienceLogger | None = None,
    upload_trace: bool = False,
) -> Tracer:
    """
    Create tracer with automatic tier detection.

    Tier Detection:
    - If api_key is provided: Try to initialize CloudTraceSink (Pro/Enterprise)
    - If cloud init fails or no api_key: Fall back to JsonlTraceSink (Free tier)

    Args:
        api_key: Sentience API key (e.g., "sk_pro_xxxxx")
                 - Free tier: None or empty
                 - Pro/Enterprise: Valid API key
        run_id: Unique identifier for this agent run. If not provided, generates UUID.
        api_url: Sentience API base URL (default: https://api.sentienceapi.com)
        logger: Optional logger instance for logging file sizes and errors
        upload_trace: Enable cloud trace upload (default: False). When True and api_key
                      is provided, traces will be uploaded to cloud. When False, traces
                      are saved locally only.

    Returns:
        Tracer configured with appropriate sink

    Example:
        >>> # Pro tier user
        >>> tracer = create_tracer(api_key="sk_pro_xyz", run_id="demo")
        >>> # Returns: Tracer with CloudTraceSink
        >>>
        >>> # Free tier user
        >>> tracer = create_tracer(run_id="demo")
        >>> # Returns: Tracer with JsonlTraceSink (local-only)
        >>>
        >>> # Use with agent
        >>> agent = SentienceAgent(browser, llm, tracer=tracer)
        >>> agent.act("Click search")
        >>> tracer.close()  # Uploads to cloud if Pro tier
    """
    if run_id is None:
        run_id = str(uuid.uuid4())

    if api_url is None:
        api_url = SENTIENCE_API_URL

    # 0. Check for orphaned traces from previous crashes (if api_key provided and upload enabled)
    if api_key and upload_trace:
        _recover_orphaned_traces(api_key, api_url)

    # 1. Try to initialize Cloud Sink (Pro/Enterprise tier) if upload enabled
    if api_key and upload_trace:
        try:
            # Request pre-signed upload URL from backend
            response = requests.post(
                f"{api_url}/v1/traces/init",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"run_id": run_id},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                upload_url = data.get("upload_url")

                if upload_url:
                    print("☁️  [Sentience] Cloud tracing enabled (Pro tier)")
                    return Tracer(
                        run_id=run_id,
                        sink=CloudTraceSink(
                            upload_url=upload_url,
                            run_id=run_id,
                            api_key=api_key,
                            api_url=api_url,
                            logger=logger,
                        ),
                    )
                else:
                    print("⚠️  [Sentience] Cloud init response missing upload_url")
                    print(f"   Response data: {data}")
                    print("   Falling back to local-only tracing")

            elif response.status_code == 403:
                print("⚠️  [Sentience] Cloud tracing requires Pro tier")
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error") or error_data.get("message", "")
                    if error_msg:
                        print(f"   API Error: {error_msg}")
                except Exception:
                    pass
                print("   Falling back to local-only tracing")
            elif response.status_code == 401:
                print("⚠️  [Sentience] Cloud init failed: HTTP 401 Unauthorized")
                print("   API key is invalid or expired")
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error") or error_data.get("message", "")
                    if error_msg:
                        print(f"   API Error: {error_msg}")
                except Exception:
                    pass
                print("   Falling back to local-only tracing")
            else:
                print(f"⚠️  [Sentience] Cloud init failed: HTTP {response.status_code}")
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error") or error_data.get(
                        "message", "Unknown error"
                    )
                    print(f"   Error: {error_msg}")
                    if "tier" in error_msg.lower() or "subscription" in error_msg.lower():
                        print(f"   💡 This may be a tier/subscription issue")
                except Exception:
                    print(f"   Response: {response.text[:200]}")
                print("   Falling back to local-only tracing")

        except requests.exceptions.Timeout:
            print("⚠️  [Sentience] Cloud init timeout")
            print("   Falling back to local-only tracing")
        except requests.exceptions.ConnectionError:
            print("⚠️  [Sentience] Cloud init connection error")
            print("   Falling back to local-only tracing")
        except Exception as e:
            print(f"⚠️  [Sentience] Cloud init error: {e}")
            print("   Falling back to local-only tracing")

    # 2. Fallback to Local Sink (Free tier / Offline mode)
    traces_dir = Path("traces")
    traces_dir.mkdir(exist_ok=True)

    local_path = traces_dir / f"{run_id}.jsonl"
    print(f"💾 [Sentience] Local tracing: {local_path}")

    return Tracer(run_id=run_id, sink=JsonlTraceSink(str(local_path)))


def _recover_orphaned_traces(api_key: str, api_url: str = SENTIENCE_API_URL) -> None:
    """
    Attempt to upload orphaned traces from previous crashed runs.

    Scans ~/.sentience/traces/pending/ for un-uploaded trace files and
    attempts to upload them using the provided API key.

    Args:
        api_key: Sentience API key for authentication
        api_url: Sentience API base URL (defaults to SENTIENCE_API_URL)
    """
    pending_dir = Path.home() / ".sentience" / "traces" / "pending"

    if not pending_dir.exists():
        return

    orphaned = list(pending_dir.glob("*.jsonl"))

    if not orphaned:
        return

    # Filter out test files (run_ids that start with "test-" or are clearly test data)
    # These are likely from local testing and shouldn't be uploaded
    test_patterns = ["test-", "test_", "test."]
    valid_orphaned = [
        f
        for f in orphaned
        if not any(f.stem.startswith(pattern) for pattern in test_patterns)
        and not f.stem.startswith("test")
    ]

    if not valid_orphaned:
        return

    print(f"⚠️  [Sentience] Found {len(valid_orphaned)} un-uploaded trace(s) from previous runs")
    print("   Attempting to upload now...")

    for trace_file in valid_orphaned:
        try:
            # Extract run_id from filename (format: {run_id}.jsonl)
            run_id = trace_file.stem

            # Request new upload URL for this run_id
            response = requests.post(
                f"{api_url}/v1/traces/init",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"run_id": run_id},
                timeout=10,
            )

            if response.status_code != 200:
                # HTTP 422 typically means invalid run_id (e.g., test files)
                # Skip silently for 422, but log other errors
                if response.status_code == 422:
                    # Likely a test file or invalid run_id, skip silently
                    continue
                print(f"❌ Failed to get upload URL for {run_id}: HTTP {response.status_code}")
                continue

            data = response.json()
            upload_url = data.get("upload_url")

            if not upload_url:
                print(f"❌ Upload URL missing for {run_id}")
                continue

            # Read and compress trace file
            with open(trace_file, "rb") as f:
                trace_data = f.read()

            compressed_data = gzip.compress(trace_data)

            # Upload to cloud
            upload_response = requests.put(
                upload_url,
                data=compressed_data,
                headers={
                    "Content-Type": "application/x-gzip",
                    "Content-Encoding": "gzip",
                },
                timeout=60,
            )

            if upload_response.status_code == 200:
                print(f"✅ Uploaded orphaned trace: {run_id}")
                # Delete file on successful upload
                try:
                    os.remove(trace_file)
                except Exception:
                    pass  # Ignore cleanup errors
            else:
                print(f"❌ Failed to upload {run_id}: HTTP {upload_response.status_code}")

        except requests.exceptions.Timeout:
            print(f"❌ Timeout uploading {trace_file.name}")
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection error uploading {trace_file.name}")
        except Exception as e:
            print(f"❌ Error uploading {trace_file.name}: {e}")
