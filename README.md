# Sentience Python SDK

**Semantic snapshots and Jest-style assertions for reliable AI web agents with time-travel traces**

## 📦 Installation

```bash
# Install from PyPI
pip install sentienceapi

# Install Playwright browsers (required)
playwright install chromium

# For LLM Agent features (optional)
pip install openai  # For OpenAI models
pip install anthropic  # For Claude models
pip install transformers torch  # For local LLMs
```

**For local development:**
```bash
pip install -e .
```

## Jest for AI Web Agent

### Semantic snapshots and assertions that let agents act, verify, and know when they're done.

Use `AgentRuntime` to add Jest-style assertions to your agent loops. Verify browser state, check task completion, and get clear feedback on what's working:

```python
import asyncio
from sentience import AsyncSentienceBrowser, AgentRuntime
from sentience.verification import (
    url_contains,
    exists,
    all_of,
    is_enabled,
    is_checked,
    value_equals,
)
from sentience.tracing import Tracer, JsonlTraceSink

async def main():
    # Create tracer
    tracer = Tracer(run_id="my-run", sink=JsonlTraceSink("trace.jsonl"))

    # Create browser and runtime
    async with AsyncSentienceBrowser() as browser:
        page = await browser.new_page()
        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser,
            page=page,
            tracer=tracer
        )

        # Navigate and take snapshot
        await page.goto("https://example.com")
        runtime.begin_step("Verify page loaded")
        await runtime.snapshot()

        # v1: deterministic assertions (Jest-style)
        runtime.assert_(url_contains("example.com"), label="on_correct_domain")
        runtime.assert_(exists("role=heading"), label="has_heading")
        runtime.assert_(all_of([
            exists("role=button"),
            exists("role=link")
        ]), label="has_interactive_elements")

        # v1: state-aware assertions (when Gateway refinement is enabled)
        runtime.assert_(is_enabled("role=button"), label="button_enabled")
        runtime.assert_(is_checked("role=checkbox name~'subscribe'"), label="subscribe_checked_if_present")
        runtime.assert_(value_equals("role=textbox name~'email'", "user@example.com"), label="email_value_if_present")

        # v2: retry loop with snapshot confidence gating + exhaustion
        ok = await runtime.check(
            exists("role=heading"),
            label="heading_eventually_visible",
            required=True,
        ).eventually(timeout_s=10.0, poll_s=0.25, min_confidence=0.7, max_snapshot_attempts=3)
        print("eventually() result:", ok)

        # Check task completion
        if runtime.assert_done(exists("text~'Example'"), label="task_complete"):
            print("✅ Task completed!")

        print(f"Task done: {runtime.is_task_done}")

asyncio.run(main())
```

**See examples:** [`examples/asserts/`](examples/asserts/)

## 🚀 Quick Start: Choose Your Abstraction Level

Sentience SDK offers **three abstraction levels** - use what fits your needs:

<details>
<summary><b>🎯 Level 3: Natural Language (Easiest)</b> - For non-technical users</summary>

```python
from sentience import SentienceBrowser, ConversationalAgent
from sentience.llm_provider import OpenAIProvider

browser = SentienceBrowser()
llm = OpenAIProvider(api_key="your-key", model="gpt-4o")
agent = ConversationalAgent(browser, llm)

with browser:
    response = agent.execute("Search for magic mouse on google.com")
    print(response)
    # → "I searched for 'magic mouse' and found several results.
    #    The top result is from amazon.com selling Magic Mouse 2 for $79."
```

**Best for:** End users, chatbots, no-code platforms
**Code required:** 3-5 lines
**Technical knowledge:** None

</details>

<details>
<summary><b>⚙️ Level 2: Technical Commands (Recommended)</b> - For AI developers</summary>

```python
from sentience import SentienceBrowser, SentienceAgent
from sentience.llm_provider import OpenAIProvider

browser = SentienceBrowser()
llm = OpenAIProvider(api_key="your-key", model="gpt-4o")
agent = SentienceAgent(browser, llm)

with browser:
    browser.page.goto("https://google.com")
    agent.act("Click the search box")
    agent.act("Type 'magic mouse' into the search field")
    agent.act("Press Enter key")
```

