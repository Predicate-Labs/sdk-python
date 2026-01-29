# Sentience Python SDK

> **A verification & control layer for AI agents that operate browsers**

Sentience is built for **AI agent developers** who already use Playwright / CDP / browser-use / LangGraph and care about **flakiness, cost, determinism, evals, and debugging**.

Often described as *Jest for Browser AI Agents* - but applied to end-to-end agent runs (not unit tests).

The core loop is:

> **Agent → Snapshot → Action → Verification → Artifact**

## What Sentience is

- A **verification-first runtime** (`AgentRuntime`) for browser agents
- Treats the browser as an adapter (Playwright / CDP / browser-use); **`AgentRuntime` is the product**
- A **controlled perception** layer (semantic snapshots; pruning/limits; lowers token usage by filtering noise from what models see)
- A **debugging layer** (structured traces + failure artifacts)
- Enables **local LLM small models (3B-7B)** for browser automation (privacy, compliance, and cost control)
- Keeps vision models **optional** (use as a fallback when DOM/snapshot structure falls short, e.g. `<canvas>`)

## What Sentience is not

- Not a browser driver
- Not a Playwright replacement
- Not a vision-first agent framework

## Install

```bash
pip install sentienceapi
playwright install chromium
```

## Conceptual example (why this exists)

In Sentience, agents don’t “hope” an action worked.

- **Every step is gated by verifiable UI assertions**
- If progress can’t be proven, the run **fails with evidence** (trace + artifacts)
- This is how you make runs **reproducible** and **debuggable**, and how you run evals reliably

## Quickstart: a verification-first loop

This is the smallest useful pattern: snapshot → assert → act → assert-done.

```python
import asyncio

from sentience import AgentRuntime, AsyncSentienceBrowser
from sentience.tracing import JsonlTraceSink, Tracer
from sentience.verification import exists, url_contains


async def main() -> None:
    tracer = Tracer(run_id="demo", sink=JsonlTraceSink("trace.jsonl"))

    async with AsyncSentienceBrowser() as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")

        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser,
            page=page,
            tracer=tracer,
        )

        runtime.begin_step("Verify homepage")
        await runtime.snapshot()

        runtime.assert_(url_contains("example.com"), label="on_domain", required=True)
        runtime.assert_(exists("role=heading"), label="has_heading")

        runtime.assert_done(exists("text~'Example'"), label="task_complete")


if __name__ == "__main__":
    asyncio.run(main())
```

## Capabilities (lifecycle guarantees)

### Controlled perception

- **Semantic snapshots** instead of raw DOM dumps
- **Pruning knobs** via `SnapshotOptions` (limit/filter)
- Snapshot diagnostics that help decide when “structure is insufficient”

### Constrained action space

- Action primitives operate on **stable IDs / rects** derived from snapshots
- Optional helpers for ordinality (“click the 3rd result”)

### Verified progress

- Predicates like `exists(...)`, `url_matches(...)`, `is_enabled(...)`, `value_equals(...)`
- Fluent assertion DSL via `expect(...)`
- Retrying verification via `runtime.check(...).eventually(...)`

### Explained failure

- JSONL trace events (`Tracer` + `JsonlTraceSink`)
- Optional failure artifact bundles (snapshots, diagnostics, step timelines, frames/clip)
- Deterministic failure semantics: when required assertions can’t be proven, the run fails with artifacts you can replay

### Framework interoperability

- Bring your own LLM and orchestration (LangGraph, AutoGen, custom loops)
- Register explicit LLM-callable tools with `ToolRegistry`

## ToolRegistry (LLM-callable tools)

Sentience can expose a **typed tool surface** for agents (with tool-call tracing).

```python
from sentience.tools import ToolRegistry, register_default_tools

registry = ToolRegistry()
register_default_tools(registry, runtime)  # or pass a ToolContext

# LLM-ready tool specs
tools_for_llm = registry.llm_tools()
```

## Permissions (avoid Chrome permission bubbles)

Chrome permission prompts are outside the DOM and can be invisible to snapshots. Prefer setting a policy **before navigation**.

```python
from sentience import AsyncSentienceBrowser, PermissionPolicy

policy = PermissionPolicy(
    default="clear",
    auto_grant=["geolocation"],
    geolocation={"latitude": 37.77, "longitude": -122.41, "accuracy": 50},
    origin="https://example.com",
)

async with AsyncSentienceBrowser(permission_policy=policy) as browser:
    ...
```

If your backend supports it, you can also use ToolRegistry permission tools (`grant_permissions`, `clear_permissions`, `set_geolocation`) mid-run.

## Downloads (verification predicate)

If a flow is expected to download a file, assert it explicitly:

```python
from sentience.verification import download_completed

runtime.assert_(download_completed("report.csv"), label="download_ok", required=True)
```

## Debugging (fast)

- **Manual driver CLI** (inspect clickables, click/type/press quickly):

```bash
sentience driver --url https://example.com
```

- **Verification + artifacts + debugging with time-travel traces (Sentience Studio demo)**:

<video src="https://github.com/user-attachments/assets/7ffde43b-1074-4d70-bb83-2eb8d0469307" controls muted playsinline></video>

If the video tag doesn’t render in your GitHub README view, use this link: [`sentience-studio-demo.mp4`](https://github.com/user-attachments/assets/7ffde43b-1074-4d70-bb83-2eb8d0469307)

- **Sentience SDK Documentation**: https://www.sentienceapi.com/docs

## Integrations (examples)

- **Browser-use:** [examples/browser-use](examples/browser-use/)
- **LangChain:** [examples/lang-chain](examples/lang-chain/)
- **LangGraph:** [examples/langgraph](examples/langgraph/)
- **Pydantic AI:** [examples/pydantic_ai](examples/pydantic_ai/)
