# Predicate Python SDK

> **A verification & control layer for AI agents that operate browsers**

Predicate is built for **AI agent developers** who already use Playwright / CDP / browser-use / LangGraph and care about **flakiness, cost, determinism, evals, and debugging**.

Often described as *Jest for Browser AI Agents* - but applied to end-to-end agent runs (not unit tests).

The core loop is:

> **Agent → Snapshot → Action → Verification → Artifact**

## What Predicate is

- A **verification-first runtime** (`AgentRuntime`) for browser agents
- Treats the browser as an adapter (Playwright / CDP / browser-use); **`AgentRuntime` is the product**
- A **controlled perception** layer (semantic snapshots; pruning/limits; lowers token usage by filtering noise from what models see)
- A **debugging layer** (structured traces + failure artifacts)
- Enables **local LLM small models (3B-7B)** for browser automation (privacy, compliance, and cost control)
- Keeps vision models **optional** (use as a fallback when DOM/snapshot structure falls short, e.g. `<canvas>`)

## What Predicate is not

- Not a browser driver
- Not a Playwright replacement
- Not a vision-first agent framework

## Install

```bash
pip install predicate-sdk
playwright install chromium
```

If you’re developing from source (this repo), install the local checkout instead:

```bash
pip install -e .
playwright install chromium
```

## Conceptual example (why this exists)

In Predicate, agents don’t “hope” an action worked.

- **Every step is gated by verifiable UI assertions**
- If progress can’t be proven, the run **fails with evidence** (trace + artifacts)
- This is how you make runs **reproducible** and **debuggable**, and how you run evals reliably

## Quickstart: a verification-first loop

This is the smallest useful pattern: snapshot → assert → act → assert-done.

```python
import asyncio

from predicate import AgentRuntime, AsyncPredicateBrowser
from predicate.tracing import JsonlTraceSink, Tracer
from predicate.verification import exists, url_contains


async def main() -> None:
    tracer = Tracer(run_id="demo", sink=JsonlTraceSink("trace.jsonl"))

    async with AsyncPredicateBrowser() as browser:
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

## PredicateDebugger: attach to your existing agent framework (sidecar mode)

If you already have an agent loop (LangGraph, browser-use, custom planner/executor), you can keep it and attach Predicate as a **verifier + trace layer**.

Key idea: your agent still decides and executes actions — Predicate **snapshots and verifies outcomes**.

```python
from predicate import PredicateDebugger, create_tracer
from predicate.verification import exists, url_contains


async def run_existing_agent(page) -> None:
    # page: playwright.async_api.Page (owned by your agent/framework)
    tracer = create_tracer(run_id="run-123")  # local JSONL by default
    dbg = PredicateDebugger.attach(page, tracer=tracer)

    async with dbg.step("agent_step: navigate + verify"):
        # 1) Let your framework do whatever it does
        await your_agent.step()

        # 2) Snapshot what the agent produced
        await dbg.snapshot()

        # 3) Verify outcomes (with bounded retries)
        await dbg.check(url_contains("example.com"), label="on_domain", required=True).eventually(timeout_s=10)
        await dbg.check(exists("role=heading"), label="has_heading").eventually(timeout_s=10)
```

## SDK-driven full loop (snapshots + actions)

If you want Predicate to drive the loop end-to-end, you can use the SDK primitives directly: take a snapshot, select elements, act, then verify.

```python
from predicate import PredicateBrowser, snapshot, find, click, type_text, wait_for


def login_example() -> None:
    with PredicateBrowser() as browser:
        browser.page.goto("https://example.com/login")

        snap = snapshot(browser)
        email = find(snap, "role=textbox text~'email'")
        password = find(snap, "role=textbox text~'password'")
        submit = find(snap, "role=button text~'sign in'")

        if not (email and password and submit):
            raise RuntimeError("login form not found")

        type_text(browser, email.id, "user@example.com")
        type_text(browser, password.id, "password123")
        click(browser, submit.id)

        # Verify success
        ok = wait_for(browser, "role=heading text~'Dashboard'", timeout=10.0)
        if not ok.found:
            raise RuntimeError("login failed")
```

## Pre-action authority hook (production pattern)

If you want every action proposal to be authorized before execution, pass a
`pre_action_authorizer` into `RuntimeAgent`.

This hook receives a shared `predicate-contracts` `ActionRequest` generated from
runtime state (`snapshot` + assertion evidence) and must return either:

- `True` / `False`, or
- an object with an `allowed: bool` field (for richer decision payloads).

```python
from predicate.agent_runtime import AgentRuntime
from predicate.runtime_agent import RuntimeAgent, RuntimeStep

