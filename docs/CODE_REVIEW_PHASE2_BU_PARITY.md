# Code Review: Browser-Use Parity Phase 2 Implementation

**Date:** 2026-01-23
**Reviewer:** Claude
**Branch:** parity_win2
**Files Reviewed:** 4 modified + 7 new files
**Scope:** Phase 2 deliverables from BU_GAP_DELIVERABLES.md

---

## Summary

This PR implements all Phase 2 deliverables for Browser-Use parity:

| Deliverable | Status | Notes |
|-------------|--------|-------|
| ToolRegistry + typed schemas | ✅ Complete | Pydantic-based, LLM-ready specs |
| ToolContext/capability routing | ✅ Complete | `ctx.require()` pattern |
| Tool execution tracing | ✅ Complete | `tool_call` events emitted |
| Default tools registered | ✅ Complete | 7 core tools |
| Filesystem tools (sandboxed) | ✅ Complete | read/write/append/replace |
| Structured extraction | ✅ Complete | `extract(query, schema)` |

Overall the implementation is well-designed and aligns with the design docs. A few issues need attention.

---

## Design Doc Alignment

### CAPABILITY_ROUTING_DESIGN.md Compliance

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| `BackendCapabilities` model | [context.py:14-19](sentience/tools/context.py#L14-L19) | ✅ |
| `runtime.capabilities()` | [agent_runtime.py:378-389](sentience/agent_runtime.py#L378-L389) | ✅ |
| `runtime.can(name)` | [agent_runtime.py:391-393](sentience/agent_runtime.py#L391-L393) | ✅ |
| Structured "unsupported" errors | [context.py:43-45](sentience/tools/context.py#L43-L45) | ⚠️ Uses ValueError, not JSON |

### JS_EVALUATE_TOOL_DESIGN.md Compliance

The `evaluate_js` capability is flagged in `BackendCapabilities`, and the existing `runtime.evaluate_js()` from Phase 1 satisfies this requirement. The tool registry does **not** currently expose `evaluate_js` as a registered tool, which may be intentional.

---

## Critical Issues

### 1. `BackendCapabilities.downloads` and `filesystem_tools` missing

**File:** [context.py:14-19](sentience/tools/context.py#L14-L19)

The design doc specifies:
```python
class BackendCapabilities(BaseModel):
    tabs: bool = False
    evaluate_js: bool = True
    downloads: bool = True
    filesystem_tools: bool = False
```

But the implementation only has:
```python
class BackendCapabilities(BaseModel):
    tabs: bool = False
    evaluate_js: bool = False
    keyboard: bool = False
```

**Impact:** No way to check if filesystem tools are available before using them.

**Fix:** Add missing capability flags per design doc.

---

### 2. `ToolContext.require()` raises ValueError, not structured error

**File:** [context.py:43-45](sentience/tools/context.py#L43-L45)

```python
def require(self, name: str) -> None:
    if not self.can(name):
        raise ValueError(f"unsupported_capability: {name}")
```

The design doc (CAPABILITY_ROUTING_DESIGN.md) specifies structured errors:
```json
{ "error": "unsupported_capability", "detail": "tabs not supported by backend" }
```

**Impact:** LLM tool calls cannot distinguish unsupported capabilities from validation errors.

**Fix:** Create a custom `UnsupportedCapabilityError` exception or return a structured result.

---

## Medium Issues

### 3. Missing `evaluate_js` tool in default registry

**File:** [defaults.py](sentience/tools/defaults.py)

The registry registers 7 tools: `snapshot_state`, `click`, `type`, `scroll`, `scroll_to_element`, `click_rect`, `press`. However, `evaluate_js` is not registered despite being a key Phase 1/2 feature per the gap analysis.

**Suggestion:** Add an `evaluate_js` tool that wraps `runtime.evaluate_js()`.

---

### 4. `extract_async` does not use async LLM call

**File:** [read.py:237-277](sentience/read.py#L237-L277)

```python
async def extract_async(...) -> ExtractResult:
    # ...
    response = llm.generate(system, user)  # Sync call in async function
```

The `LLMProvider.generate()` is synchronous, so `extract_async` doesn't provide true async benefits.

**Suggestion:** Consider adding `generate_async()` to `LLMProvider` or document this limitation.

---

### 5. `FileSandbox` path validation may have edge cases

**File:** [filesystem.py:18-22](sentience/tools/filesystem.py#L18-L22)

```python
def _resolve(self, path: str) -> Path:
    candidate = (self.base_dir / path).resolve()
    if not str(candidate).startswith(str(self.base_dir)):
        raise ValueError("path escapes sandbox root")
    return candidate
```

The string prefix check could fail on edge cases like:
- `base_dir = /tmp/sandbox` and path resolves to `/tmp/sandbox2/file` (passes check incorrectly)

**Fix:** Use `candidate.is_relative_to(self.base_dir)` (Python 3.9+) instead of string prefix.

---

### 6. Duplicate capability logic in `AgentRuntime` and `ToolContext`

**Files:** [agent_runtime.py:378-393](sentience/agent_runtime.py#L378-L393), [context.py:37-41](sentience/tools/context.py#L37-L41)

Both classes implement `capabilities()` and `can()`. `ToolContext` delegates to `runtime`, which is correct, but the capability detection logic in `AgentRuntime.capabilities()` is complex:

```python
has_keyboard = hasattr(backend, "type_text") or bool(
    getattr(getattr(backend, "_page", None), "keyboard", None)
)
```

**Suggestion:** Consider moving capability detection to the backend protocol or making it more explicit.

---

## Minor Issues

### 7. `read.py` inconsistent return types fixed

The diff shows fixing inconsistent `dict` vs `ReadResult` returns:
```python
-return {
-    "status": "success",
-    ...
-}
+return ReadResult(
+    status="success",
+    ...
+)
```

This is a good fix.

---

### 8. Missing docstrings in new modules

**Files:** `context.py`, `defaults.py`, `filesystem.py`

The `ToolContext` and `FileSandbox` classes lack detailed docstrings explaining their purpose and usage patterns.

---

### 9. `defaults.py` has unused `Snapshot` import warning potential

**File:** [defaults.py:7](sentience/tools/defaults.py#L7)

```python
from ..models import ActionResult, BBox, Snapshot
```

`Snapshot` is used as the output model for `snapshot_state`, so this is correct. No issue.

---

## Test Coverage

The tests are comprehensive and well-structured:

| Test File | Coverage |
|-----------|----------|
| test_tool_registry.py | ✅ Registration, validation, LLM spec, execution, tracing, capability checks |
| test_filesystem_tools.py | ✅ Sandbox traversal prevention, CRUD operations |
| test_extract.py | ✅ Schema validation success/failure |

### Missing Test Cases

1. **`extract_async` test** - Only sync `extract` is tested
2. **Edge case for sandbox path validation** - Test `/tmp/sandbox` vs `/tmp/sandbox2` scenario
3. **`capabilities()` detection logic** - No test for `AgentRuntime.capabilities()`

---

## Architecture Assessment

The implementation follows a clean layered architecture:

```
┌─────────────────────────────────────┐
│           ToolRegistry              │  ← LLM-facing tool specs
├─────────────────────────────────────┤
│           ToolContext               │  ← Capability routing
├─────────────────────────────────────┤
│          AgentRuntime               │  ← Backend abstraction
├─────────────────────────────────────┤
│      PlaywrightBackend / CDP        │  ← Browser execution
└─────────────────────────────────────┘
```

This aligns with the design goal: *"unified SDK surface through AgentRuntime regardless of backend"*.

---

## Verdict

**Approve with required changes:**

1. **Must fix:** Add missing capability flags (`downloads`, `filesystem_tools`) per design doc
2. **Must fix:** Fix `FileSandbox._resolve()` to use `is_relative_to()` instead of string prefix
3. **Should fix:** Add `evaluate_js` tool to default registry

The Phase 2 deliverables are functionally complete. The tool registry design is solid and the filesystem sandbox provides good security boundaries.

---

## Appendix: Files Changed

### Modified Files

| File | Changes |
|------|---------|
| sentience/__init__.py | Export new tools module symbols |
| sentience/agent_runtime.py | Add `tool_registry`, `capabilities()`, `can()` |
| sentience/models.py | Add `ExtractResult` model |
| sentience/read.py | Add `extract()` / `extract_async()`, fix return types |

### New Files

| File | Purpose |
|------|---------|
| sentience/tools/__init__.py | Package exports |
| sentience/tools/registry.py | `ToolRegistry` and `ToolSpec` classes |
| sentience/tools/context.py | `ToolContext` and `BackendCapabilities` |
| sentience/tools/defaults.py | Default browser tool registrations |
| sentience/tools/filesystem.py | Sandboxed filesystem tools |
| tests/unit/test_tool_registry.py | Registry + execution tests |
| tests/unit/test_filesystem_tools.py | Sandbox + CRUD tests |
| tests/unit/test_extract.py | Extraction tests |
