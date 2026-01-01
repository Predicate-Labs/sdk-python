"""
Example: Basic agent usage (Async version)
Demonstrates SentienceAgentAsync for natural language automation
"""

import asyncio
import os

from sentience.async_api import AsyncSentienceBrowser, SentienceAgentAsync
from sentience.llm_provider import LLMProvider, LLMResponse


# Simple mock LLM provider for demonstration
# In production, use OpenAIProvider, AnthropicProvider, etc.
class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing"""

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        # Simple mock that returns CLICK action
        return LLMResponse(
            content="CLICK(1)",
            model_name="mock-model",
            prompt_tokens=100,
            completion_tokens=10,
            total_tokens=110,
        )

    def supports_json_mode(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return "mock-model"


async def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")

    async with AsyncSentienceBrowser(api_key=api_key, headless=False) as browser:
        # Navigate to a page
        await browser.goto("https://example.com", wait_until="domcontentloaded")

        # Create LLM provider
        # In production, use: llm = OpenAIProvider(api_key="your-key", model="gpt-4o")
        llm = MockLLMProvider()

        # Create agent
        agent = SentienceAgentAsync(browser, llm, verbose=True)

        print("=== Basic Agent Demo ===\n")

        # Example 1: Simple action
        print("1. Executing simple action...")
        try:
            result = await agent.act("Click the first link")
            print(f"   Result: success={result.success}, action={result.action}")
            if result.element_id:
                print(f"   Clicked element ID: {result.element_id}")
        except Exception as e:
            print(f"   Error: {e}")

        print()

        # Example 2: Check history
        print("2. Agent execution history:")
        history = agent.get_history()
        print(f"   Total actions: {len(history)}")
        for i, entry in enumerate(history, 1):
            print(f"   {i}. {entry.goal} -> {entry.action} (success: {entry.success})")

        print()

        # Example 3: Token statistics
        print("3. Token usage statistics:")
        stats = agent.get_token_stats()
        print(f"   Total tokens: {stats.total_tokens}")
        print(f"   Prompt tokens: {stats.total_prompt_tokens}")
        print(f"   Completion tokens: {stats.total_completion_tokens}")

        print()

        # Example 4: Clear history
        print("4. Clearing history...")
        agent.clear_history()
        print(f"   History length after clear: {len(agent.get_history())}")

        print("\n✅ Basic agent demo complete!")
        print("\nNote: This example uses a mock LLM provider.")
        print("In production, use a real LLM provider like OpenAIProvider or AnthropicProvider.")


if __name__ == "__main__":
    asyncio.run(main())