# Optional: your authority client can be local guard, sidecar client, or remote API client.
def pre_action_authorizer(action_request):
    # Example: call your authority service
    # resp = authority_client.authorize(action_request)
    # return resp
    return True


runtime = AgentRuntime(backend=backend, tracer=tracer)
agent = RuntimeAgent(
    runtime=runtime,
    executor=executor,
    pre_action_authorizer=pre_action_authorizer,
    authority_principal_id="agent:web-checkout",
    authority_tenant_id="tenant-a",
    authority_session_id="session-123",
    authority_fail_closed=True,  # deny/authorizer errors block action execution
)

ok = await agent.run_step(
    task_goal="Complete checkout",
    step=RuntimeStep(goal="Click submit order"),
)
```

Fail-open option (not recommended for sensitive actions):

```python
agent = RuntimeAgent(
    runtime=runtime,
    executor=executor,
    pre_action_authorizer=pre_action_authorizer,
    authority_fail_closed=False,  # authorizer errors allow action to proceed
)
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

### Scroll verification (prevent no-op scroll drift)

A common agent failure mode is “scrolling” without the UI actually advancing (overlays, nested scrollers, focus issues). Use `AgentRuntime.scroll_by(...)` to deterministically verify scroll *had effect* via before/after `scrollTop`.

```python
runtime.begin_step("Scroll the page and verify it moved")
ok = await runtime.scroll_by(
    600,
    verify=True,
    min_delta_px=50,
    label="scroll_effective",
    required=True,
    timeout_s=5.0,
)
if not ok:
    raise RuntimeError("Scroll had no effect (likely blocked by overlay or nested scroller).")
```

### Explained failure

- JSONL trace events (`Tracer` + `JsonlTraceSink`)
- Optional failure artifact bundles (snapshots, diagnostics, step timelines, frames/clip)
- Deterministic failure semantics: when required assertions can’t be proven, the run fails with artifacts you can replay

### Framework interoperability

- Bring your own LLM and orchestration (LangGraph, AutoGen, custom loops)
- Register explicit LLM-callable tools with `ToolRegistry`

## ToolRegistry (LLM-callable tools)

Predicate can expose a **typed tool surface** for agents (with tool-call tracing).

```python
from predicate.tools import ToolRegistry, register_default_tools

registry = ToolRegistry()
register_default_tools(registry, runtime)  # or pass a ToolContext

# LLM-ready tool specs
tools_for_llm = registry.llm_tools()
```

## Permissions (avoid Chrome permission bubbles)

Chrome permission prompts are outside the DOM and can be invisible to snapshots. Prefer setting a policy **before navigation**.

```python
from predicate import AsyncPredicateBrowser, PermissionPolicy

policy = PermissionPolicy(
    default="clear",
    auto_grant=["geolocation"],
    geolocation={"latitude": 37.77, "longitude": -122.41, "accuracy": 50},
    origin="https://example.com",
)

async with AsyncPredicateBrowser(permission_policy=policy) as browser:
    ...
```

If your backend supports it, you can also use ToolRegistry permission tools (`grant_permissions`, `clear_permissions`, `set_geolocation`) mid-run.

## Downloads (verification predicate)

If a flow is expected to download a file, assert it explicitly:

```python
from predicate.verification import download_completed

runtime.assert_(download_completed("report.csv"), label="download_ok", required=True)
```

## Debugging (fast)

- **Manual driver CLI** (inspect clickables, click/type/press quickly):

```bash
predicate driver --url https://example.com
```

- **Verification + artifacts + debugging with time-travel traces (Predicate Studio demo)**:

<video src="https://github.com/user-attachments/assets/7ffde43b-1074-4d70-bb83-2eb8d0469307" controls muted playsinline></video>

If the video tag doesn’t render in your GitHub README view, use this link: [`sentience-studio-demo.mp4`](https://github.com/user-attachments/assets/7ffde43b-1074-4d70-bb83-2eb8d0469307)

- **Predicate SDK Documentation**: https://predicatelabs.dev/docs

## Integrations (examples)

- **Browser-use:** [examples/browser-use](examples/browser-use/)
- **LangChain:** [examples/lang-chain](examples/lang-chain/)
- **LangGraph:** [examples/langgraph](examples/langgraph/)
- **Pydantic AI:** [examples/pydantic_ai](examples/pydantic_ai/)