**Best for:** Building AI agents, automation scripts
**Code required:** 10-15 lines
**Technical knowledge:** Medium (Python basics)

</details>

<details>
<summary><b>🔧 Level 1: Direct SDK (Most Control)</b> - For production automation</summary>

```python
from sentience import SentienceBrowser, snapshot, find, click

with SentienceBrowser(headless=False) as browser:
    browser.page.goto("https://example.com")

    # Take snapshot - captures all interactive elements
    snap = snapshot(browser)
    print(f"Found {len(snap.elements)} elements")

    # Find and click a link using semantic selectors
    link = find(snap, "role=link text~'More information'")
    if link:
        result = click(browser, link.id)
        print(f"Click success: {result.success}")
```

**Best for:** Maximum control, performance-critical apps
**Code required:** 20-50 lines
**Technical knowledge:** High (SDK API, selectors)

</details>

---

## 🆕 What's New (2026-01-06)

### Human-like Typing
Add realistic delays between keystrokes to mimic human typing:
```python
from sentience import type_text

# Type instantly (default)
type_text(browser, element_id, "Hello World")

# Type with human-like delay (~10ms between keystrokes)
type_text(browser, element_id, "Hello World", delay_ms=10)
```

### Scroll to Element
Scroll elements into view with smooth animation:
```python
from sentience import snapshot, find, scroll_to

snap = snapshot(browser)
button = find(snap, 'role=button text~"Submit"')

# Scroll element into view with smooth animation
scroll_to(browser, button.id)

# Scroll instantly to top of viewport
scroll_to(browser, button.id, behavior='instant', block='start')
```

---

<details>
<summary><h2>💼 Real-World Example: Assertion-driven navigation</h2></summary>

This example shows how to use **assertions + `.eventually()`** to make an agent loop resilient:

```python
import asyncio
import os
from sentience import AsyncSentienceBrowser, AgentRuntime
from sentience.tracing import Tracer, JsonlTraceSink
from sentience.verification import url_contains, exists

async def main():
    tracer = Tracer(run_id="verified-run", sink=JsonlTraceSink("trace_verified.jsonl"))
    async with AsyncSentienceBrowser(headless=True) as browser:
        page = await browser.new_page()
        runtime = await AgentRuntime.from_sentience_browser(browser=browser, page=page, tracer=tracer)
        runtime.sentience_api_key = os.getenv("SENTIENCE_API_KEY")  # optional, enables Gateway diagnostics

        await page.goto("https://example.com")
        runtime.begin_step("Verify we're on the right page")

        await runtime.check(url_contains("example.com"), label="on_domain", required=True).eventually(
            timeout_s=10.0, poll_s=0.25, min_confidence=0.7, max_snapshot_attempts=3
        )
        runtime.assert_(exists("role=heading"), label="heading_present")

asyncio.run(main())
```

</details>

---

## 📚 Core Features

<details>
<summary><h3>🌐 Browser Control</h3></summary>

- **`SentienceBrowser`** - Playwright browser with Sentience extension pre-loaded
- **`browser.goto(url)`** - Navigate with automatic extension readiness checks
- Automatic bot evasion and stealth mode
- Configurable headless/headed mode

</details>

<details>
<summary><h3>📸 Snapshot - Intelligent Page Analysis</h3></summary>

**`snapshot(browser, options=SnapshotOptions(screenshot=True, show_overlay=False, limit=None, goal=None))`** - Capture page state with AI-ranked elements

Features:
- Returns semantic elements with roles, text, importance scores, and bounding boxes
- Optional screenshot capture (PNG/JPEG) - set `screenshot=True`
- Optional visual overlay to see what elements are detected - set `show_overlay=True`
- Pydantic models for type safety
- Optional ML reranking when `goal` is provided
- **`snapshot.save(filepath)`** - Export to JSON

**Example:**
```python
from sentience import snapshot, SnapshotOptions

# Basic snapshot with defaults (no screenshot, no overlay)
snap = snapshot(browser)

# With screenshot and overlay
snap = snapshot(browser, SnapshotOptions(
    screenshot=True,
    show_overlay=True,
    limit=100,
    goal="Click the login button"  # Optional: enables ML reranking
))

# Access structured data
print(f"URL: {snap.url}")
print(f"Viewport: {snap.viewport.width}x{snap.viewport.height}")
print(f"Elements: {len(snap.elements)}")

# Iterate over elements
for element in snap.elements:
    print(f"{element.role}: {element.text} (importance: {element.importance})")

    # Check ML reranking metadata (when goal is provided)
    if element.rerank_index is not None:
        print(f"  ML rank: {element.rerank_index} (confidence: {element.ml_probability:.2%})")
```

