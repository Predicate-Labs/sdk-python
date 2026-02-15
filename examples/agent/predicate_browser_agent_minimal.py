"""
Example: PredicateBrowserAgent minimal demo.

PredicateBrowserAgent is a higher-level, browser-use-like wrapper over:
AgentRuntime + RuntimeAgent (snapshot-first action proposal + execution + verification).

Usage:
  python examples/agent/predicate_browser_agent_minimal.py
"""

import asyncio
import os

from predicate import AsyncSentienceBrowser, PredicateBrowserAgent, PredicateBrowserAgentConfig
from predicate.agent_runtime import AgentRuntime
from predicate.llm_provider import LLMProvider, LLMResponse
from predicate.runtime_agent import RuntimeStep, StepVerification
from predicate.tracing import JsonlTraceSink, Tracer
from predicate.verification import exists, url_contains


class FixedActionProvider(LLMProvider):
    """Tiny in-process provider for examples/tests."""

    def __init__(self, action: str):
        super().__init__(model="fixed-action")
        self._action = action

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        _ = system_prompt, user_prompt, kwargs
        return LLMResponse(content=self._action, model_name=self.model_name)

    def supports_json_mode(self) -> bool:
        return False

    @property
    def model_name(self) -> str:
        return "fixed-action"


async def main() -> None:
    run_id = "predicate-browser-agent-minimal"
    tracer = Tracer(run_id=run_id, sink=JsonlTraceSink(f"traces/{run_id}.jsonl"))

    api_key = os.environ.get("PREDICATE_API_KEY") or os.environ.get("SENTIENCE_API_KEY")

    async with AsyncSentienceBrowser(api_key=api_key, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")

        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser, page=page, tracer=tracer
        )

        # For a "real" run, swap this for OpenAIProvider / AnthropicProvider / DeepInfraProvider / LocalLLMProvider.
        executor = FixedActionProvider("FINISH()")

        agent = PredicateBrowserAgent(
            runtime=runtime,
            executor=executor,
            config=PredicateBrowserAgentConfig(
                # Keep a tiny, bounded LLM-facing step history (0 disables history entirely).
                history_last_n=2,
            ),
        )

        steps = [
            RuntimeStep(
                goal="Verify Example Domain is loaded",
                verifications=[
                    StepVerification(
                        predicate=url_contains("example.com"),
                        label="url_contains_example",
                        required=True,
                        eventually=True,
                        timeout_s=5.0,
                    ),
                    StepVerification(
                        predicate=exists("role=heading"),
                        label="has_heading",
                        required=True,
                        eventually=True,
                        timeout_s=5.0,
                    ),
                ],
                max_snapshot_attempts=2,
                snapshot_limit_base=60,
            )
        ]

        ok = await agent.run(task_goal="Open example.com and verify", steps=steps)
        print(f"run ok: {ok}")

    tracer.close()
    print(f"trace written to traces/{run_id}.jsonl")


if __name__ == "__main__":
    asyncio.run(main())

