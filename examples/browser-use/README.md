# Sentience + browser-use Integration

This directory contains examples for integrating [Sentience](https://github.com/Predicate-Labs/sdk-python) with [browser-use](https://github.com/browser-use/browser-use).

## What is browser-use?

[browser-use](https://github.com/browser-use/browser-use) is an open-source framework for building AI agents that can interact with web browsers. Sentience enhances browser-use by providing:

- **Semantic element detection** — Accurate element identification using visual and structural cues
- **Token-slashed DOM context** — Reduces tokens by ~80% compared to raw DOM dumps
- **Importance-ranked elements** — Elements sorted by actionability for better LLM targeting
- **Ordinal task support** — "Click the 3rd item" works reliably with dominant group detection

## Installation

Install both packages together using the optional dependency:

```bash
pip install "predicatelabs[browser-use]"
```

Or install separately:

```bash
pip install predicatelabs browser-use
```

## Quick Start

### Using SentienceContext (Recommended)

`SentienceContext` provides a high-level API for getting compact, ranked DOM context:

```python
from browser_use import BrowserSession, BrowserProfile
from predicate import get_extension_dir
from predicate.backends import SentienceContext, TopElementSelector

# Setup browser with Sentience extension
profile = BrowserProfile(
    args=[f"--load-extension={get_extension_dir()}"],
)
session = BrowserSession(browser_profile=profile)
await session.start()

# Create context builder
ctx = SentienceContext(
    max_elements=60,
    top_element_selector=TopElementSelector(
        by_importance=60,        # Top N by importance score
        from_dominant_group=15,  # Top N from dominant group
        by_position=10,          # Top N by page position
    ),
)

# Build context from browser session
await session.navigate("https://news.ycombinator.com")
state = await ctx.build(
    session,
    goal="Find the first Show HN post",
    wait_for_extension_ms=5000,
)

if state:
    print(f"URL: {state.url}")
    print(f"Elements: {len(state.snapshot.elements)}")
    print(f"Prompt block:\n{state.prompt_block}")
```

### Using Low-Level APIs

For fine-grained control over snapshots and actions:

```python
from predicate import find, query, get_extension_dir
from predicate.backends import BrowserUseAdapter, snapshot, click, type_text

# Create adapter and backend
adapter = BrowserUseAdapter(session)
backend = await adapter.create_backend()

# Take snapshot
snap = await snapshot(backend)

# Find and interact with elements
search_box = find(snap, 'role=textbox[name*="Search"]')
if search_box:
    await click(backend, search_box.bbox)
    await type_text(backend, "Sentience AI")
```

## Examples

| File | Description |
|------|-------------|
| [integration.py](integration.py) | Complete integration example with SentienceContext |

## Output Format

The `SentienceContext.build()` method returns a `SentienceContextState` with:

- `url` — Current page URL
- `snapshot` — Full Sentience snapshot with all elements
- `prompt_block` — Compact LLM-ready context block

The prompt block format:
```
Elements: ID|role|text|imp|is_primary|docYq|ord|DG|href
Rules: ordinal→DG=1 then ord asc; otherwise imp desc. Use click(ID)/input_text(ID,...).
1|link|Show HN: My Project|85|1|2|0|1|ycombinato
2|link|Ask HN: Best practices|80|0|3|1|1|ycombinato
...
```

Fields:
- `ID` — Element ID for actions
- `role` — Semantic role (button, link, textbox, etc.)
- `text` — Truncated element text (max 30 chars)
- `imp` — Importance score (0-100)
- `is_primary` — 1 if primary CTA, 0 otherwise
- `docYq` — Quantized Y position (doc_y / 200)
- `ord` — Ordinal rank within dominant group, or "-"
- `DG` — 1 if in dominant group, 0 otherwise
- `href` — Compressed href token

## API Reference

### SentienceContext

```python
SentienceContext(
    sentience_api_key: str | None = None,  # API key for gateway mode
    use_api: bool | None = None,           # Force API vs extension mode
    max_elements: int = 60,                # Max elements to fetch
    show_overlay: bool = False,            # Show visual overlay
    top_element_selector: TopElementSelector | None = None,
)
```

### TopElementSelector

```python
TopElementSelector(
    by_importance: int = 60,        # Top N by importance score
    from_dominant_group: int = 15,  # Top N from dominant group
    by_position: int = 10,          # Top N by page position
)
```

### SentienceContext.build()

```python
await ctx.build(
    browser_session,                    # browser-use BrowserSession
    goal: str | None = None,            # Task description for reranking
    wait_for_extension_ms: int = 5000,  # Extension load timeout
    retries: int = 2,                   # Retry attempts
    retry_delay_s: float = 1.0,         # Delay between retries
) -> SentienceContextState | None
```

## License

Sentience SDK is dual-licensed under MIT and Apache-2.0.

browser-use is licensed under MIT. See [THIRD_PARTY_LICENSES.md](../../THIRD_PARTY_LICENSES.md).
