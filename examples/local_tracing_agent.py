"""
Example: Agent with Cloud Tracing

Demonstrates how to use cloud tracing with SentienceAgent to upload traces
and screenshots to cloud storage for remote viewing and analysis.

Requirements:
- Pro or Enterprise tier API key (SENTIENCE_API_KEY)
- OpenAI API key (OPENAI_API_KEY) for LLM

Usage:
    python examples/cloud_tracing_agent.py
"""

import os

from predicate import SentienceAgent, SentienceBrowser
from predicate.agent_config import AgentConfig
from predicate.llm_provider import OpenAIProvider
from predicate.tracer_factory import create_tracer


def main():
    # Get API keys from environment
    sentience_key = os.environ.get("SENTIENCE_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not sentience_key:
        print("❌ Error: SENTIENCE_API_KEY not set")
        print("   Cloud tracing requires Pro or Enterprise tier")
        print("   Get your API key at: https://sentience.studio")
        return

    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not set")
        return

    print("🚀 Starting Agent with Cloud Tracing Demo\n")

    # 1. Create tracer with automatic tier detection
    # If api_key is Pro/Enterprise, uses CloudTraceSink
    # If api_key is missing/invalid, falls back to local JsonlTraceSink
    run_id = "cloud-tracing-demo"
    # local storage tracer, is upload_tracer is True and api_key is provided, will upload to cloud
    tracer = create_tracer(api_key=sentience_key, run_id=run_id, upload_trace=False)

    print(f"🆔 Run ID: {run_id}\n")

    # 2. Configure agent with screenshot capture
    config = AgentConfig(
        snapshot_limit=50,
        capture_screenshots=True,  # Enable screenshot capture
        screenshot_format="jpeg",  # JPEG for smaller file size
        screenshot_quality=80,  # 80% quality (good balance)
    )

    # 3. Create browser and LLM
    browser = SentienceBrowser(api_key=sentience_key, headless=False)
    llm = OpenAIProvider(api_key=openai_key, model="gpt-4o-mini")

    # 4. Create agent with tracer
    agent = SentienceAgent(browser, llm, tracer=tracer, config=config)

    try:
        # 5. Navigate and execute agent actions
        print("🌐 Navigating to Google...\n")
        browser.start()
        browser.page.goto("https://www.google.com")
        browser.page.wait_for_load_state("networkidle")

        # All actions are automatically traced!
        print("📝 Executing agent actions (all automatically traced)...\n")
        agent.act("Click the search box")
        agent.act("Type 'Sentience AI agent SDK' into the search field")
        agent.act("Press Enter key")

        # Wait for results
        import time

        time.sleep(2)

        agent.act("Click the first non-ad search result")

        print("\n✅ Agent execution complete!")

        # 6. Get token usage stats
        stats = agent.get_token_stats()
        print("\n📊 Token Usage:")
        print(f"   Total tokens: {stats.total_tokens}")
        print(f"   Prompt tokens: {stats.total_prompt_tokens}")
        print(f"   Completion tokens: {stats.total_completion_tokens}")

    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        raise

    finally:
        # 7. Close tracer (uploads to cloud)
        print("\n📤 Uploading trace to cloud...")
        try:
            tracer.close(blocking=True)  # Wait for upload to complete
            print("✅ Trace uploaded successfully!")
            print(f"   View at: https://studio.sentienceapi.com (run_id: {run_id})")
        except Exception as e:
            print(f"⚠️  Upload failed: {e}")
            print(f"   Trace preserved locally at: ~/.sentience/traces/pending/{run_id}.jsonl")

        browser.close()


if __name__ == "__main__":
    main()
