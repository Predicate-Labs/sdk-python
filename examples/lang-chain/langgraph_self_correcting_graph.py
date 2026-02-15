"""
LangGraph reference example: Sentience observe → act → verify → branch (self-correcting).

Install:
  pip install predicate-sdk[langchain]

Run:
  python examples/lang-chain/langgraph_self_correcting_graph.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from predicate import AsyncSentienceBrowser
from predicate.integrations.langchain import SentienceLangChainContext, SentienceLangChainCore


@dataclass
class State:
    url: str | None = None
    last_action: str | None = None
    attempts: int = 0
    done: bool = False


async def main() -> None:
    from langgraph.graph import END, StateGraph

    browser = AsyncSentienceBrowser(headless=False)
    await browser.start()

    core = SentienceLangChainCore(SentienceLangChainContext(browser=browser))

    async def observe(state: State) -> State:
        s = await core.snapshot_state()
        state.url = s.url
        return state

    async def act(state: State) -> State:
        # Replace with an LLM decision node. For demo we just navigate once.
        if state.attempts == 0:
            await core.navigate("https://example.com")
            state.last_action = "navigate"
        else:
            state.last_action = "noop"
        state.attempts += 1
        return state

    async def verify(state: State) -> State:
        out = await core.verify_url_matches(r"example\.com")
        state.done = bool(out.passed)
        return state

    def branch(state: State) -> str:
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
    g.add_conditional_edges("verify", branch, {"retry": "observe", "done": END})
    app = g.compile()

    final = await app.ainvoke(State())
    print(final)

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