</details>

<details>
<summary><h3>🔍 Query Engine - Semantic Element Selection</h3></summary>

- **`query(snapshot, selector)`** - Find all matching elements
- **`find(snapshot, selector)`** - Find single best match (by importance)
- Powerful query DSL with multiple operators

**Query Examples:**
```python
# Find by role and text
button = find(snap, "role=button text='Sign in'")

# Substring match (case-insensitive)
link = find(snap, "role=link text~'more info'")

# Spatial filtering
top_left = find(snap, "bbox.x<=100 bbox.y<=200")

# Multiple conditions (AND logic)
primary_btn = find(snap, "role=button clickable=true visible=true importance>800")

# Prefix/suffix matching
starts_with = find(snap, "text^='Add'")
ends_with = find(snap, "text$='Cart'")

# Numeric comparisons
important = query(snap, "importance>=700")
first_row = query(snap, "bbox.y<600")
```

**📖 [Complete Query DSL Guide](docs/QUERY_DSL.md)** - All operators, fields, and advanced patterns

</details>

<details>
<summary><h3>👆 Actions - Interact with Elements</h3></summary>

- **`click(browser, element_id)`** - Click element by ID
- **`click_rect(browser, rect)`** - Click at center of rectangle (coordinate-based)
- **`type_text(browser, element_id, text)`** - Type into input fields
- **`press(browser, key)`** - Press keyboard keys (Enter, Escape, Tab, etc.)

All actions return `ActionResult` with success status, timing, and outcome:

```python
result = click(browser, element.id)

print(f"Success: {result.success}")
print(f"Outcome: {result.outcome}")  # "navigated", "dom_updated", "error"
print(f"Duration: {result.duration_ms}ms")
print(f"URL changed: {result.url_changed}")
```

**Coordinate-based clicking:**
```python
from sentience import click_rect

# Click at center of rectangle (x, y, width, height)
click_rect(browser, {"x": 100, "y": 200, "w": 50, "h": 30})

# With visual highlight (default: red border for 2 seconds)
click_rect(browser, {"x": 100, "y": 200, "w": 50, "h": 30}, highlight=True, highlight_duration=2.0)

# Using element's bounding box
snap = snapshot(browser)
element = find(snap, "role=button")
if element:
    click_rect(browser, {
        "x": element.bbox.x,
        "y": element.bbox.y,
        "w": element.bbox.width,
        "h": element.bbox.height
    })
```

</details>

<details>
<summary><h3>⏱️ Wait & Assertions</h3></summary>

- **`wait_for(browser, selector, timeout=5.0, interval=None, use_api=None)`** - Wait for element to appear
- **`expect(browser, selector)`** - Assertion helper with fluent API

**Examples:**
```python
# Wait for element (auto-detects optimal interval based on API usage)
result = wait_for(browser, "role=button text='Submit'", timeout=10.0)
if result.found:
    print(f"Found after {result.duration_ms}ms")

# Use local extension with fast polling (0.25s interval)
result = wait_for(browser, "role=button", timeout=5.0, use_api=False)

# Use remote API with network-friendly polling (1.5s interval)
result = wait_for(browser, "role=button", timeout=5.0, use_api=True)

# Custom interval override
result = wait_for(browser, "role=button", timeout=5.0, interval=0.5, use_api=False)

# Semantic wait conditions
wait_for(browser, "clickable=true", timeout=5.0)  # Wait for clickable element
wait_for(browser, "importance>100", timeout=5.0)  # Wait for important element
wait_for(browser, "role=link visible=true", timeout=5.0)  # Wait for visible link

# Assertions
expect(browser, "role=button text='Submit'").to_exist(timeout=5.0)
expect(browser, "role=heading").to_be_visible()
expect(browser, "role=button").to_have_text("Submit")
expect(browser, "role=link").to_have_count(10)
```

</details>

