"""
Tracer factory with automatic tier detection.

Provides convenient factory function for creating tracers with cloud upload support.
"""

import uuid
from pathlib import Path
from typing import Optional

import requests

from sentience.cloud_tracing import CloudTraceSink
from sentience.tracing import JsonlTraceSink, Tracer


def create_tracer(
    api_key: str | None = None,
    run_id: str | None = None,
    api_url: str = "https://api.sentienceapi.com",
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

    # 1. Try to initialize Cloud Sink (Pro/Enterprise tier)
    if api_key:
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
                        sink=CloudTraceSink(upload_url=upload_url),
                    )
                else:
                    print("⚠️  [Sentience] Cloud init response missing upload_url")
                    print("   Falling back to local-only tracing")

            elif response.status_code == 403:
                print("⚠️  [Sentience] Cloud tracing requires Pro tier")
                print("   Falling back to local-only tracing")
            else:
                print(f"⚠️  [Sentience] Cloud init failed: HTTP {response.status_code}")
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
