"""
Example: RuntimeAgent (AgentRuntime-backed) minimal demo.

This demonstrates the verification-first loop:
snapshot -> propose action (structured executor) -> execute -> verify (AgentRuntime predicates)

Usage:
  python examples/runtime_agent_minimal.py
"""

import asyncio

from sentience import AsyncSentienceBrowser
from sentience.agent_runtime import AgentRuntime
from sentience.llm_provider import LLMProvider, LLMResponse
from sentience.runtime_agent import RuntimeAgent, RuntimeStep, StepVerification
from sentience.tracing import JsonlTraceSink, Tracer
from sentience.verification import AssertContext, AssertOutcome, exists, url_contains


class FixedActionProvider(LLMProvider):
    """A tiny in-process provider for examples/tests."""

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
    # Local trace (viewable in Studio if uploaded later).
    run_id = "runtime-agent-minimal"
    tracer = Tracer(run_id=run_id, sink=JsonlTraceSink(f"traces/{run_id}.jsonl"))

    async with AsyncSentienceBrowser(headless=False) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")

        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser, page=page, tracer=tracer
        )

        # Structured executor (for demo, we just return FINISH()).
        executor = FixedActionProvider("FINISH()")

        agent = RuntimeAgent(
            runtime=runtime,
            executor=executor,
            # vision_executor=... (optional)
            # vision_verifier=... (optional, for AgentRuntime assertion vision fallback)
        )

        # One step: no action needed; we just verify structure + URL.
        def has_example_heading(ctx: AssertContext) -> AssertOutcome:
            # Demonstrates custom predicates (you can also use exists/url_contains helpers).
            snap = ctx.snapshot
            ok = bool(
                snap
                and any(
                    (el.role == "heading" and (el.text or "").startswith("Example"))
                    for el in snap.elements
                )
            )
            return AssertOutcome(passed=ok, reason="" if ok else "missing heading", details={})

        step = RuntimeStep(
            goal="Confirm Example Domain page is loaded",
            verifications=[
                StepVerification(
                    predicate=url_contains("example.com"),
                    label="url_contains_example",
                    required=True,
                ),
                StepVerification(
                    predicate=exists("role=heading"), label="has_heading", required=True
                ),
                StepVerification(
                    predicate=has_example_heading, label="heading_text_matches", required=False
                ),
            ],
            max_snapshot_attempts=2,
            snapshot_limit_base=60,
        )

        ok = await agent.run_step(task_goal="Open example.com and verify", step=step)
        print(f"step ok: {ok}")

    tracer.close()
    print(f"trace written to traces/{run_id}.jsonl")


if __name__ == "__main__":
    asyncio.run(main())
