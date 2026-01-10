# Build SentienceContext for Browser-Use Agent Framework

## Relevant Files for Reference:
1.state_injector.py: `/Users/guoliangwang/Code/Python/browser-use/browser_use/integrations/sentience/state_injector.py`
2. Browser-use repo: `/Users/guoliangwang/Code/Python/browser-use`

## Task
You are implementing a “Token-Slasher Context Middleware” for browser-use users, shipped inside the Sentience SDK.

### Goal

Create a **directly importable** context class named `SentienceContext` that browser-use users can plug into their agent runtime to generate a compact, ranked DOM context block using Sentience snapshots, reducing tokens and improving reliability.

This should be implemented inside the Sentience SDK repo under:

* `sentience/backends/sentience_context.py` (new file)
* and exported from `sentience/backends/__init__.py`

It should refactor and supersede the logic currently in `state_injector.py` (which lives in a local browser-use repo copy). Use it as the baseline behavior, but remove debugging prints and improve robustness. 

Also integrate with the already-existing `BrowserUseAdapter` inside the SDK. 

---

## Requirements

### 1) Public API

Implement:

```py
@dataclass
class SentienceContextState:
    url: str
    snapshot: Snapshot
    prompt_block: str
    # optional: selected_element_ids: list[int]

class SentienceContext:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        use_api: bool | None = None,
        limit: int = 60,
        show_overlay: bool = False,
        top_by_importance: int = 60,
        top_from_dominant_group: int = 15,
        top_by_position: int = 10,
        role_link_when_href: bool = True,
        include_rank_in_group: bool = True,
        env_api_key: str = "SENTIENCE_API_KEY",
    ): ...

    async def build(
        self,
        browser_session: "BrowserSession",
        *,
        goal: str | None = None,
        wait_for_extension_ms: int = 5000,
        retries: int = 2,
        retry_delay_s: float = 1.0,
    ) -> SentienceContextState | None:
        """Return context state or None if snapshot isn’t available."""
```

Notes:

* `build()` must not throw for common failures; it should return `None` and log a warning.
* `goal` should be passed into SnapshotOptions (so gateway rerank can use it).
* Support both **extension-only mode** and **gateway mode** (if api_key exists or use_api=True).
* `api_key` defaults from env var `SENTIENCE_API_KEY` if not passed.
* Must avoid making browser-use a hard dependency (import types only under TYPE_CHECKING).

### 2) Snapshot acquisition (browser-use)

Use Sentience SDK’s existing integration pattern:

* Construct a `BrowserUseAdapter(browser_session)` and call `await adapter.create_backend()` (or equivalent) to obtain a backend for `sentience.backends.snapshot.snapshot()`.

Your `BrowserUseAdapter` exists and wraps CDP access. Don’t change its behavior except where necessary to make the context class clean. 

### 3) Formatting: compact prompt block

The prompt block should be a minimal token “inventory,” similar to `state_injector.py`:

* Output header:

  * `Elements: ID|role|text|imp|docYq|ord|DG|href` (compatible with existing)
* Then list lines `cur_line = f"{id}|{role}|{name}|{importance}|{doc_yq}|{ord_val}|{dg_flag}|{href}"`

BUT improvements required:

#### 3.1 Remove debug prints

The existing file prints group keys and formatted lines; remove those entirely. 

#### 3.2 Role semantics improvement (link vs button)

If `role_link_when_href=True`:

* If element has a non-empty `href`, output `role="link"` even if original role/tag is `button`.
* Else keep existing role.

This improves LLM priors for feed/list pages.

#### 3.3 Dominant group membership must NOT use exact match

Use `el.in_dominant_group` if present (preferred). That field is expected from gateway and uses fuzzy matching.
If it’s missing, fallback to exact match ONLY as last resort. (You already do this; keep it.) 

#### 3.4 Fix `ord_val` semantics (avoid huge values)

If `include_rank_in_group=True`:

* Prefer a true small ordinal index over `group_index` if `group_index` can be “bucket-like”.
  Implement:
* `rank_in_group`: computed locally in this formatter:

  * Take interactive elements where `in_dominant_group=True`
  * Sort them by `(doc_y, bbox.y, bbox.x, -importance)` using available fields
  * Assign `rank_in_group = 0..n-1`
* Then set:

  * `ord_val = rank_in_group` for dominant group items
  * otherwise `ord_val="-"`

Do NOT modify the Snapshot schema; compute this locally in the context builder.

Keep emitting `doc_yq` as `round(doc_y/200)` like current code, but ensure doc_y uses `el.doc_y` if present.

#### 3.5 `href` field: keep short token

Keep the current behavior of compressing href into a short token (domain second-level or last path segment). 

### 4) Element selection strategy (token slasher)

Replicate the selection recipe from `state_injector.py`:

* Filter to “interactive roles”
* Take:

  * top_by_importance
  * top_from_dominant_group
  * top_by_position (lowest doc_y)
* Deduplicate by element ID.

BUT make it robust:

