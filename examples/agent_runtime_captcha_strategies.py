import asyncio
import os

from sentience import (
    AgentRuntime,
    AsyncSentienceBrowser,
    CaptchaOptions,
    ExternalSolver,
    HumanHandoffSolver,
    VisionSolver,
)
from sentience.tracing import JsonlTraceSink, Tracer


async def notify_webhook(ctx) -> None:
    # Example hook: send context to your system (no solver logic in Sentience).
    # Replace with your own client / queue / webhook call.
    print(f"[captcha] external resolver notified: url={ctx.url} run_id={ctx.run_id}")


async def main() -> None:
    tracer = Tracer(run_id="captcha-demo", sink=JsonlTraceSink("trace.jsonl"))

    async with AsyncSentienceBrowser() as browser:
        page = await browser.new_page()
        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser,
            page=page,
            tracer=tracer,
        )

        # Option 1: Human-in-loop
        runtime.set_captcha_options(
            CaptchaOptions(policy="callback", handler=HumanHandoffSolver())
        )

        # Option 2: Vision-only verification (no actions)
        runtime.set_captcha_options(
            CaptchaOptions(policy="callback", handler=VisionSolver())
        )

        # Option 3: External resolver orchestration
        runtime.set_captcha_options(
            CaptchaOptions(policy="callback", handler=ExternalSolver(lambda ctx: notify_webhook(ctx)))
        )

        await page.goto(os.environ.get("CAPTCHA_TEST_URL", "https://example.com"))
        runtime.begin_step("Captcha-aware snapshot")
        await runtime.snapshot()


if __name__ == "__main__":
    asyncio.run(main())
