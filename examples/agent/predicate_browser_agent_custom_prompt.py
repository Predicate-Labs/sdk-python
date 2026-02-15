"""
Example: PredicateBrowserAgent with compact prompt customization.

This shows how to override the compact prompt used for action proposal.

Usage:
  python examples/agent/predicate_browser_agent_custom_prompt.py
"""

import asyncio
import os

from predicate import AsyncSentienceBrowser, PredicateBrowserAgent, PredicateBrowserAgentConfig
from predicate.agent_runtime import AgentRuntime
from predicate.llm_provider import LLMProvider, LLMResponse
from predicate.models import Snapshot
from predicate.runtime_agent import RuntimeStep
from predicate.tracing import JsonlTraceSink, Tracer


class RecordingProvider(LLMProvider):
    """
    Example provider that records the prompts it receives.

    Swap this for OpenAIProvider / AnthropicProvider / DeepInfraProvider / LocalLLMProvider in real usage.
    """

    def __init__(self, action: str = "FINISH()"):
        super().__init__(model="recording-provider")
        self._action = action
        self.last_system: str | None = None
        self.last_user: str | None = None

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        _ = kwargs
        self.last_system = system_prompt
        self.last_user = user_prompt
        return LLMResponse(content=self._action, model_name=self.model_name)

    def supports_json_mode(self) -> bool:
        return False

    @property
    def model_name(self) -> str:
        return "recording-provider"


def compact_prompt_builder(
    task_goal: str,
    step_goal: str,
    dom_context: str,
    snap: Snapshot,
    history_summary: str,
) -> tuple[str, str]:
    _ = snap
    system = (
        "You are a web automation executor.\n"
        "Return ONLY ONE action in this format:\n"
        "- CLICK(id)\n"
        '- TYPE(id, "text")\n'
        "- PRESS('key')\n"
        "- FINISH()\n"
        "No prose."
    )
    # Optional: aggressively control token usage by truncating DOM context.
    dom_context = dom_context[:4000]
    user = (
        f"TASK GOAL:\n{task_goal}\n\n"
        + (f"RECENT STEPS:\n{history_summary}\n\n" if history_summary else "")
        + f"STEP GOAL:\n{step_goal}\n\n"
        f"DOM CONTEXT:\n{dom_context}\n"
    )
    return system, user


async def main() -> None:
    run_id = "predicate-browser-agent-custom-prompt"
    tracer = Tracer(run_id=run_id, sink=JsonlTraceSink(f"traces/{run_id}.jsonl"))

    api_key = os.environ.get("PREDICATE_API_KEY") or os.environ.get("SENTIENCE_API_KEY")

    async with AsyncSentienceBrowser(api_key=api_key, headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")

        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser, page=page, tracer=tracer
        )

        executor = RecordingProvider(action="FINISH()")

        agent = PredicateBrowserAgent(
            runtime=runtime,
            executor=executor,
            config=PredicateBrowserAgentConfig(
                history_last_n=2,
                compact_prompt_builder=compact_prompt_builder,
            ),
        )

        out = await agent.step(
            task_goal="Open example.com",
            step=RuntimeStep(goal="Take no action; just finish"),
        )
        print(f"step ok: {out.ok}")
        print("--- prompt preview (system) ---")
        print((executor.last_system or "")[:300])
        print("--- prompt preview (user) ---")
        print((executor.last_user or "")[:300])

    tracer.close()


if __name__ == "__main__":
    asyncio.run(main())

