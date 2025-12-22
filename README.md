# Sentience Python SDK

**Status**: ✅ Week 1 Complete

Python SDK for Sentience AI Agent Browser Automation.

## Installation

```bash
cd sdk-python
pip install -e .

# Install Playwright browsers (required)
playwright install chromium
```

## Quick Start

```python
from sentience import SentienceBrowser, snapshot, find, click

# Start browser with extension
with SentienceBrowser(headless=False) as browser:
    browser.page.goto("https://example.com")
    browser.page.wait_for_load_state("networkidle")
    
    # Take snapshot
    snap = snapshot(browser)
    print(f"Found {len(snap.elements)} elements")
    
    # Find and click a link
    link = find(snap, "role=link")
    if link:
        result = click(browser, link.id)
        print(f"Click success: {result.success}")
```

## Features

### Day 2: Browser Harness
- `SentienceBrowser` - Launch Playwright with extension loaded
- Automatic extension loading and verification

### Day 3: Snapshot
- `snapshot(browser, options)` - Capture page state
- Pydantic models for type safety
- `snapshot.save(filepath)` - Save to JSON

### Day 4: Query Engine
- `query(snapshot, selector)` - Find elements matching selector
- `find(snapshot, selector)` - Find single best match
- String DSL: `"role=button text~'Sign in'"`
- **📖 [Complete DSL Query Guide](docs/QUERY_DSL.md)** - Comprehensive documentation with all operators, fields, and examples

### Day 5: Actions
- `click(browser, element_id)` - Click element
- `type_text(browser, element_id, text)` - Type into element
- `press(browser, key)` - Press keyboard key

### Day 6: Wait & Assert
- `wait_for(browser, selector, timeout)` - Wait for element
- `expect(browser, selector)` - Assertion helper
  - `.to_exist()`
  - `.to_be_visible()`
  - `.to_have_text(text)`
  - `.to_have_count(n)`

### Content Reading
- `read(browser, format="raw|text|markdown")` - Read page content
  - **Default format: `"raw"`** - Returns HTML suitable for Turndown/markdownify
  - `format="raw"` - Get cleaned HTML
  - `format="markdown"` - Get high-quality markdown (uses markdownify internally)
  - `format="text"` - Get plain text
  
  **Examples:**
  ```python
  from sentience import read
  
  # Get raw HTML (default)
  result = read(browser)
  html = result["content"]
  
  # Get high-quality markdown (uses markdownify automatically)
  result = read(browser, format="markdown")
  markdown = result["content"]
  ```
  
  See `examples/read_markdown.py` for complete examples.

## Examples

See `examples/` directory:
- `hello.py` - Extension bridge verification
- `basic_agent.py` - Basic snapshot
- `query_demo.py` - Query engine
- `wait_and_click.py` - Wait and actions
- `read_markdown.py` - Reading page content and converting to markdown

## Testing

```bash
pytest tests/
```

## Documentation

- **📖 [Query DSL Guide](docs/QUERY_DSL.md)** - Complete guide to the semantic query language
- API Contract: `../spec/SNAPSHOT_V1.md`
- Type Definitions: `../spec/sdk-types.md`