* don’t rely on `snapshot.dominant_group_key` being present; use `in_dominant_group=True` filtering primarily.
* if `doc_y` missing, fallback to `bbox.y` if bbox exists.

### 5) Logging

Use `logging.getLogger(__name__)`.

* On ImportError: warn “Sentience SDK not available…”
* On snapshot failure: warn and include exception string.
* On success: info “SentienceContext snapshot: X elements URL=…”

No prints.

### 6) Packaging / exports

* Export `SentienceContext` and `SentienceContextState` from `sentience/backends/__init__.py`
* Keep browser-use as optional dependency (document usage in README; do not introduce mandatory dependency)
* Ensure type hints don’t import browser-use at runtime.

### 7) Example usage snippet

Provide an example in docstring or comments:

```py
from browser_use import Agent
from sentience.backends import SentienceContext

ctx = SentienceContext(show_overlay=True)
state = await ctx.build(agent.browser_session, goal="Click the first Show HN post")
if state:
    agent.add_context(state.prompt_block)  # or however browser-use injects state
```

Do not modify browser-use repo. This is SDK-only.

---

## Deliverables

1. `sentience/backends/sentience_context.py` new module
2. update `sentience/backends/__init__.py` exports
3. Ensure it compiles and is formatted
4. Keep behavior backwards compatible with existing compact line schema, but improve `role` and `ord_val` as above.

---

If you need to reference the baseline behavior, use the attached `state_injector.py` as the template. 

---

If you want, I can also give you a short "README integration snippet" for browser-use users (the 5-line copy/paste install + usage) once Claude produces the code.

---

## Feasibility & Complexity Assessment

### Overall Verdict: ✅ FEASIBLE - Medium Complexity

**Estimated effort:** 2-4 hours for Python SDK

---

### Prerequisites Analysis

| Prerequisite | Status | Notes |
|-------------|--------|-------|
| `BrowserUseAdapter` exists | ✅ Ready | `sentience/backends/browser_use_adapter.py` - wraps CDP for browser-use |
| `snapshot()` function exists | ✅ Ready | `sentience/backends/snapshot.py` - supports both extension and API modes |
| `Element` model has ordinal fields | ✅ Ready | `doc_y`, `group_key`, `group_index`, `href`, `in_dominant_group` all present |
| `Snapshot` model has `dominant_group_key` | ✅ Ready | Added in Phase 2 |
| `SnapshotOptions` supports `goal` | ✅ Ready | Line 139 in models.py |
| browser-use not a hard dependency | ✅ Ready | Already uses `TYPE_CHECKING` pattern |

---

### Complexity Breakdown by Requirement

| Requirement | Complexity | Rationale |
|-------------|------------|-----------|
| 1) Public API (`SentienceContext`, `SentienceContextState`) | 🟢 Low | Simple dataclass + class with `__init__` and `build()` |
| 2) Snapshot acquisition | 🟢 Low | Reuse existing `BrowserUseAdapter` + `snapshot()` |
| 3.1) Remove debug prints | 🟢 Low | Just don't add them |
| 3.2) Role link-when-href | 🟢 Low | Simple conditional: `"link" if href else role` |
| 3.3) Use `in_dominant_group` (fuzzy) | 🟢 Low | Field already exists from gateway |
| 3.4) Fix `ord_val` (local rank computation) | 🟡 Medium | Need to sort dominant group elements locally and assign 0..n-1 |
| 3.5) Short href token | 🟢 Low | URL parsing logic already in state_injector.py |
| 4) Element selection (token slasher) | 🟡 Medium | 3-way selection + deduplication, but logic is clear |
| 5) Logging | 🟢 Low | Standard `logging.getLogger(__name__)` |
| 6) Packaging/exports | 🟢 Low | Add 2 lines to `__init__.py` |
| 7) Example in docstring | 🟢 Low | Copy from design doc |

---

### Risk Areas

1. **`ord_val` local computation (Req 3.4)**: The design requires computing `rank_in_group` locally by sorting `in_dominant_group=True` elements. This is the right approach to fix the large `ord_val` issue, but requires careful implementation:
   - Sort key: `(doc_y or bbox.y, bbox.x, -importance)`
   - Must handle missing `doc_y` gracefully

2. **Retry logic**: The `build()` method has `retries` and `retry_delay_s` parameters. Need to implement exponential backoff or simple retry loop.

3. **Error handling**: Must catch exceptions from `snapshot()` and return `None` instead of propagating.

---

### Implementation Checklist

- [ ] Create `sentience/backends/sentience_context.py`
- [ ] Update `sentience/backends/__init__.py` with exports
- [ ] Test with browser-use locally

---

### Conclusion

This is a **well-scoped, medium-complexity task** with all prerequisites already in place. The main implementation work is:
1. Element selection logic (3-way merge with deduplication)
2. Local `rank_in_group` computation (sort + enumerate)
3. Compact line formatting

No schema changes or gateway modifications required. The gateway fix for `is_content_like_element` (MIN_CONTENT_TEXT_LENGTH=5) has already been implemented, which should reduce the large `ord_val` issue at the source.