<details>
<summary><h3>🎨 Visual Overlay - Debug Element Detection</h3></summary>

- **`show_overlay(browser, elements, target_element_id=None)`** - Display visual overlay highlighting elements
- **`clear_overlay(browser)`** - Clear overlay manually

Show color-coded borders around detected elements to debug, validate, and understand what Sentience sees:

```python
from sentience import show_overlay, clear_overlay

# Take snapshot once
snap = snapshot(browser)

# Show overlay anytime without re-snapshotting
show_overlay(browser, snap)  # Auto-clears after 5 seconds

# Highlight specific target element in red
button = find(snap, "role=button text~'Submit'")
show_overlay(browser, snap, target_element_id=button.id)

# Clear manually before 5 seconds
import time
time.sleep(2)
clear_overlay(browser)
```

**Color Coding:**
- 🔴 Red: Target element
- 🔵 Blue: Primary elements (`is_primary=true`)
- 🟢 Green: Regular interactive elements

**Visual Indicators:**
- Border thickness/opacity scales with importance
- Semi-transparent fill
- Importance badges
- Star icons for primary elements
- Auto-clear after 5 seconds

</details>

<details>
<summary><h3>📄 Content Reading</h3></summary>

**`read(browser, format="text|markdown|raw")`** - Extract page content
- `format="text"` - Plain text extraction
- `format="markdown"` - High-quality markdown conversion (uses markdownify)
- `format="raw"` - Cleaned HTML (default)

**Example:**
```python
from sentience import read

# Get markdown content
result = read(browser, format="markdown")
print(result["content"])  # Markdown text

# Get plain text
result = read(browser, format="text")
print(result["content"])  # Plain text
```

</details>

<details>
<summary><h3>📷 Screenshots</h3></summary>

**`screenshot(browser, format="png|jpeg", quality=80)`** - Standalone screenshot capture
- Returns base64-encoded data URL
- PNG or JPEG format
- Quality control for JPEG (1-100)

**Example:**
```python
from sentience import screenshot
import base64

# Capture PNG screenshot
data_url = screenshot(browser, format="png")

# Save to file
image_data = base64.b64decode(data_url.split(",")[1])
with open("screenshot.png", "wb") as f:
    f.write(image_data)

# JPEG with quality control (smaller file size)
data_url = screenshot(browser, format="jpeg", quality=85)
```

</details>

<details>
<summary><h3>🔎 Text Search - Find Elements by Visible Text</h3></summary>

**`find_text_rect(browser, text, case_sensitive=False, whole_word=False, max_results=10)`** - Find text on page and get exact pixel coordinates

Find buttons, links, or any UI elements by their visible text without needing element IDs or CSS selectors. Returns exact pixel coordinates for each match.

**Example:**
```python
from sentience import SentienceBrowser, find_text_rect, click_rect

with SentienceBrowser() as browser:
    browser.page.goto("https://example.com")

    # Find "Sign In" button
    result = find_text_rect(browser, "Sign In")
    if result.status == "success" and result.results:
        first_match = result.results[0]
        print(f"Found at: ({first_match.rect.x}, {first_match.rect.y})")
        print(f"In viewport: {first_match.in_viewport}")

        # Click on the found text
        if first_match.in_viewport:
            click_rect(browser, {
                "x": first_match.rect.x,
                "y": first_match.rect.y,
                "w": first_match.rect.width,
                "h": first_match.rect.height
            })
```

**Advanced Options:**
```python
# Case-sensitive search
result = find_text_rect(browser, "LOGIN", case_sensitive=True)

# Whole word only (won't match "login" as part of "loginButton")
result = find_text_rect(browser, "log", whole_word=True)

# Find multiple matches
result = find_text_rect(browser, "Buy", max_results=10)
for match in result.results:
    if match.in_viewport:
        print(f"Found '{match.text}' at ({match.rect.x}, {match.rect.y})")
        print(f"Context: ...{match.context.before}[{match.text}]{match.context.after}...")
```

**Returns:** `TextRectSearchResult` with:
- **`status`**: "success" or "error"
- **`results`**: List of `TextMatch` objects with:
  - `text` - The matched text
  - `rect` - Absolute coordinates (with scroll offset)
  - `viewport_rect` - Viewport-relative coordinates
  - `context` - Surrounding text (before/after)
  - `in_viewport` - Whether visible in current viewport

