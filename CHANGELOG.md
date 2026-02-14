# Changelog

All notable changes to the Sentience Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### 2026-02-13

#### Expanded deterministic verifications (adaptive resnapshotting)

When you use `.eventually()` for deterministic checks, you can now **automatically increase the snapshot element limit across retries**. This helps on long / virtualized pages where a small snapshot limit can miss the target element, causing a false failure.

- **AgentRuntime verifications**: `AssertionHandle.eventually(..., snapshot_limit_growth=...)`
- **Expect-style verifications**: `with_eventually(..., snapshot_limit_growth=...)`
- **Commit**: `59125ce19001c457336dccbb3c9463560bd00245`

**Example**

```python
from predicate.verification import exists

# Grow snapshot limit on each retry until the element appears.
await dbg.check(exists("text~'Checkout'"), label="checkout_visible", required=True).eventually(
    timeout_s=12,
    snapshot_limit_growth={
        "start_limit": 60,
        "step": 40,
        "max_limit": 220,
        "apply_on": "only_on_fail",  # default; or "all"
    },
)
```

## [0.12.0] - 2025-12-26

### Added

#### Agent Tracing & Debugging
- **New Module: `predicate.tracing`** - Built-in tracing infrastructure for debugging and analyzing agent behavior
  - `Tracer` class for recording agent execution
  - `TraceSink` abstract base class for custom trace storage
  - `JsonlTraceSink` for saving traces to JSONL files
  - `TraceEvent` dataclass for structured trace events
  - Trace events: `step_start`, `snapshot`, `llm_query`, `action`, `step_end`, `error`
- **New Module: `predicate.agent_config`** - Centralized agent configuration
  - `AgentConfig` dataclass with defaults for snapshot limits, LLM settings, screenshot options
- **New Module: `predicate.utils`** - Snapshot digest utilities
  - `compute_snapshot_digests()` - Generate SHA256 fingerprints for loop detection
  - `canonical_snapshot_strict()` - Digest including element text
  - `canonical_snapshot_loose()` - Digest excluding text (layout only)
  - `sha256_digest()` - Hash computation helper
- **New Module: `predicate.formatting`** - LLM prompt formatting
  - `format_snapshot_for_llm()` - Convert snapshots to LLM-friendly text format
- **Schema File: `predicate/schemas/trace_v1.json`** - JSON Schema for trace events, bundled with package

#### Enhanced SentienceAgent
- Added optional `tracer` parameter to `SentienceAgent.__init__()` for execution tracking
- Added optional `config` parameter to `SentienceAgent.__init__()` for advanced configuration
- Automatic tracing throughout `act()` method when tracer is provided
- All tracing is **opt-in** - backward compatible with existing code

### Changed
- Bumped version from `0.11.0` to `0.12.0`
- Updated `__init__.py` to export new modules: `AgentConfig`, `Tracer`, `TraceSink`, `JsonlTraceSink`, `TraceEvent`, and utility functions
- Added `MANIFEST.in` to include JSON schema files in package distribution

### Fixed
- Fixed linting errors across multiple files:
  - `predicate/cli.py` - Removed unused variable `code` (F841)
  - `predicate/inspector.py` - Removed unused imports (F401)
  - `tests/test_inspector.py` - Removed unused `pytest` import (F401)
  - `tests/test_recorder.py` - Removed unused imports (F401)
  - `tests/test_smart_selector.py` - Removed unused `pytest` import (F401)
  - `tests/test_stealth.py` - Added `noqa` comments for intentional violations (E402, C901, F541)
  - `tests/test_tracing.py` - Removed unused `TraceSink` import (F401)

### Documentation
- Updated `README.md` with comprehensive "Advanced Features" section covering tracing and utilities
- Updated `docs/SDK_MANUAL.md` to v0.12.0 with new "Agent Tracing & Debugging" section
- Added examples for:
  - Basic tracing setup
  - AgentConfig usage
  - Snapshot digests for loop detection
  - LLM prompt formatting
  - Custom trace sinks

### Testing
- Added comprehensive test suites for new modules:
  - `tests/test_tracing.py` - 10 tests for tracing infrastructure
  - `tests/test_utils.py` - 22 tests for digest utilities
  - `tests/test_formatting.py` - 9 tests for LLM formatting
  - `tests/test_agent_config.py` - 9 tests for configuration
- All 50 new tests passing ✅

### Migration Guide

#### For Existing Users
No breaking changes! All new features are opt-in:

```python
# Old code continues to work exactly the same
agent = SentienceAgent(browser, llm)
agent.act("Click the button")

# New optional features
tracer = Tracer(run_id="run-123", sink=JsonlTraceSink("trace.jsonl"))
config = AgentConfig(snapshot_limit=100, temperature=0.5)
agent = SentienceAgent(browser, llm, tracer=tracer, config=config)
agent.act("Click the button")  # Now traced!
```

#### Importing New Modules

```python
# Tracing
from predicate.tracing import Tracer, JsonlTraceSink, TraceEvent, TraceSink

# Configuration
from predicate.agent_config import AgentConfig

# Utilities
from predicate.utils import (
    compute_snapshot_digests,
    canonical_snapshot_strict,
    canonical_snapshot_loose,
    sha256_digest
)

# Formatting
from predicate.formatting import format_snapshot_for_llm
```

### Notes
- This release focuses on developer experience and debugging capabilities
- No changes to browser automation APIs
- No changes to snapshot APIs
- No changes to query/action APIs
- Fully backward compatible with v0.11.0

---

## [0.11.0] - Previous Release

(Previous changelog entries would go here)
