"""
LangGraph reference example: Sentience observe → act → verify → branch (self-correcting).

Install:
  pip install predicate-runtime[langchain]

Run:
  python examples/langgraph/sentience_self_correcting_graph.py

Notes:
- This is a template demonstrating control flow; you can replace the "decide" node
  with an LLM step (LangChain) that chooses actions based on snapshot_state/read_page.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from predicate import AsyncSentienceBrowser
from predicate.integrations.langchain import SentienceLangChainContext, SentienceLangChainCore


@dataclass
class State:
    url: str | None = None
    last_action: str | None = None
    attempts: int = 0
    done: bool = False


async def main() -> None:
    # Lazy import so the file can exist without langgraph installed
    from langgraph.graph import END, StateGraph

    browser = AsyncSentienceBrowser(headless=False)
    await browser.start()

    core = SentienceLangChainCore(SentienceLangChainContext(browser=browser))

    async def observe(state: State) -> State:
        s = await core.snapshot_state()
        state.url = s.url
        return state

    async def act(state: State) -> State:
        # Replace this with an LLM-driven decision. For demo purposes, we just navigate once.
        if state.attempts == 0:
            await core.navigate("https://example.com")
            state.last_action = "navigate"
        else:
            state.last_action = "noop"
        state.attempts += 1
        return state

    async def verify(state: State) -> State:
        # Guard condition: URL should contain example.com
        out = await core.verify_url_matches(r"example\.com")
        state.done = bool(out.passed)
        return state

    def should_continue(state: State) -> str:
        # Self-correcting loop: retry observe→act→verify up to 3 attempts
        if state.done:
            return "done"
        if state.attempts >= 3:
            return "done"
        return "retry"

    g = StateGraph(State)
    g.add_node("observe", observe)
    g.add_node("act", act)
    g.add_node("verify", verify)
    g.set_entry_point("observe")
    g.add_edge("observe", "act")
    g.add_edge("act", "verify")
    g.add_conditional_edges("verify", should_continue, {"retry": "observe", "done": END})
    app = g.compile()

    final = await app.ainvoke(State())
    print(final)

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
