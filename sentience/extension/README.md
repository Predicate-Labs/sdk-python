# Sentience Chrome Extension (Embedded)

This directory contains the Sentience Chrome extension files bundled with the Python SDK.

## Auto-Sync

These files are automatically synced from the [sentience-chrome](https://github.com/rcholic/Sentience-Geometry-Chrome-Extension) repository when new releases are published.

## Files

- `manifest.json` - Chrome extension manifest
- `content.js` - Content script injected into web pages
- `background.js` - Background service worker
- `injected_api.js` - API injected into page context
- `pkg/` - WebAssembly bindings and core logic
  - `sentience_core.js` - WASM JavaScript bindings
  - `sentience_core_bg.wasm` - Compiled WebAssembly binary
  - `*.d.ts` - TypeScript definitions

## Usage

The extension is automatically loaded by `SentienceBrowser` when you create a browser instance:

```python
from sentience import SentienceBrowser

with SentienceBrowser() as browser:
    browser.page.goto("https://example.com")
    # Extension is automatically loaded and active
```

## Development

For local development, you can use the development extension at `../sentience-chrome/` instead. The SDK will automatically detect and use it if available.

## Manual Update

If you need to manually update the extension files:

```bash
# Copy from sentience-chrome repo
cp ../sentience-chrome/manifest.json sentience/extension/
cp ../sentience-chrome/*.js sentience/extension/
cp -r ../sentience-chrome/pkg sentience/extension/
```

Or trigger the sync workflow manually:

```bash
gh workflow run sync-extension.yml -f release_tag=v1.0.0
```
