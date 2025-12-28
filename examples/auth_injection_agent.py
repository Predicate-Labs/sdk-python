"""
Example: Using Authentication Session Injection with SentienceAgent

Demonstrates how to inject pre-recorded authentication sessions (cookies + localStorage)
into SentienceBrowser to start agents already logged in, bypassing login screens and CAPTCHAs.

Two Workflows:
1. Inject Pre-recorded Session: Load a saved session from a JSON file
2. Persistent Sessions: Use a user data directory to persist sessions across runs

Benefits:
- Bypass login screens and CAPTCHAs
- Save tokens and reduce costs (no login steps needed)
- Maintain stateful sessions across agent runs
- Act as authenticated users (access "My Orders", "My Account", etc.)

Usage:
    # Workflow 1: Inject pre-recorded session
    python examples/auth_injection_agent.py --storage-state auth.json

    # Workflow 2: Use persistent user data directory
    python examples/auth_injection_agent.py --user-data-dir ./chrome_profile

Requirements:
- OpenAI API key (OPENAI_API_KEY) for LLM
- Optional: Sentience API key (SENTIENCE_API_KEY) for Pro/Enterprise features
- Optional: Pre-saved storage state file (auth.json) or user data directory
"""

import argparse
import os

from sentience import SentienceAgent, SentienceBrowser, save_storage_state
from sentience.llm_provider import OpenAIProvider


def example_inject_storage_state():
    """Example 1: Inject pre-recorded session from file"""
    print("=" * 60)
    print("Example 1: Inject Pre-recorded Session")
    print("=" * 60)

    # Path to saved storage state file
    # You can create this file using save_storage_state() after logging in manually
    storage_state_file = "auth.json"

    if not os.path.exists(storage_state_file):
        print(f"\n⚠️  Storage state file not found: {storage_state_file}")
        print("\n   To create this file:")
        print("   1. Log in manually to your target website")
        print("   2. Use save_storage_state() to save the session")
        print("\n   Example code:")
        print("   ```python")
        print("   from sentience import SentienceBrowser, save_storage_state")
        print("   browser = SentienceBrowser()")
        print("   browser.start()")
        print("   browser.goto('https://example.com')")
        print("   # ... log in manually ...")
        print("   save_storage_state(browser.context, 'auth.json')")
        print("   ```")
        print("\n   Skipping this example...\n")
        return

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not set")
        return

    # Create browser with storage state injection
    browser = SentienceBrowser(
        storage_state=storage_state_file,  # Inject saved session
        headless=False,
    )

    llm = OpenAIProvider(api_key=openai_key, model="gpt-4o-mini")
    agent = SentienceAgent(browser, llm, verbose=True)

    try:
        print("\n🚀 Starting browser with injected session...")
        browser.start()

        print("🌐 Navigating to authenticated page...")
        # Agent starts already logged in!
        browser.page.goto("https://example.com/orders")  # Or your authenticated page
        browser.page.wait_for_load_state("networkidle")

        print("\n✅ Browser started with pre-injected authentication!")
        print("   Agent can now access authenticated pages without logging in")

        # Example: Use agent on authenticated pages
        agent.act("Show me my recent orders")
        agent.act("Click on the first order")

        print("\n✅ Agent execution complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        browser.close()


def example_persistent_session():
    """Example 2: Use persistent user data directory"""
    print("=" * 60)
    print("Example 2: Persistent Session (User Data Directory)")
    print("=" * 60)

    # Directory to persist browser session
    user_data_dir = "./chrome_profile"

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not set")
        return

    # Create browser with persistent user data directory
    browser = SentienceBrowser(
        user_data_dir=user_data_dir,  # Persist cookies and localStorage
        headless=False,
    )

    llm = OpenAIProvider(api_key=openai_key, model="gpt-4o-mini")
    agent = SentienceAgent(browser, llm, verbose=True)

    try:
        print("\n🚀 Starting browser with persistent session...")
        browser.start()

        # Check if this is first run (no existing session)
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # First run: Agent needs to log in
        # Second run: Agent is already logged in (cookies persist)
        if os.path.exists(user_data_dir):
            print("\n✅ Using existing session from previous run")
            print("   Cookies and localStorage are loaded automatically")
        else:
            print("\n📝 First run - session will be saved after login")
            print("   Next run will automatically use saved session")

        # Example: Log in (first run) or use existing session (subsequent runs)
        agent.act("Click the sign in button")
        agent.act("Type your email into the email field")
        agent.act("Type your password into the password field")
        agent.act("Click the login button")

        print("\n✅ Session will persist in:", user_data_dir)
        print("   Next run will automatically use this session")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        browser.close()


def example_save_storage_state():
    """Example 3: Save current session for later use"""
    print("=" * 60)
    print("Example 3: Save Current Session")
    print("=" * 60)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("❌ Error: OPENAI_API_KEY not set")
        return

    browser = SentienceBrowser(headless=False)
    llm = OpenAIProvider(api_key=openai_key, model="gpt-4o-mini")
    agent = SentienceAgent(browser, llm, verbose=True)

    try:
        print("\n🚀 Starting browser...")
        browser.start()

        print("🌐 Navigate to your target website and log in manually...")
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        print("\n⏸️  Please log in manually in the browser window")
        print("   Press Enter when you're done logging in...")
        input()

        # Save the current session
        storage_state_file = "auth.json"
        save_storage_state(browser.context, storage_state_file)

        print(f"\n✅ Session saved to: {storage_state_file}")
        print("   You can now use this file with storage_state parameter:")
        print(f"   browser = SentienceBrowser(storage_state='{storage_state_file}')")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        browser.close()


def main():
    """Run auth injection examples"""
    parser = argparse.ArgumentParser(description="Auth Injection Examples")
    parser.add_argument(
        "--storage-state",
        type=str,
        help="Path to storage state JSON file to inject",
    )
    parser.add_argument(
        "--user-data-dir",
        type=str,
        help="Path to user data directory for persistent sessions",
    )
    parser.add_argument(
        "--save-session",
        action="store_true",
        help="Save current session to auth.json",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("Sentience SDK - Authentication Session Injection Examples")
    print("=" * 60 + "\n")

    if args.save_session:
        example_save_storage_state()
    elif args.storage_state:
        # Override default file path
        import sys

        sys.modules[__name__].storage_state_file = args.storage_state
        example_inject_storage_state()
    elif args.user_data_dir:
        # Override default directory
        import sys

        sys.modules[__name__].user_data_dir = args.user_data_dir
        example_persistent_session()
    else:
        # Run all examples
        example_save_storage_state()
        print("\n")
        example_inject_storage_state()
        print("\n")
        example_persistent_session()

    print("\n" + "=" * 60)
    print("Examples Complete!")
    print("=" * 60)
    print("\n💡 Tips:")
    print("   - Use storage_state to inject pre-recorded sessions")
    print("   - Use user_data_dir to persist sessions across runs")
    print("   - Save sessions after manual login for reuse")
    print("   - Bypass login screens and CAPTCHAs with valid sessions")
    print("   - Reduce token costs by skipping login steps\n")


if __name__ == "__main__":
    main()