**Use Cases:**
- Find buttons/links by visible text without CSS selectors
- Get exact pixel coordinates for click automation
- Verify text visibility and position on page
- Search dynamic content that changes frequently

**Note:** Does not consume API credits (runs locally in browser)

**See example:** `examples/find_text_demo.py`

</details>

---

## 🔄 Async API

For asyncio contexts (FastAPI, async frameworks):

```python
from sentience.async_api import AsyncSentienceBrowser, snapshot_async, click_async, find

async def main():
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        snap = await snapshot_async(browser)
        button = find(snap, "role=button")
        if button:
            await click_async(browser, button.id)

asyncio.run(main())
```

**See example:** `examples/async_api_demo.py`

---

## 📋 Reference

<details>
<summary><h3>Element Properties</h3></summary>

Elements returned by `snapshot()` have the following properties:

```python
element.id              # Unique identifier for interactions
element.role            # ARIA role (button, link, textbox, heading, etc.)
element.text            # Visible text content
element.importance      # AI importance score (0-1000)
element.bbox            # Bounding box (x, y, width, height)
element.visual_cues     # Visual analysis (is_primary, is_clickable, background_color)
element.in_viewport     # Is element visible in current viewport?
element.is_occluded     # Is element covered by other elements?
element.z_index         # CSS stacking order
```

</details>

<details>
<summary><h3>Query DSL Reference</h3></summary>

### Basic Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `=` | Exact match | `role=button` |
| `!=` | Exclusion | `role!=link` |
| `~` | Substring (case-insensitive) | `text~'sign in'` |
| `^=` | Prefix match | `text^='Add'` |
| `$=` | Suffix match | `text$='Cart'` |
| `>`, `>=` | Greater than | `importance>500` |
| `<`, `<=` | Less than | `bbox.y<600` |

### Supported Fields

- **Role**: `role=button|link|textbox|heading|...`
- **Text**: `text`, `text~`, `text^=`, `text$=`
- **Visibility**: `clickable=true|false`, `visible=true|false`
- **Importance**: `importance`, `importance>=N`, `importance<N`
- **Position**: `bbox.x`, `bbox.y`, `bbox.width`, `bbox.height`
- **Layering**: `z_index`

</details>

---

## ⚙️ Configuration

<details>
<summary><h3>Viewport Size</h3></summary>

Default viewport is **1280x800** pixels. You can customize it using Playwright's API:

```python
with SentienceBrowser(headless=False) as browser:
    # Set custom viewport before navigating
    browser.page.set_viewport_size({"width": 1920, "height": 1080})

    browser.goto("https://example.com")
```

</details>

<details>
<summary><h3>Headless Mode</h3></summary>

```python
# Headed mode (default in dev, shows browser window)
browser = SentienceBrowser(headless=False)

# Headless mode (default in CI environments)
browser = SentienceBrowser(headless=True)

# Auto-detect based on environment
browser = SentienceBrowser()  # headless=True if CI=true, else False
```

</details>

<details>
<summary><h3>🌍 Residential Proxy Support</h3></summary>

Use residential proxies to route traffic and protect your IP address. Supports HTTP, HTTPS, and SOCKS5 with automatic SSL certificate handling:

```python
# Method 1: Direct configuration
browser = SentienceBrowser(proxy="http://user:pass@proxy.example.com:8080")

# Method 2: Environment variable
# export SENTIENCE_PROXY="http://user:pass@proxy.example.com:8080"
browser = SentienceBrowser()

# Works with agents
llm = OpenAIProvider(api_key="your-key", model="gpt-4o")
agent = SentienceAgent(browser, llm)

with browser:
    browser.page.goto("https://example.com")
    agent.act("Search for products")
    # All traffic routed through proxy with WebRTC leak protection
```

**Features:**
- HTTP, HTTPS, SOCKS5 proxy support
- Username/password authentication
- Automatic self-signed SSL certificate handling
- WebRTC IP leak protection (automatic)

See `examples/residential_proxy_agent.py` for complete examples.

</details>

<details>
<summary><h3>🔐 Authentication Session Injection</h3></summary>

