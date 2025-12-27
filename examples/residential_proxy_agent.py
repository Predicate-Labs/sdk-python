"""
Example: Using Residential Proxies with SentienceAgent

Demonstrates how to configure and use residential proxies with SentienceBrowser
for web automation while protecting your real IP address.

Proxy Support:
- HTTP, HTTPS, and SOCKS5 proxies
- Authentication (username/password)
- Environment variable configuration
- WebRTC leak protection (automatic)
- Self-signed SSL certificate handling (automatic for proxies)

HTTPS Certificate Handling:
When using a proxy, the SDK automatically sets `ignore_https_errors=True` to handle
residential proxies that use self-signed SSL certificates. This is common with proxy
providers and prevents `ERR_CERT_AUTHORITY_INVALID` errors.

Note: HTTPS errors are ONLY ignored when a proxy is configured - normal browsing
(without proxy) maintains full SSL certificate validation for security.

Usage:
    # Method 1: Direct proxy argument
    python examples/residential_proxy_agent.py

    # Method 2: Environment variable
    export SENTIENCE_PROXY="http://user:pass@proxy.example.com:8080"
    python examples/residential_proxy_agent.py

Requirements:
- OpenAI API key (OPENAI_API_KEY) for LLM
- Optional: Sentience API key (SENTIENCE_API_KEY) for Pro/Enterprise features
- Optional: Proxy server credentials
"""

import os

from sentience import SentienceAgent, SentienceBrowser
from sentience.agent_config import AgentConfig
from sentience.llm_provider import OpenAIProvider


def example_proxy_direct_argument():
    """Example 1: Configure proxy via direct argument"""
    print("=" * 60)
    print("Example 1: Proxy via Direct Argument")
    print("=" * 60)

    # Configure your proxy credentials here
    # Supported formats:
    # - HTTP:   http://user:pass@proxy.example.com:8080
    # - HTTPS:  https://user:pass@proxy.example.com:8443
    # - SOCKS5: socks5://user:pass@proxy.example.com:1080
    # - No auth: http://proxy.example.com:8080

    proxy_url = "http://user:pass@proxy.example.com:8080"

    # Create browser with proxy
    browser = SentienceBrowser(
        proxy=proxy_url,  # Direct proxy configuration
        headless=False,  # Set to True for production
    )

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not set")
        return

    llm = OpenAIProvider(api_key=openai_key, model="gpt-4o-mini")
    agent = SentienceAgent(browser, llm, verbose=True)

    try:
        print("\n🚀 Starting browser with proxy...")
        browser.start()

        print("🌐 Navigating to IP check service...")
        browser.page.goto("https://api.ipify.org?format=json")
        browser.page.wait_for_load_state("networkidle")

        # Verify proxy is working by checking IP
        print("\n✅ Browser started successfully with proxy!")
        print("   You should see the proxy's IP address in the browser\n")

        # Example: Use agent to interact with pages through proxy
        browser.page.goto("https://www.google.com")
        browser.page.wait_for_load_state("networkidle")

        agent.act("Click the search box")
        agent.act('Type "my ip address" into the search field')
        agent.act("Press Enter key")

        import time

        time.sleep(2)

        print("\n✅ Agent execution complete!")
        print("   All traffic was routed through the proxy")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        browser.close()


