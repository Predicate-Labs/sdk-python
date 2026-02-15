"""
Example: PredicateBrowserAgent + Playwright video recording (recommended approach).

Video recording is a *Playwright context feature* (record_video_dir), not a PredicateBrowserAgent knob.
This example shows how to:
1) create a Playwright context with video recording enabled
2) wrap the existing page with AsyncSentienceBrowser.from_page(...)
3) use AgentRuntime + PredicateBrowserAgent normally

Usage:
  python examples/agent/predicate_browser_agent_video_recording_playwright.py
"""

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

from predicate import AsyncSentienceBrowser, PredicateBrowserAgent, PredicateBrowserAgentConfig
from predicate.agent_runtime import AgentRuntime
from predicate.llm_provider import LLMProvider, LLMResponse
from predicate.runtime_agent import RuntimeStep


class FixedActionProvider(LLMProvider):
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
    api_key = os.environ.get("PREDICATE_API_KEY") or os.environ.get("SENTIENCE_API_KEY")

    recordings_dir = Path("recordings")
    recordings_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            record_video_dir=str(recordings_dir),
            record_video_size={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        # Wrap existing Playwright page.
        sentience_browser = await AsyncSentienceBrowser.from_page(
            page, api_key=api_key
        )

        try:
            await page.goto("https://example.com")
            await page.wait_for_load_state("networkidle")

            runtime = await AgentRuntime.from_sentience_browser(
                browser=sentience_browser, page=page, tracer=None
            )

            agent = PredicateBrowserAgent(
                runtime=runtime,
                executor=FixedActionProvider("FINISH()"),
                config=PredicateBrowserAgentConfig(history_last_n=0),
            )

            out = await agent.step(
                task_goal="Open example.com",
                step=RuntimeStep(goal="Finish immediately"),
            )
            print(f"step ok: {out.ok}")
            print(f"videos will be saved under: {recordings_dir.resolve()}")
        finally:
            # Close the Playwright context to flush the video.
            try:
                await context.close()
            finally:
                await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

