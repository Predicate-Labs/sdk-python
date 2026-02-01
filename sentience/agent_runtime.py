"""
Agent runtime for verification loop support.

This module provides a thin runtime wrapper that combines:
1. Browser session management (via BrowserBackend protocol)
2. Snapshot/query helpers
3. Tracer for event emission
4. Assertion/verification methods

The AgentRuntime is designed to be used in agent verification loops where
you need to repeatedly take snapshots, execute actions, and verify results.

Example usage with browser-use:
    from browser_use import BrowserSession, BrowserProfile
    from sentience import get_extension_dir
    from sentience.backends import BrowserUseAdapter
    from sentience.agent_runtime import AgentRuntime
    from sentience.verification import url_matches, exists
    from sentience.tracing import Tracer, JsonlTraceSink

    # Setup browser-use with Sentience extension
    profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"])
    session = BrowserSession(browser_profile=profile)
    await session.start()

    # Create adapter and backend
    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Navigate using browser-use
    page = await session.get_current_page()
    await page.goto("https://example.com")

    # Create runtime with backend
    sink = JsonlTraceSink("trace.jsonl")
    tracer = Tracer(run_id="test-run", sink=sink)
    runtime = AgentRuntime(backend=backend, tracer=tracer)

    # Take snapshot and run assertions
    await runtime.snapshot()
    runtime.assert_(url_matches(r"example\\.com"), label="on_homepage")
    runtime.assert_(exists("role=button"), label="has_buttons")

    # Check if task is done
    if runtime.assert_done(exists("text~'Success'"), label="task_complete"):
        print("Task completed!")

Example usage with AsyncSentienceBrowser (backward compatible):
    from sentience import AsyncSentienceBrowser
    from sentience.agent_runtime import AgentRuntime

    async with AsyncSentienceBrowser() as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")

        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser,
            page=page,
            tracer=tracer,
        )
        await runtime.snapshot()
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .captcha import (
    CaptchaContext,
    CaptchaHandlingError,
    CaptchaOptions,
    CaptchaResolution,
    PageControlHook,
)
from .failure_artifacts import FailureArtifactBuffer, FailureArtifactsOptions
from .models import (
    EvaluateJsRequest,
    EvaluateJsResult,
    Snapshot,
    SnapshotOptions,
    TabInfo,
    TabListResult,
    TabOperationResult,
)
from .tools import BackendCapabilities, ToolRegistry
from .trace_event_builder import TraceEventBuilder
from .verification import AssertContext, AssertOutcome, Predicate

if TYPE_CHECKING:
    from playwright.async_api import Page

    from .backends.protocol import BrowserBackend
    from .browser import AsyncSentienceBrowser
    from .tracing import Tracer


class AgentRuntime:
    """
    Runtime wrapper for agent verification loops.

    Provides ergonomic methods for:
    - snapshot(): Take page snapshot
    - assert_(): Evaluate assertion predicates
    - assert_done(): Assert task completion (required assertion)

    The runtime manages assertion state per step and emits verification events
    to the tracer for Studio timeline display.

    Attributes:
        backend: BrowserBackend instance for browser operations
        tracer: Tracer for event emission
        step_id: Current step identifier
        step_index: Current step index (0-based)
        last_snapshot: Most recent snapshot (for assertion context)
    """

    def __init__(
        self,
        backend: BrowserBackend,
        tracer: Tracer,
        snapshot_options: SnapshotOptions | None = None,
        sentience_api_key: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        """
        Initialize agent runtime with any BrowserBackend-compatible browser.

        Args:
            backend: Any browser implementing BrowserBackend protocol.
                     Examples:
                     - CDPBackendV0 (for browser-use via BrowserUseAdapter)
                     - PlaywrightBackend (future, for direct Playwright)
            tracer: Tracer for emitting verification events
            snapshot_options: Default options for snapshots
            sentience_api_key: API key for Pro/Enterprise tier (enables Gateway refinement)
            tool_registry: Optional ToolRegistry for LLM-callable tools
        """
        self.backend = backend
        self.tracer = tracer
        self.tool_registry = tool_registry

        # Build default snapshot options with API key if provided
        default_opts = snapshot_options or SnapshotOptions()
        if sentience_api_key:
            default_opts.sentience_api_key = sentience_api_key
            if default_opts.use_api is None:
                default_opts.use_api = True
        self._snapshot_options = default_opts

        # Step tracking
        self.step_id: str | None = None
        # 0-based step indexing (first auto-generated step_id is "step-0")
        self.step_index: int = -1

        # Snapshot state
        self.last_snapshot: Snapshot | None = None
        self._step_pre_snapshot: Snapshot | None = None
        self._step_pre_url: str | None = None

        # Failure artifacts (Phase 1)
        self._artifact_buffer: FailureArtifactBuffer | None = None
        self._artifact_timer_task: asyncio.Task | None = None

        # Cached URL (updated on snapshot or explicit get_url call)
        self._cached_url: str | None = None

        # Assertions accumulated during current step
        self._assertions_this_step: list[dict[str, Any]] = []
        self._step_goal: str | None = None
        self._last_action: str | None = None
        self._last_action_error: str | None = None
        self._last_action_outcome: str | None = None
        self._last_action_duration_ms: int | None = None
        self._last_action_success: bool | None = None

        # Task completion tracking
        self._task_done: bool = False
        self._task_done_label: str | None = None

        # CAPTCHA handling (optional, disabled by default)
        self._captcha_options: CaptchaOptions | None = None
        self._captcha_retry_count: int = 0

    @classmethod
    def from_playwright_page(
        cls,
        page: Page,
        tracer: Tracer,
        snapshot_options: SnapshotOptions | None = None,
        sentience_api_key: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> AgentRuntime:
        """
        Create AgentRuntime from a raw Playwright Page (sidecar mode).

        Args:
            page: Playwright Page for browser interaction
            tracer: Tracer for emitting verification events
            snapshot_options: Default options for snapshots
            sentience_api_key: API key for Pro/Enterprise tier
            tool_registry: Optional ToolRegistry for LLM-callable tools

        Returns:
            AgentRuntime instance
        """
        from .backends.playwright_backend import PlaywrightBackend

        backend = PlaywrightBackend(page)
        return cls(
            backend=backend,
            tracer=tracer,
            snapshot_options=snapshot_options,
            sentience_api_key=sentience_api_key,
            tool_registry=tool_registry,
        )

    @classmethod
    def attach(
        cls,
        page: Page,
        tracer: Tracer,
        snapshot_options: SnapshotOptions | None = None,
        sentience_api_key: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> AgentRuntime:
        """
        Sidecar alias for from_playwright_page().
        """
        return cls.from_playwright_page(
            page=page,
            tracer=tracer,
            snapshot_options=snapshot_options,
            sentience_api_key=sentience_api_key,
            tool_registry=tool_registry,
        )

    @classmethod
    async def from_sentience_browser(
        cls,
        browser: AsyncSentienceBrowser,
        page: Page,
        tracer: Tracer,
        snapshot_options: SnapshotOptions | None = None,
        sentience_api_key: str | None = None,
    ) -> AgentRuntime:
        """
        Create AgentRuntime from AsyncSentienceBrowser (backward compatibility).

        This factory method wraps an AsyncSentienceBrowser + Page combination
        into the new BrowserBackend-based AgentRuntime.

        Args:
            browser: AsyncSentienceBrowser instance
            page: Playwright Page for browser interaction
            tracer: Tracer for emitting verification events
            snapshot_options: Default options for snapshots
            sentience_api_key: API key for Pro/Enterprise tier

        Returns:
            AgentRuntime instance
        """
        from .backends.playwright_backend import PlaywrightBackend

        backend = PlaywrightBackend(page)
        runtime = cls(
            backend=backend,
            tracer=tracer,
            snapshot_options=snapshot_options,
            sentience_api_key=sentience_api_key,
        )
        # Store browser reference for snapshot() to use
        runtime._legacy_browser = browser
        runtime._legacy_page = page
        return runtime

    def _ctx(self) -> AssertContext:
        """
        Build assertion context from current state.

        Returns:
            AssertContext with current snapshot and URL
        """
        url = None
        if self.last_snapshot is not None:
            url = self.last_snapshot.url
        elif self._cached_url:
            url = self._cached_url

        downloads = None
        try:
            downloads = getattr(self.backend, "downloads", None)
        except Exception:
            downloads = None

        return AssertContext(
            snapshot=self.last_snapshot, url=url, step_id=self.step_id, downloads=downloads
        )

    async def get_url(self) -> str:
        """
        Get current page URL.

        Returns:
            Current page URL
        """
        url = await self.backend.get_url()
        self._cached_url = url
        return url

    async def snapshot(self, emit_trace: bool = True, **kwargs: Any) -> Snapshot:
        """
        Take a snapshot of the current page state.

        This updates last_snapshot which is used as context for assertions.
        When emit_trace=True (default), automatically emits a 'snapshot' trace event
        with screenshot_base64 for Sentience Studio visualization.

        Args:
            emit_trace: If True (default), emit a 'snapshot' trace event with screenshot.
                       Set to False to disable automatic trace emission.
            **kwargs: Override default snapshot options for this call.
                     Common options:
                     - limit: Maximum elements to return
                     - goal: Task goal for ordinal support
                     - screenshot: Include screenshot
                     - show_overlay: Show visual overlay

        Returns:
            Snapshot of current page state

        Example:
            >>> # Default: snapshot with auto-emit trace event
            >>> snapshot = await runtime.snapshot()

            >>> # Disable auto-emit for manual control
            >>> snapshot = await runtime.snapshot(emit_trace=False)
            >>> # Later, manually emit if needed:
            >>> tracer.emit_snapshot(snapshot, step_id=runtime.step_id)
        """
        # Check if using legacy browser (backward compat)
        if hasattr(self, "_legacy_browser") and hasattr(self, "_legacy_page"):
            self.last_snapshot = await self._legacy_browser.snapshot(self._legacy_page, **kwargs)
            if self.last_snapshot is not None:
                self._cached_url = self.last_snapshot.url
                if self._step_pre_snapshot is None:
                    self._step_pre_snapshot = self.last_snapshot
                    self._step_pre_url = self.last_snapshot.url
            # Auto-emit trace for legacy path too
            if emit_trace and self.last_snapshot is not None:
                self._emit_snapshot_trace(self.last_snapshot)
            return self.last_snapshot

        # Use backend-agnostic snapshot
        from .backends.snapshot import snapshot as backend_snapshot

        # Merge default options with call-specific kwargs
        skip_captcha_handling = bool(kwargs.pop("_skip_captcha_handling", False))
        options_dict = self._snapshot_options.model_dump(exclude_none=True)
        options_dict.update(kwargs)
        options = SnapshotOptions(**options_dict)

        self.last_snapshot = await backend_snapshot(self.backend, options=options)
        if self.last_snapshot is not None:
            self._cached_url = self.last_snapshot.url
            if self._step_pre_snapshot is None:
                self._step_pre_snapshot = self.last_snapshot
                self._step_pre_url = self.last_snapshot.url
        if not skip_captcha_handling:
            await self._handle_captcha_if_needed(self.last_snapshot, source="gateway")

        # Auto-emit snapshot trace event for Studio visualization
        if emit_trace and self.last_snapshot is not None:
            self._emit_snapshot_trace(self.last_snapshot)

        return self.last_snapshot

    def _emit_snapshot_trace(self, snapshot: Snapshot) -> None:
        """
        Emit a snapshot trace event with screenshot for Studio visualization.

        This is called automatically by snapshot() when emit_trace=True.
        """
        if self.tracer is None:
            return

        try:
            self.tracer.emit_snapshot(
                snapshot=snapshot,
                step_id=self.step_id,
                step_index=self.step_index,
                screenshot_format="jpeg",
            )
        except Exception:
            # Best-effort: don't let trace emission errors break snapshot
            pass

    async def sampled_snapshot(
        self,
        *,
        samples: int = 4,
        scroll_delta_y: float | None = None,
        settle_ms: int = 250,
        union_limit: int | None = None,
        restore_scroll: bool = True,
        **kwargs: Any,
    ) -> Snapshot:
        """
        Take multiple snapshots while scrolling and merge them into a "union snapshot".

        Intended for analysis/extraction on long / virtualized pages where a single
        viewport snapshot is insufficient.

        IMPORTANT:
        - The returned snapshot's element bboxes may not correspond to the current viewport.
          Do NOT use it for clicking unless you also scroll to the right position.
        - This method does NOT update `self.last_snapshot` (to avoid confusing verification
          loops that depend on the current viewport).
        """
        # Legacy browser path: fall back to a single snapshot (we can't rely on backend ops).
        if hasattr(self, "_legacy_browser") and hasattr(self, "_legacy_page"):
            return await self.snapshot(**kwargs)

        from .backends.snapshot import sampled_snapshot as backend_sampled_snapshot

        # Merge default options with call-specific kwargs
        options_dict = self._snapshot_options.model_dump(exclude_none=True)
        options_dict.update(kwargs)
        options = SnapshotOptions(**options_dict)

        snap = await backend_sampled_snapshot(
            self.backend,
            options=options,
            samples=samples,
            scroll_delta_y=scroll_delta_y,
            settle_ms=settle_ms,
            union_limit=union_limit,
            restore_scroll=restore_scroll,
        )
        return snap

    async def evaluate_js(self, request: EvaluateJsRequest) -> EvaluateJsResult:
        """
        Evaluate JavaScript expression in the active backend.

        Args:
            request: EvaluateJsRequest with code and output limits.

        Returns:
            EvaluateJsResult with normalized text output.
        """
        try:
            value = await self.backend.eval(request.code)
        except Exception as exc:  # pragma: no cover - backend-specific errors
            return EvaluateJsResult(ok=False, error=str(exc))

        text = self._stringify_eval_value(value)
        truncated = False
        if request.truncate and len(text) > request.max_output_chars:
            text = text[: request.max_output_chars] + "..."
            truncated = True

        return EvaluateJsResult(
            ok=True,
            value=value,
            text=text,
            truncated=truncated,
        )

    async def list_tabs(self) -> TabListResult:
        backend = self._get_tab_backend()
        if backend is None:
            return TabListResult(ok=False, error="unsupported_capability")
        try:
            tabs = await backend.list_tabs()
        except Exception as exc:  # pragma: no cover - backend specific
            return TabListResult(ok=False, error=str(exc))
        return TabListResult(ok=True, tabs=tabs)

    async def open_tab(self, url: str) -> TabOperationResult:
        backend = self._get_tab_backend()
        if backend is None:
            return TabOperationResult(ok=False, error="unsupported_capability")
        try:
            tab = await backend.open_tab(url)
        except Exception as exc:  # pragma: no cover - backend specific
            return TabOperationResult(ok=False, error=str(exc))
        return TabOperationResult(ok=True, tab=tab)

    async def switch_tab(self, tab_id: str) -> TabOperationResult:
        backend = self._get_tab_backend()
        if backend is None:
            return TabOperationResult(ok=False, error="unsupported_capability")
        try:
            tab = await backend.switch_tab(tab_id)
        except Exception as exc:  # pragma: no cover - backend specific
            return TabOperationResult(ok=False, error=str(exc))
        return TabOperationResult(ok=True, tab=tab)

    async def close_tab(self, tab_id: str) -> TabOperationResult:
        backend = self._get_tab_backend()
        if backend is None:
            return TabOperationResult(ok=False, error="unsupported_capability")
        try:
            tab = await backend.close_tab(tab_id)
        except Exception as exc:  # pragma: no cover - backend specific
            return TabOperationResult(ok=False, error=str(exc))
        return TabOperationResult(ok=True, tab=tab)

    def _get_tab_backend(self):
        backend = getattr(self, "backend", None)
        if backend is None:
            return None
        if not all(
            hasattr(backend, attr) for attr in ("list_tabs", "open_tab", "switch_tab", "close_tab")
        ):
            return None
        return backend

    def capabilities(self) -> BackendCapabilities:
        backend = getattr(self, "backend", None)
        if backend is None:
            return BackendCapabilities()
        has_eval = hasattr(backend, "eval")
        has_keyboard = hasattr(backend, "type_text") or bool(
            getattr(getattr(backend, "_page", None), "keyboard", None)
        )
        has_downloads = bool(getattr(backend, "downloads", None))
        has_permissions = False
        try:
            context = None
            legacy_browser = getattr(self, "_legacy_browser", None)
            if legacy_browser is not None:
                context = getattr(legacy_browser, "context", None)
            if context is None:
                page = getattr(backend, "_page", None) or getattr(backend, "page", None)
                context = getattr(page, "context", None) if page is not None else None
            if context is not None:
                has_permissions = bool(
                    hasattr(context, "clear_permissions") and hasattr(context, "grant_permissions")
                )
        except Exception:
            has_permissions = False
        has_files = False
        if self.tool_registry is not None:
            try:
                has_files = self.tool_registry.get("read_file") is not None
            except Exception:
                has_files = False
        return BackendCapabilities(
            tabs=self._get_tab_backend() is not None,
            evaluate_js=bool(has_eval),
            downloads=has_downloads,
            filesystem_tools=has_files,
            keyboard=bool(has_keyboard or has_eval),
            permissions=has_permissions,
        )

    def can(self, capability: str) -> bool:
        caps = self.capabilities()
        return bool(getattr(caps, capability, False))

    @staticmethod
    def _stringify_eval_value(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, (dict, list)):
            try:
                import json

                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value)

    def set_captcha_options(self, options: CaptchaOptions) -> None:
        """
        Configure CAPTCHA handling (disabled by default unless set).
        """
        self._captcha_options = options
        self._captcha_retry_count = 0

    def _is_captcha_detected(self, snapshot: Snapshot) -> bool:
        if not self._captcha_options:
            return False
        captcha = getattr(snapshot.diagnostics, "captcha", None) if snapshot.diagnostics else None
        if not captcha or not getattr(captcha, "detected", False):
            return False
        # IMPORTANT: Many sites load CAPTCHA libraries proactively. We only want to
        # block execution when there's evidence it's actually *present/active*.
        # If we block on low-signal detections (e.g. just a recaptcha script tag),
        # interactive runs will “do nothing” and time out.
        evidence = getattr(captcha, "evidence", None)
        if evidence is not None:

            def _list(name: str) -> list[str]:
                try:
                    v = getattr(evidence, name, None)
                except Exception:
                    v = None
                if v is None and isinstance(evidence, dict):
                    v = evidence.get(name)
                if not v:
                    return []
                return [str(x) for x in v if x is not None]

            iframe_hits = _list("iframe_src_hits")
            url_hits = _list("url_hits")
            text_hits = _list("text_hits")
            # If we only saw selector/script hints, treat as non-blocking.
            if not iframe_hits and not url_hits and not text_hits:
                return False
        confidence = getattr(captcha, "confidence", 0.0)
        return confidence >= self._captcha_options.min_confidence

    def _build_captcha_context(self, snapshot: Snapshot, source: str) -> CaptchaContext:
        captcha = getattr(snapshot.diagnostics, "captcha", None)
        return CaptchaContext(
            run_id=self.tracer.run_id,
            step_index=self.step_index,
            url=snapshot.url,
            source=source,  # type: ignore[arg-type]
            captcha=captcha,
            page_control=self._create_captcha_page_control(),
        )

    def _create_captcha_page_control(self) -> PageControlHook:
        async def _eval(code: str) -> Any:
            result = await self.evaluate_js(EvaluateJsRequest(code=code))
            if not result.ok:
                raise RuntimeError(result.error or "evaluate_js failed")
            return result.value

        return PageControlHook(evaluate_js=_eval)

    def _emit_captcha_event(self, reason_code: str, details: dict[str, Any] | None = None) -> None:
        payload = {
            "kind": "captcha",
            "passed": False,
            "label": reason_code,
            "details": {"reason_code": reason_code, **(details or {})},
        }
        self.tracer.emit("verification", data=payload, step_id=self.step_id)

    async def _handle_captcha_if_needed(self, snapshot: Snapshot, source: str) -> None:
        if not self._captcha_options:
            return
        if not self._is_captcha_detected(snapshot):
            return

        captcha = getattr(snapshot.diagnostics, "captcha", None)
        self._emit_captcha_event(
            "captcha_detected",
            {"captcha": getattr(captcha, "model_dump", lambda: captcha)()},
        )

        resolution: CaptchaResolution
        if self._captcha_options.policy == "callback":
            if not self._captcha_options.handler:
                self._emit_captcha_event("captcha_handler_error")
                raise CaptchaHandlingError(
                    "captcha_handler_error",
                    'Captcha handler is required for policy="callback".',
                )
            try:
                resolution = await self._captcha_options.handler(
                    self._build_captcha_context(snapshot, source)
                )
            except Exception as exc:  # pragma: no cover - defensive
                self._emit_captcha_event("captcha_handler_error", {"error": str(exc)})
                raise CaptchaHandlingError(
                    "captcha_handler_error", "Captcha handler failed."
                ) from exc
        else:
            resolution = CaptchaResolution(action="abort")

        await self._apply_captcha_resolution(resolution, snapshot, source)

    async def _apply_captcha_resolution(
        self,
        resolution: CaptchaResolution,
        snapshot: Snapshot,
        source: str,
    ) -> None:
        if resolution.action == "abort":
            self._emit_captcha_event("captcha_policy_abort", {"message": resolution.message})
            raise CaptchaHandlingError(
                "captcha_policy_abort",
                resolution.message or "Captcha detected. Aborting per policy.",
            )

        if resolution.action == "retry_new_session":
            self._captcha_retry_count += 1
            self._emit_captcha_event("captcha_retry_new_session")
            if self._captcha_retry_count > self._captcha_options.max_retries_new_session:
                self._emit_captcha_event("captcha_retry_exhausted")
                raise CaptchaHandlingError(
                    "captcha_retry_exhausted",
                    "Captcha retry_new_session exhausted.",
                )
            if not self._captcha_options.reset_session:
                raise CaptchaHandlingError(
                    "captcha_retry_new_session",
                    "reset_session callback is required for retry_new_session.",
                )
            await self._captcha_options.reset_session()
            return

        if resolution.action == "wait_until_cleared":
            timeout_ms = resolution.timeout_ms or self._captcha_options.timeout_ms
            poll_ms = resolution.poll_ms or self._captcha_options.poll_ms
            await self._wait_until_cleared(timeout_ms=timeout_ms, poll_ms=poll_ms, source=source)
            self._emit_captcha_event("captcha_resumed")

    async def _wait_until_cleared(self, *, timeout_ms: int, poll_ms: int, source: str) -> None:
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() <= deadline:
            await asyncio.sleep(poll_ms / 1000.0)
            snap = await self.snapshot(_skip_captcha_handling=True)
            if not self._is_captcha_detected(snap):
                self._emit_captcha_event("captcha_cleared", {"source": source})
                return
        self._emit_captcha_event("captcha_wait_timeout", {"timeout_ms": timeout_ms})
        raise CaptchaHandlingError("captcha_wait_timeout", "Captcha wait_until_cleared timed out.")

    async def enable_failure_artifacts(
        self,
        options: FailureArtifactsOptions | None = None,
    ) -> None:
        """
        Enable failure artifact buffer (Phase 1).
        """
        opts = options or FailureArtifactsOptions()
        self._artifact_buffer = FailureArtifactBuffer(
            run_id=self.tracer.run_id,
            options=opts,
        )
        if opts.fps > 0:
            self._artifact_timer_task = asyncio.create_task(self._artifact_timer_loop())

    def disable_failure_artifacts(self) -> None:
        """
        Disable failure artifact buffer and stop background capture.
        """
        if self._artifact_timer_task:
            self._artifact_timer_task.cancel()
            self._artifact_timer_task = None

    async def record_action(
        self,
        action: str,
        *,
        url: str | None = None,
    ) -> None:
        """
        Record an action in the artifact timeline and capture a frame if enabled.
        """
        self._last_action = action
        if not self._artifact_buffer:
            return
        self._artifact_buffer.record_step(
            action=action,
            step_id=self.step_id,
            step_index=self.step_index,
            url=url,
        )
        if self._artifact_buffer.options.capture_on_action:
            await self._capture_artifact_frame()

    def _compute_snapshot_digest(self, snap: Snapshot | None) -> str | None:
        if snap is None:
            return None
        try:
            return "sha256:" + hashlib.sha256(f"{snap.url}{snap.timestamp}".encode()).hexdigest()
        except Exception:
            return None

    async def emit_step_end(
        self,
        *,
        action: str | None = None,
        success: bool | None = None,
        error: str | None = None,
        outcome: str | None = None,
        duration_ms: int | None = None,
        attempt: int = 0,
        verify_passed: bool | None = None,
        verify_signals: dict[str, Any] | None = None,
        post_url: str | None = None,
        post_snapshot_digest: str | None = None,
    ) -> dict[str, Any]:
        """
        Emit a step_end event using TraceEventBuilder.
        """
        goal = self._step_goal or ""
        pre_snap = self._step_pre_snapshot or self.last_snapshot
        pre_url = (
            self._step_pre_url or (pre_snap.url if pre_snap else None) or self._cached_url or ""
        )

        if post_url is None:
            try:
                post_url = await self.get_url()
            except Exception:
                post_url = (
                    self.last_snapshot.url if self.last_snapshot else None
                ) or self._cached_url
        post_url = post_url or pre_url

        pre_digest = self._compute_snapshot_digest(pre_snap)
        post_digest = post_snapshot_digest or self._compute_snapshot_digest(self.last_snapshot)
        url_changed = bool(pre_url and post_url and str(pre_url) != str(post_url))

        assertions_data = self.get_assertions_for_step_end()
        assertions = assertions_data.get("assertions") or []

        signals = dict(verify_signals or {})
        signals.setdefault("url_changed", url_changed)
        if error and "error" not in signals:
            signals["error"] = error

        passed = (
            bool(verify_passed) if verify_passed is not None else self.required_assertions_passed()
        )

        exec_success = (
            bool(success)
            if success is not None
            else bool(
                self._last_action_success if self._last_action_success is not None else passed
            )
        )

        exec_data: dict[str, Any] = {
            "success": exec_success,
            "action": action or self._last_action or "unknown",
            "outcome": outcome or self._last_action_outcome or "",
        }
        if duration_ms is not None:
            exec_data["duration_ms"] = int(duration_ms)
        if error:
            exec_data["error"] = error

        verify_data = {
            "passed": bool(passed),
            "signals": signals,
        }

        step_end_data = TraceEventBuilder.build_step_end_event(
            step_id=self.step_id or "",
            step_index=int(self.step_index),
            goal=goal,
            attempt=int(attempt),
            pre_url=str(pre_url or ""),
            post_url=str(post_url or ""),
            snapshot_digest=pre_digest,
            llm_data={},
            exec_data=exec_data,
            verify_data=verify_data,
            pre_elements=None,
            assertions=assertions,
            post_snapshot_digest=post_digest,
        )
        self.tracer.emit("step_end", step_end_data, step_id=self.step_id)
        return step_end_data

    async def end_step(self, **kwargs: Any) -> dict[str, Any]:
        """
        User-friendly alias for emit_step_end().

        This keeps step lifecycle naming symmetric with begin_step().
        """
        return await self.emit_step_end(**kwargs)

    async def _capture_artifact_frame(self) -> None:
        if not self._artifact_buffer:
            return
        try:
            fmt = self._artifact_buffer.options.frame_format
            if fmt == "jpeg":
                image_bytes = await self.backend.screenshot_jpeg()
            else:
                image_bytes = await self.backend.screenshot_png()
        except Exception:
            return
        self._artifact_buffer.add_frame(image_bytes, fmt=fmt)

    async def _artifact_timer_loop(self) -> None:
        if not self._artifact_buffer:
            return
        interval = 1.0 / max(0.001, self._artifact_buffer.options.fps)
        try:
            while True:
                await self._capture_artifact_frame()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return

    def finalize_run(self, *, success: bool) -> None:
        """
        Finalize artifact buffer at end of run.
        """
        if not self._artifact_buffer:
            return
        if success:
            if self._artifact_buffer.options.persist_mode == "always":
                self._artifact_buffer.persist(
                    reason="success",
                    status="success",
                    snapshot=self.last_snapshot,
                    diagnostics=getattr(self.last_snapshot, "diagnostics", None),
                    metadata=self._artifact_metadata(),
                )
            self._artifact_buffer.cleanup()
        else:
            self._persist_failure_artifacts(reason="finalize_failure")

    def _persist_failure_artifacts(self, *, reason: str) -> None:
        if not self._artifact_buffer:
            return
        self._artifact_buffer.persist(
            reason=reason,
            status="failure",
            snapshot=self.last_snapshot,
            diagnostics=getattr(self.last_snapshot, "diagnostics", None),
            metadata=self._artifact_metadata(),
        )
        self._artifact_buffer.cleanup()
        if self._artifact_buffer.options.persist_mode == "onFail":
            self.disable_failure_artifacts()

    def _artifact_metadata(self) -> dict[str, Any]:
        url = None
        if self.last_snapshot is not None:
            url = self.last_snapshot.url
        elif self._cached_url:
            url = self._cached_url
        return {
            "backend": self.backend.__class__.__name__,
            "url": url,
        }

    def begin_step(
        self,
        goal: str,
        step_index: int | None = None,
        emit_trace: bool = True,
        pre_url: str | None = None,
    ) -> str:
        """
        Begin a new step in the verification loop.

        This:
        - Generates a new step_id
        - Clears assertions from previous step
        - Increments step_index (or uses provided value)
        - Emits step_start trace event (optional)

        Args:
            goal: Description of what this step aims to achieve
            step_index: Optional explicit step index (otherwise auto-increments)
            emit_trace: If True (default), emit step_start trace event for Studio timeline
            pre_url: Optional URL to record in step_start event (otherwise uses cached URL)

        Returns:
            Generated step_id in format 'step-N' where N is the step index
        """
        # Clear previous step state
        self._assertions_this_step = []
        self._step_pre_snapshot = None
        self._step_pre_url = None
        self._step_goal = goal
        self._last_action = None
        self._last_action_error = None
        self._last_action_outcome = None
        self._last_action_duration_ms = None
        self._last_action_success = None

        # Update step index
        if step_index is not None:
            self.step_index = step_index
        else:
            self.step_index += 1

        # Generate step_id in 'step-N' format for Studio compatibility
        self.step_id = f"step-{self.step_index}"

        # Emit step_start trace event for Studio timeline display
        if emit_trace and self.tracer:
            try:
                url = pre_url or self._cached_url or ""
                self.tracer.emit_step_start(
                    step_id=self.step_id,
                    step_index=self.step_index,
                    goal=goal,
                    attempt=0,
                    pre_url=url,
                )
            except Exception:
                pass  # Tracing must be non-fatal

        return self.step_id

    def assert_(
        self,
        predicate: Predicate,
        label: str,
        required: bool = False,
    ) -> bool:
        """
        Evaluate an assertion against current snapshot state.

        The assertion result is:
        1. Accumulated for inclusion in step_end.data.verify.signals.assertions
        2. Emitted as a dedicated 'verification' event for Studio timeline

        Args:
            predicate: Predicate function to evaluate
            label: Human-readable label for this assertion
            required: If True, this assertion gates step success (default: False)

        Returns:
            True if assertion passed, False otherwise
        """
        outcome = predicate(self._ctx())
        self._record_outcome(
            outcome=outcome,
            label=label,
            required=required,
            kind="assert",
            record_in_step=True,
        )
        if required and not outcome.passed:
            self._persist_failure_artifacts(reason=f"assert_failed:{label}")
        return outcome.passed

    def check(self, predicate: Predicate, label: str, required: bool = False) -> AssertionHandle:
        """
        Create an AssertionHandle for fluent `.once()` / `.eventually()` usage.

        This does NOT evaluate the predicate immediately.
        """

        return AssertionHandle(runtime=self, predicate=predicate, label=label, required=required)

    def assert_done(
        self,
        predicate: Predicate,
        label: str,
    ) -> bool:
        """
        Assert task completion (required assertion).

        This is a convenience wrapper for assert_() with required=True.
        When the assertion passes, it marks the task as done.

        Use this for final verification that the agent's goal is complete.

        Args:
            predicate: Predicate function to evaluate
            label: Human-readable label for this assertion

        Returns:
            True if task is complete (assertion passed), False otherwise
        """
        # Convenience wrapper for assert_ with required=True
        # pylint: disable=deprecated-method
        ok = self.assert_(predicate, label=label, required=True)
        # pylint: enable=deprecated-method
        if ok:
            self._task_done = True
            self._task_done_label = label

            # Emit task_done verification event
            self.tracer.emit(
                "verification",
                data={
                    "kind": "task_done",
                    "passed": True,
                    "label": label,
                },
                step_id=self.step_id,
            )

        return ok

    def _record_outcome(
        self,
        *,
        outcome: Any,
        label: str,
        required: bool,
        kind: str,
        record_in_step: bool,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """
        Internal helper: emit verification event and optionally accumulate for step_end.
        """
        details = dict(outcome.details or {})

        # Failure intelligence: nearest matches for selector-driven assertions
        if not outcome.passed and self.last_snapshot is not None and "selector" in details:
            selector = str(details.get("selector") or "")
            details.setdefault("nearest_matches", self._nearest_matches(selector, limit=3))

        record = {
            "label": label,
            "passed": bool(outcome.passed),
            "required": required,
            "reason": str(outcome.reason or ""),
            "details": details,
        }
        if extra:
            record.update(extra)

        if record_in_step:
            self._assertions_this_step.append(record)

        self.tracer.emit(
            "verification",
            data={
                "kind": kind,
                "passed": bool(outcome.passed),
                **record,
            },
            step_id=self.step_id,
        )

    def _nearest_matches(self, selector: str, *, limit: int = 3) -> list[dict[str, Any]]:
        """
        Best-effort nearest match suggestions for debugging failed selector assertions.
        """
        if self.last_snapshot is None:
            return []

        s = selector.lower().strip()
        if not s:
            return []

        scored: list[tuple[float, Any]] = []
        for el in self.last_snapshot.elements:
            hay = (getattr(el, "name", None) or getattr(el, "text", None) or "").strip()
            if not hay:
                continue
            score = difflib.SequenceMatcher(None, s, hay.lower()).ratio()
            scored.append((score, el))

        scored.sort(key=lambda t: t[0], reverse=True)
        out: list[dict[str, Any]] = []
        for score, el in scored[:limit]:
            out.append(
                {
                    "id": getattr(el, "id", None),
                    "role": getattr(el, "role", None),
                    "text": (getattr(el, "text", "") or "")[:80],
                    "name": (getattr(el, "name", "") or "")[:80],
                    "score": round(float(score), 4),
                }
            )
        return out

    def get_assertions_for_step_end(self) -> dict[str, Any]:
        """
        Get assertions data for inclusion in step_end.data.verify.signals.

        Returns:
            Dictionary with 'assertions', 'task_done', 'task_done_label' keys
        """
        result: dict[str, Any] = {
            "assertions": self._assertions_this_step.copy(),
        }

        if self._task_done:
            result["task_done"] = True
            result["task_done_label"] = self._task_done_label

        return result

    def flush_assertions(self) -> list[dict[str, Any]]:
        """
        Get and clear assertions for current step.
        """
        assertions = self._assertions_this_step.copy()
        self._assertions_this_step = []
        return assertions

    @property
    def is_task_done(self) -> bool:
        """Check if task has been marked as done via assert_done()."""
        return self._task_done

    def reset_task_done(self) -> None:
        """Reset task_done state (for multi-task runs)."""
        self._task_done = False
        self._task_done_label = None

    def all_assertions_passed(self) -> bool:
        """Return True if all assertions in current step passed (or none)."""
        return all(a["passed"] for a in self._assertions_this_step)

    def required_assertions_passed(self) -> bool:
        """Return True if all required assertions in current step passed (or none)."""
        required = [a for a in self._assertions_this_step if a.get("required")]
        return all(a["passed"] for a in required)


@dataclass
class AssertionHandle:
    runtime: AgentRuntime
    predicate: Predicate
    label: str
    required: bool = False

    def once(self) -> bool:
        """Evaluate once (same behavior as runtime.assert_)."""
        return self.runtime.assert_(self.predicate, label=self.label, required=self.required)

    async def eventually(
        self,
        *,
        timeout_s: float = 10.0,
        poll_s: float = 0.25,
        min_confidence: float | None = None,
        max_snapshot_attempts: int = 3,
        snapshot_kwargs: dict[str, Any] | None = None,
        vision_provider: Any | None = None,
        vision_system_prompt: str | None = None,
        vision_user_prompt: str | None = None,
    ) -> bool:
        """
        Retry until the predicate passes or timeout is reached.

        Intermediate attempts emit verification events but do NOT accumulate in step_end assertions.
        Final result is accumulated once.
        """
        deadline = time.monotonic() + timeout_s
        attempt = 0
        snapshot_attempt = 0
        last_outcome = None

        while True:
            attempt += 1
            await self.runtime.snapshot(**(snapshot_kwargs or {}))
            snapshot_attempt += 1

            # Optional: gate predicate evaluation on snapshot confidence.
            # If diagnostics are missing, we don't block (backward compatible).
            confidence = None
            diagnostics = None
            if self.runtime.last_snapshot is not None:
                diagnostics = getattr(self.runtime.last_snapshot, "diagnostics", None)
                if diagnostics is not None:
                    confidence = getattr(diagnostics, "confidence", None)

            if (
                min_confidence is not None
                and confidence is not None
                and isinstance(confidence, (int, float))
                and confidence < min_confidence
            ):
                last_outcome = AssertOutcome(
                    passed=False,
                    reason=f"Snapshot confidence {confidence:.3f} < min_confidence {min_confidence:.3f}",
                    details={
                        "reason_code": "snapshot_low_confidence",
                        "confidence": confidence,
                        "min_confidence": min_confidence,
                        "snapshot_attempt": snapshot_attempt,
                        "diagnostics": (
                            diagnostics.model_dump()
                            if hasattr(diagnostics, "model_dump")
                            else diagnostics
                        ),
                    },
                )

                # Emit attempt event (not recorded in step_end)
                self.runtime._record_outcome(
                    outcome=last_outcome,
                    label=self.label,
                    required=self.required,
                    kind="assert",
                    record_in_step=False,
                    extra={
                        "eventually": True,
                        "attempt": attempt,
                        "snapshot_attempt": snapshot_attempt,
                    },
                )

                if snapshot_attempt >= max_snapshot_attempts:
                    # Optional: vision fallback as last resort (Phase 2-lite).
                    # This keeps the assertion surface invariant; only the perception layer changes.
                    if (
                        vision_provider is not None
                        and getattr(vision_provider, "supports_vision", lambda: False)()
                    ):
                        try:
                            import base64

                            png_bytes = await self.runtime.backend.screenshot_png()
                            image_b64 = base64.b64encode(png_bytes).decode("utf-8")

                            sys_prompt = vision_system_prompt or (
                                "You are a strict visual verifier. Answer only YES or NO."
                            )
                            user_prompt = vision_user_prompt or (
                                f"Given the screenshot, is the following condition satisfied?\n\n{self.label}\n\nAnswer YES or NO."
                            )

                            resp = vision_provider.generate_with_image(
                                sys_prompt,
                                user_prompt,
                                image_base64=image_b64,
                                temperature=0.0,
                            )
                            text = (resp.content or "").strip().lower()
                            passed = text.startswith("yes")

                            final_outcome = AssertOutcome(
                                passed=passed,
                                reason="vision_fallback_yes" if passed else "vision_fallback_no",
                                details={
                                    "reason_code": (
                                        "vision_fallback_pass" if passed else "vision_fallback_fail"
                                    ),
                                    "vision_response": resp.content,
                                    "min_confidence": min_confidence,
                                    "snapshot_attempts": snapshot_attempt,
                                },
                            )
                            self.runtime._record_outcome(
                                outcome=final_outcome,
                                label=self.label,
                                required=self.required,
                                kind="assert",
                                record_in_step=True,
                                extra={
                                    "eventually": True,
                                    "attempt": attempt,
                                    "snapshot_attempt": snapshot_attempt,
                                    "final": True,
                                    "vision_fallback": True,
                                },
                            )
                            if self.required and not passed:
                                self.runtime._persist_failure_artifacts(
                                    reason=f"assert_eventually_failed:{self.label}"
                                )
                            return passed
                        except Exception as e:
                            # If vision fallback fails, fall through to snapshot_exhausted.
                            last_outcome.details["vision_error"] = str(e)

                    final_outcome = AssertOutcome(
                        passed=False,
                        reason=f"Snapshot exhausted after {snapshot_attempt} attempt(s) below min_confidence {min_confidence:.3f}",
                        details={
                            "reason_code": "snapshot_exhausted",
                            "confidence": confidence,
                            "min_confidence": min_confidence,
                            "snapshot_attempts": snapshot_attempt,
                            "diagnostics": last_outcome.details.get("diagnostics"),
                        },
                    )
                    self.runtime._record_outcome(
                        outcome=final_outcome,
                        label=self.label,
                        required=self.required,
                        kind="assert",
                        record_in_step=True,
                        extra={
                            "eventually": True,
                            "attempt": attempt,
                            "snapshot_attempt": snapshot_attempt,
                            "final": True,
                            "exhausted": True,
                        },
                    )
                    if self.required:
                        self.runtime._persist_failure_artifacts(
                            reason=f"assert_eventually_failed:{self.label}"
                        )
                    return False

                if time.monotonic() >= deadline:
                    self.runtime._record_outcome(
                        outcome=last_outcome,
                        label=self.label,
                        required=self.required,
                        kind="assert",
                        record_in_step=True,
                        extra={
                            "eventually": True,
                            "attempt": attempt,
                            "snapshot_attempt": snapshot_attempt,
                            "final": True,
                            "timeout": True,
                        },
                    )
                    if self.required:
                        self.runtime._persist_failure_artifacts(
                            reason=f"assert_eventually_timeout:{self.label}"
                        )
                    return False

                await asyncio.sleep(poll_s)
                continue

            last_outcome = self.predicate(self.runtime._ctx())

            # Emit attempt event (not recorded in step_end)
            self.runtime._record_outcome(
                outcome=last_outcome,
                label=self.label,
                required=self.required,
                kind="assert",
                record_in_step=False,
                extra={"eventually": True, "attempt": attempt},
            )

            if last_outcome.passed:
                # Record final success once
                self.runtime._record_outcome(
                    outcome=last_outcome,
                    label=self.label,
                    required=self.required,
                    kind="assert",
                    record_in_step=True,
                    extra={"eventually": True, "attempt": attempt, "final": True},
                )
                return True

            if time.monotonic() >= deadline:
                # Record final failure once
                self.runtime._record_outcome(
                    outcome=last_outcome,
                    label=self.label,
                    required=self.required,
                    kind="assert",
                    record_in_step=True,
                    extra={"eventually": True, "attempt": attempt, "final": True, "timeout": True},
                )
                if self.required:
                    self.runtime._persist_failure_artifacts(
                        reason=f"assert_eventually_timeout:{self.label}"
                    )
                return False

            await asyncio.sleep(poll_s)