def example_proxy_environment_variable():
    """Example 2: Configure proxy via environment variable"""
    print("=" * 60)
    print("Example 2: Proxy via Environment Variable")
    print("=" * 60)

    # Check if SENTIENCE_PROXY is set
    proxy_from_env = os.environ.get("SENTIENCE_PROXY")

    if not proxy_from_env:
        print("\n⚠️  SENTIENCE_PROXY environment variable not set")
        print("   Set it with:")
        print('   export SENTIENCE_PROXY="http://user:pass@proxy.example.com:8080"')
        print("\n   Skipping this example...\n")
        return

    print(f"\n🔧 Using proxy from environment: {proxy_from_env.split('@')[0]}@***")

    # Create browser without explicit proxy argument
    # It will automatically use SENTIENCE_PROXY from environment
    browser = SentienceBrowser(headless=False)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not set")
        return

    llm = OpenAIProvider(api_key=openai_key, model="gpt-4o-mini")
    agent = SentienceAgent(browser, llm, verbose=True)

    try:
        print("\n🚀 Starting browser with proxy from environment...")
        browser.start()

        print("🌐 Navigating to IP check service...")
        browser.page.goto("https://api.ipify.org?format=json")
        browser.page.wait_for_load_state("networkidle")

        print("\n✅ Browser started successfully with environment proxy!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        browser.close()


def example_proxy_types():
    """Example 3: Different proxy types (HTTP, HTTPS, SOCKS5)"""
    print("=" * 60)
    print("Example 3: Different Proxy Types")
    print("=" * 60)

    proxy_examples = {
        "HTTP": "http://user:pass@proxy.example.com:8080",
        "HTTPS": "https://user:pass@secure-proxy.example.com:8443",
        "SOCKS5": "socks5://user:pass@socks-proxy.example.com:1080",
        "No Auth": "http://proxy.example.com:8080",  # Without credentials
    }

    print("\n📋 Supported proxy formats:")
    for proxy_type, example_url in proxy_examples.items():
        # Hide credentials in output
        display_url = example_url.replace("user:pass@", "user:***@")
        print(f"   {proxy_type:10s}: {display_url}")

    print("\n💡 To use a specific proxy type, pass it to SentienceBrowser:")
    print('   browser = SentienceBrowser(proxy="socks5://user:pass@proxy.com:1080")')


def example_webrtc_leak_protection():
    """Example 4: WebRTC leak protection (automatic)"""
    print("=" * 60)
    print("Example 4: WebRTC Leak Protection (Automatic)")
    print("=" * 60)

    print("\n🔒 WebRTC leak protection is AUTOMATICALLY enabled for all users!")
    print("   This prevents your real IP from leaking via WebRTC when using proxies.")
    print("\n   Browser flags applied:")
    print("   - --disable-features=WebRtcHideLocalIpsWithMdns")
    print("   - --force-webrtc-ip-handling-policy=disable_non_proxied_udp")
    print("\n🔒 HTTPS certificate handling (when using proxy):")
    print("   - ignore_https_errors=True (automatically set)")
    print("   - Handles residential proxies with self-signed SSL certificates")
    print("   - Prevents ERR_CERT_AUTHORITY_INVALID errors")
    print("   - Only active when proxy is configured (normal browsing unaffected)")
    print("\n   No additional configuration needed - it just works!\n")


def example_proxy_with_cloud_tracing():
    """Example 5: Combine proxy with cloud tracing"""
    print("=" * 60)
    print("Example 5: Proxy + Cloud Tracing")
    print("=" * 60)

    sentience_key = os.environ.get("SENTIENCE_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not sentience_key:
        print("\n⚠️  SENTIENCE_API_KEY not set")
        print("   Cloud tracing requires Pro or Enterprise tier")
        print("   Get your API key at: https://sentience.studio")
        print("\n   Skipping this example...\n")
        return

    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not set")
        return

    from sentience.tracer_factory import create_tracer

    # Create tracer for cloud upload
    run_id = "proxy-with-tracing-demo"
    tracer = create_tracer(api_key=sentience_key, run_id=run_id)

    # Configure proxy
    proxy_url = "http://user:pass@proxy.example.com:8080"

    # Create browser with BOTH proxy and API key
    browser = SentienceBrowser(api_key=sentience_key, proxy=proxy_url, headless=False)

    llm = OpenAIProvider(api_key=openai_key, model="gpt-4o-mini")

    # Configure agent with screenshots + tracer
    config = AgentConfig(
        snapshot_limit=50,
        capture_screenshots=True,
        screenshot_format="jpeg",
        screenshot_quality=80,
    )

    agent = SentienceAgent(browser, llm, tracer=tracer, config=config)

    try:
        print("\n🚀 Starting browser with proxy + cloud tracing...")
        browser.start()

        print("🌐 Executing agent actions (all traced)...")
        browser.page.goto("https://www.google.com")
        browser.page.wait_for_load_state("networkidle")

        agent.act("Click the search box")
        agent.act('Type "sentience AI SDK" into the search field')
        agent.act("Press Enter key")

        print("\n✅ Agent execution complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        # Upload trace to cloud
        print("\n📤 Uploading trace to cloud...")
        try:
            tracer.close(blocking=True)
            print("✅ Trace uploaded successfully!")
            print(f"   View at: https://studio.sentienceapi.com (run_id: {run_id})")
        except Exception as e:
            print(f"⚠️  Upload failed: {e}")

        browser.close()


def example_no_proxy_baseline():
    """Example 0: Baseline - Run agent without proxy to show it works"""
    print("=" * 60)
    print("Example 0: Baseline (No Proxy)")
    print("=" * 60)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not set")
        print("   Set it with: export OPENAI_API_KEY='your-key-here'")
        return

    # Create browser WITHOUT proxy (baseline)
    browser = SentienceBrowser(headless=False)
    llm = OpenAIProvider(api_key=openai_key, model="gpt-4o-mini")
    agent = SentienceAgent(browser, llm, verbose=True)

    try:
        print("\n🚀 Starting browser (without proxy)...")
        browser.start()

        print("🌐 Navigating to Google...")
        browser.page.goto("https://www.google.com")
        browser.page.wait_for_load_state("networkidle")

        print("\n🤖 Running agent actions...")
        agent.act("Click the search box")
        agent.act('Type "what is my ip" into the search field')
        agent.act("Press Enter key")

        import time

        time.sleep(3)

        print("\n✅ Agent execution complete!")
        print("   This shows your REAL IP address (no proxy)")
        print("\n💡 To use a proxy:")
        print("   1. Get proxy credentials from your provider")
        print("   2. Run example_proxy_direct_argument() or set SENTIENCE_PROXY")
        print("      You should see a DIFFERENT IP (the proxy's IP)")

        stats = agent.get_token_stats()
        print("\n📊 Token Usage:")
        print(f"   Prompt tokens: {stats.total_prompt_tokens}")
        print(f"   Completion tokens: {stats.total_completion_tokens}")
        print(f"   Total tokens: {stats.total_tokens}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        browser.close()


def main():
    """Run all proxy examples"""
    print("\n" + "=" * 60)
    print("Sentience SDK - Residential Proxy Examples")
    print("=" * 60 + "\n")

    # Run examples
    # Note: Uncomment the examples you want to run

    # Example 0: Baseline (no proxy) - WORKS OUT OF THE BOX
    example_no_proxy_baseline()

    # Example 1: Direct argument (configure proxy_url first)
    # example_proxy_direct_argument()

    # Example 2: Environment variable (set SENTIENCE_PROXY first)
    # example_proxy_environment_variable()

    # Example 3: Show supported proxy types
    # example_proxy_types()

    # Example 4: WebRTC leak protection info
    # example_webrtc_leak_protection()

    # Example 5: Proxy + Cloud Tracing (requires API key)
    # example_proxy_with_cloud_tracing()

    print("\n" + "=" * 60)
    print("Examples Complete!")
    print("=" * 60)
    print("\n💡 Tips:")
    print("   - Example 0 shows baseline (no proxy) - works immediately")
    print("   - Uncomment other examples after configuring proxy credentials")
    print("   - Set SENTIENCE_PROXY environment variable for easy configuration")
    print("   - WebRTC leak protection is automatic - no configuration needed")
    print("   - Combine with cloud tracing for full visibility\n")


if __name__ == "__main__":
    main()