Inject pre-recorded authentication sessions (cookies + localStorage) to start your agent already logged in, bypassing login screens, 2FA, and CAPTCHAs. This saves tokens and reduces costs by eliminating login steps.

```python
# Workflow 1: Inject pre-recorded session from file
from sentience import SentienceBrowser, save_storage_state

# Save session after manual login
browser = SentienceBrowser()
browser.start()
browser.goto("https://example.com")
# ... log in manually ...
save_storage_state(browser.context, "auth.json")

# Use saved session in future runs
browser = SentienceBrowser(storage_state="auth.json")
browser.start()
# Agent starts already logged in!

# Workflow 2: Persistent sessions (cookies persist across runs)
browser = SentienceBrowser(user_data_dir="./chrome_profile")
browser.start()
# First run: Log in
# Second run: Already logged in (cookies persist automatically)
```

**Benefits:**
- Bypass login screens and CAPTCHAs with valid sessions
- Save 5-10 agent steps and hundreds of tokens per run
- Maintain stateful sessions for accessing authenticated pages
- Act as authenticated users (e.g., "Go to my Orders page")

See `examples/auth_injection_agent.py` for complete examples.

</details>

---

## 💡 Best Practices

<details>
<summary>Click to expand best practices</summary>

### 1. Wait for Dynamic Content
```python
browser.goto("https://example.com", wait_until="domcontentloaded")
time.sleep(1)  # Extra buffer for AJAX/animations
```

### 2. Use Multiple Strategies for Finding Elements
```python
# Try exact match first
btn = find(snap, "role=button text='Add to Cart'")

# Fallback to fuzzy match
if not btn:
    btn = find(snap, "role=button text~='cart'")
```

### 3. Check Element Visibility Before Clicking
```python
if element.in_viewport and not element.is_occluded:
    click(browser, element.id)
```

### 4. Handle Navigation
```python
result = click(browser, link_id)
if result.url_changed:
    browser.page.wait_for_load_state("networkidle")
```

### 5. Use Screenshots Sparingly
```python
# Fast - no screenshot (only element data)
snap = snapshot(browser)

# Slower - with screenshot (for debugging/verification)
snap = snapshot(browser, SnapshotOptions(screenshot=True))
```

</details>

---

## 🛠️ Troubleshooting

<details>
<summary>Click to expand common issues and solutions</summary>

### "Extension failed to load"
**Solution:** Build the extension first:
```bash
cd sentience-chrome
./build.sh
```

### "Element not found"
**Solutions:**
- Ensure page is loaded: `browser.page.wait_for_load_state("networkidle")`
- Use `wait_for()`: `wait_for(browser, "role=button", timeout=10)`
- Debug elements: `print([el.text for el in snap.elements])`

### Button not clickable
**Solutions:**
- Check visibility: `element.in_viewport and not element.is_occluded`
- Scroll to element: `browser.page.evaluate(f"window.sentience_registry[{element.id}].scrollIntoView()")`

</details>

---

## 🔬 Advanced Features (v0.12.0+)

<details>
<summary><h3>📊 Agent Tracing & Debugging</h3></summary>

The SDK now includes built-in tracing infrastructure for debugging and analyzing agent behavior:

```python
from sentience import SentienceBrowser, SentienceAgent
from sentience.llm_provider import OpenAIProvider
from sentience.tracing import Tracer, JsonlTraceSink
from sentience.agent_config import AgentConfig

# Create tracer to record agent execution
tracer = Tracer(
    run_id="my-agent-run-123",
    sink=JsonlTraceSink("trace.jsonl")
)

# Configure agent behavior
config = AgentConfig(
    snapshot_limit=50,
    temperature=0.0,
    max_retries=1,
    capture_screenshots=True
)

browser = SentienceBrowser()
llm = OpenAIProvider(api_key="your-key", model="gpt-4o")

# Pass tracer and config to agent
agent = SentienceAgent(browser, llm, tracer=tracer, config=config)

with browser:
    browser.page.goto("https://example.com")

    # All actions are automatically traced
    agent.act("Click the sign in button")
    agent.act("Type 'user@example.com' into email field")

# Trace events saved to trace.jsonl
# Events: step_start, snapshot, llm_query, action, step_end, error
```

