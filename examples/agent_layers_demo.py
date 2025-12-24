"""
Demonstration of all three abstraction layers in Sentience SDK

Layer 1: Direct SDK (Full Control)
Layer 2: SentienceAgent (Technical Commands)
Layer 3: ConversationalAgent (Natural Language)

This script shows how the same task can be accomplished at different abstraction levels.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def demo_layer1_direct_sdk():
    """
    Layer 1: Direct SDK Usage
    - Full control over every action
    - Requires knowing exact element selectors
    - 50+ lines of code for typical automation
    """
    print("\n" + "="*70)
    print("LAYER 1: Direct SDK Usage (Full Control)")
    print("="*70)

    from sentience import SentienceBrowser, snapshot, find, click, type_text, press

    with SentienceBrowser(headless=False) as browser:
        # Navigate
        browser.page.goto("https://google.com")

        # Get snapshot
        snap = snapshot(browser)

        # Find search box manually
        search_box = find(snap, "role=searchbox")
        if not search_box:
            search_box = find(snap, "role=textbox")

        # Click search box
        click(browser, search_box.id)

        # Type query
        type_text(browser, search_box.id, "magic mouse")

        # Press Enter
        press(browser, "Enter")

        print("\n✅ Layer 1 Demo Complete")
        print("   Code required: ~20 lines")
        print("   Technical knowledge: High")
        print("   Flexibility: Maximum")


def demo_layer2_sentience_agent():
    """
    Layer 2: SentienceAgent (Technical Commands)
    - High-level commands with LLM intelligence
    - No need to know selectors
    - 15 lines of code for typical automation
    """
    print("\n" + "="*70)
    print("LAYER 2: SentienceAgent (Technical Commands)")
    print("="*70)

    from sentience import SentienceBrowser, SentienceAgent
    from sentience.llm_provider import OpenAIProvider

    # Initialize
    browser = SentienceBrowser(headless=False)
    llm = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini")
    agent = SentienceAgent(browser, llm, verbose=True)

    with browser:
        browser.page.goto("https://google.com")

        # Execute technical commands
        agent.act("Click the search box")
        agent.act("Type 'magic mouse' into the search field")
        agent.act("Press Enter key")

        print("\n✅ Layer 2 Demo Complete")
        print("   Code required: ~10 lines")
        print("   Technical knowledge: Medium")
        print("   Flexibility: High")
        # Use new TokenStats dataclass
        stats = agent.get_token_stats()
        print(f"   Tokens used: {stats.total_tokens}")


def demo_layer3_conversational_agent():
    """
    Layer 3: ConversationalAgent (Natural Language)
    - Pure natural language interface
    - Automatic planning and execution
    - 3 lines of code for typical automation
    """
    print("\n" + "="*70)
    print("LAYER 3: ConversationalAgent (Natural Language)")
    print("="*70)

    from sentience import SentienceBrowser, ConversationalAgent
    from sentience.llm_provider import OpenAIProvider

    # Initialize
    browser = SentienceBrowser(headless=False)
    llm = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o")
    agent = ConversationalAgent(browser, llm, verbose=True)

    with browser:
        # Execute in natural language (agent plans and executes automatically)
        response = agent.execute("Search for magic mouse on google.com")

        print("\n✅ Layer 3 Demo Complete")
        print("   Code required: ~5 lines")
        print("   Technical knowledge: None")
        print("   Flexibility: Medium")
        print(f"   Agent Response: {response}")


def demo_layer3_with_local_llm():
    """
    Layer 3 with Local LLM (Zero Cost)
    - Uses local Qwen 2.5 3B model
    - No API costs
    - Runs on your hardware
    """
    print("\n" + "="*70)
    print("LAYER 3: ConversationalAgent with Local LLM (Zero Cost)")
    print("="*70)

    from sentience import SentienceBrowser, ConversationalAgent
    from sentience.llm_provider import LocalLLMProvider

    # Initialize with local LLM
    browser = SentienceBrowser(headless=False)
    llm = LocalLLMProvider(
        model_name="Qwen/Qwen2.5-3B-Instruct",
        device="auto",  # Use CUDA if available
        load_in_4bit=True  # Save memory with quantization
    )
    agent = ConversationalAgent(browser, llm, verbose=True)

    with browser:
        # Execute in natural language
        response = agent.execute("Go to google.com and search for python tutorials")

        print("\n✅ Layer 3 with Local LLM Demo Complete")
        print("   API Cost: $0 (runs locally)")
        print("   Privacy: 100% (no data sent to cloud)")
        print(f"   Agent Response: {response}")


def demo_comparison():
    """
    Side-by-side comparison of all layers
    """
    print("\n" + "="*70)
    print("COMPARISON: All Three Layers")
    print("="*70)

    comparison_table = """
    | Feature                  | Layer 1 (SDK)    | Layer 2 (Agent)  | Layer 3 (Conversational) |
    |--------------------------|------------------|------------------|--------------------------|
    | Lines of code            | 50+              | 15               | 3-5                      |
    | Technical knowledge      | High             | Medium           | None                     |
    | Requires selectors?      | Yes              | No               | No                       |
    | LLM required?            | No               | Yes              | Yes                      |
    | Cost per action          | $0               | ~$0.005          | ~$0.010                  |
    | Speed                    | Fastest          | Fast             | Medium                   |
    | Error handling           | Manual           | Auto-retry       | Auto-recovery            |
    | Multi-step planning      | Manual           | Manual           | Automatic                |
    | Natural language I/O     | No               | Commands only    | Full conversation        |
    | Best for                 | Production       | AI developers    | End users                |
    """

    print(comparison_table)


def main():
    """Run all demos"""
    print("\n" + "="*70)
    print("SENTIENCE SDK: Multi-Layer Abstraction Demo")
    print("="*70)
    print("\nThis demo shows how to use the SDK at different abstraction levels:")
    print("  1. Layer 1: Direct SDK (maximum control)")
    print("  2. Layer 2: SentienceAgent (technical commands)")
    print("  3. Layer 3: ConversationalAgent (natural language)")
    print("\nChoose which demo to run:")
    print("  1 - Layer 1: Direct SDK")
    print("  2 - Layer 2: SentienceAgent")
    print("  3 - Layer 3: ConversationalAgent (OpenAI)")
    print("  4 - Layer 3: ConversationalAgent (Local LLM)")
    print("  5 - Show comparison table")
    print("  0 - Exit")

    choice = input("\nEnter your choice (0-5): ").strip()

    if choice == "1":
        demo_layer1_direct_sdk()
    elif choice == "2":
        if not os.getenv("OPENAI_API_KEY"):
            print("\n❌ Error: OPENAI_API_KEY not set")
            return
        demo_layer2_sentience_agent()
    elif choice == "3":
        if not os.getenv("OPENAI_API_KEY"):
            print("\n❌ Error: OPENAI_API_KEY not set")
            return
        demo_layer3_conversational_agent()
    elif choice == "4":
        demo_layer3_with_local_llm()
    elif choice == "5":
        demo_comparison()
    elif choice == "0":
        print("Goodbye!")
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