**Trace Events Captured:**
- `step_start` - Agent begins executing a goal
- `snapshot` - Page state captured
- `llm_query` - LLM decision made (includes tokens, model, response)
- `action` - Action executed (click, type, press)
- `step_end` - Step completed successfully
- `error` - Error occurred during execution

**Use Cases:**
- Debug why agent failed or got stuck
- Analyze token usage and costs
- Replay agent sessions
- Train custom models from successful runs
- Monitor production agents

</details>

<details>
<summary><h3>🔍 Agent Runtime Verification</h3></summary>

`AgentRuntime` provides assertion predicates for runtime verification in agent loops, enabling programmatic verification of browser state during execution.

```python
from sentience import (
    AgentRuntime, SentienceBrowser,
    url_contains, exists, all_of
)
from sentience.tracer_factory import create_tracer

browser = SentienceBrowser()
browser.start()
tracer = create_tracer(run_id="my-run", upload_trace=False)
runtime = AgentRuntime(browser, browser.page, tracer)

# Navigate and take snapshot
browser.page.goto("https://example.com")
runtime.begin_step("Verify page")
runtime.snapshot()

# Run assertions
runtime.assert_(url_contains("example.com"), "on_correct_domain")
runtime.assert_(exists("role=heading"), "has_heading")
runtime.assert_done(exists("text~'Example'"), "task_complete")

print(f"Task done: {runtime.is_task_done}")
```

**See example:** [`examples/agent_runtime_verification.py`](examples/agent_runtime_verification.py)

</details>

<details>
<summary><h3>🧰 Snapshot Utilities</h3></summary>

New utility functions for working with snapshots:

```python
from sentience import snapshot
from sentience.utils import compute_snapshot_digests, canonical_snapshot_strict
from sentience.formatting import format_snapshot_for_llm

snap = snapshot(browser)

# Compute snapshot fingerprints (detect page changes)
digests = compute_snapshot_digests(snap.elements)
print(f"Strict digest: {digests['strict']}")  # Changes when text changes
print(f"Loose digest: {digests['loose']}")   # Only changes when layout changes

# Format snapshot for LLM prompts
llm_context = format_snapshot_for_llm(snap, limit=50)
print(llm_context)
# Output: [1] <button> "Sign In" {PRIMARY,CLICKABLE} @ (100,50) (Imp:10)
```

</details>

---

## 📖 Documentation

- **📖 [Amazon Shopping Guide](../docs/AMAZON_SHOPPING_GUIDE.md)** - Complete tutorial with real-world example
- **📖 [Query DSL Guide](docs/QUERY_DSL.md)** - Advanced query patterns and operators
- **📄 [API Contract](../spec/SNAPSHOT_V1.md)** - Snapshot API specification
- **📄 [Type Definitions](../spec/sdk-types.md)** - TypeScript/Python type definitions

---

## 💻 Examples & Testing

<details>
<summary><h3>Examples</h3></summary>

See the `examples/` directory for complete working examples:

- **`hello.py`** - Extension bridge verification
- **`basic_agent.py`** - Basic snapshot and element inspection
- **`query_demo.py`** - Query engine demonstrations
- **`wait_and_click.py`** - Waiting for elements and performing actions
- **`read_markdown.py`** - Content extraction and markdown conversion

</details>

<details>
<summary><h3>Testing</h3></summary>

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_snapshot.py

# Run with verbose output
pytest -v tests/
```

</details>

---

## License & Commercial Use

### Open Source SDK
The Sentience SDK is dual-licensed under [MIT License](./LICENSE-MIT) and [Apache 2.0](./LICENSE-APACHE). You are free to use, modify, and distribute this SDK in your own projects (including commercial ones) without restriction.

### Commercial Platform
While the SDK is open source, the **Sentience Cloud Platform** (API, Hosting, Sentience Studio) is a commercial service.

**We offer Commercial Licenses for:**
* **High-Volume Production:** Usage beyond the free tier limits.
* **SLA & Support:** Guaranteed uptime and dedicated engineering support.
* **On-Premise / Self-Hosted Gateway:** If you need to run the Sentience Gateway (Rust+ONNX) in your own VPC for compliance (e.g., banking/healthcare), you need an Enterprise License.

[Contact Us](mailto:support@sentienceapi.com) for Enterprise inquiries.
