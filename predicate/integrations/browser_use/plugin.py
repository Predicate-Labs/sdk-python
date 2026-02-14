from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from predicate.agent_runtime import AgentRuntime
from predicate.debugger import SentienceDebugger as PredicateDebugger
from predicate.integrations.models import AssertionResult, BrowserState, ElementSummary
from predicate.models import Snapshot, SnapshotOptions
from predicate.tracing import TraceSink, Tracer
from predicate.verification import Predicate


class _NoopTraceSink(TraceSink):
    def emit(self, event: dict[str, Any]) -> None:  # pragma: no cover
        return

    def close(self) -> None:  # pragma: no cover
        return


@dataclass(frozen=True)
class StepCheckSpec:
    predicate: Predicate
    label: str
    required: bool = True
    eventually: bool = True
    timeout_s: float = 10.0
    poll_s: float = 0.25
    max_snapshot_attempts: int = 3
    min_confidence: float | None = None


@dataclass
class PredicateBrowserUsePluginConfig:
    # Backend / binding
    predicate_api_key: str | None = None
    use_api: bool | None = None
    wait_for_extension_ms: int = 10_000
    bind_retries: int = 1

    # Snapshot defaults
    snapshot_options: SnapshotOptions = field(default_factory=SnapshotOptions)

    # Hybrid auto behavior
    auto_snapshot_each_step: bool = True
    auto_checks_each_step: bool = True
    auto_checks: list[StepCheckSpec] = field(default_factory=list)

    # Failure policy
    on_failure: Literal["raise", "pause", "log"] = "raise"

    # Tracing
    tracer: Tracer | None = None
    run_id: str | None = None


class PredicateBrowserUseVerificationError(RuntimeError):
    def __init__(self, message: str, *, results: list[AssertionResult] | None = None):
        super().__init__(message)
        self.results = results or []


class PredicateBrowserUsePlugin:
    """
    Browser Use “plugin” for Predicate deterministic verification.

    Integration surfaces:
    - lifecycle hooks: pass `plugin.on_step_start` / `plugin.on_step_end` to `agent.run(...)`
    - optional tools: `plugin.register_tools(Tools())`
    """

    def __init__(self, *, config: PredicateBrowserUsePluginConfig | None = None) -> None:
        self.config = config or PredicateBrowserUsePluginConfig()

        self._lock = asyncio.Lock()

        self._bound_session: Any | None = None
        self.runtime: AgentRuntime | None = None
        self.dbg: PredicateDebugger | None = None

        # Best-effort step counter if Browser Use does not expose one
        self._step_counter = 0

    async def bind(self, *, browser_session: Any) -> None:
        """
        Bind plugin to a Browser Use BrowserSession.

        Creates CDP backend via BrowserUseAdapter and wires AgentRuntime + PredicateDebugger.
        Safe to call multiple times; rebinds if session object changed.
        """
        async with self._lock:
            if browser_session is None:
                raise ValueError("browser_session is required")

            if self._bound_session is browser_session and self.runtime is not None and self.dbg is not None:
                return

            # Lazy import so predicate can be imported without browser-use installed.
            from predicate.backends import BrowserUseAdapter

            last_err: Exception | None = None
            for attempt in range(max(1, int(self.config.bind_retries)) + 1):
                try:
                    adapter = BrowserUseAdapter(browser_session)
                    backend = await adapter.create_backend()

                    tracer = self.config.tracer
                    if tracer is None:
                        run_id = self.config.run_id or str(uuid.uuid4())
                        tracer = Tracer(run_id=run_id, sink=_NoopTraceSink())

                    # Ensure snapshot options carry credentials and use_api policy.
                    snap_opts = self._effective_snapshot_options()
                    self.runtime = AgentRuntime(
                        backend=backend,
                        tracer=tracer,
                        snapshot_options=snap_opts,
                        predicate_api_key=self.config.predicate_api_key,
                    )
                    self.dbg = PredicateDebugger(runtime=self.runtime, auto_step=True)

                    self._bound_session = browser_session
                    return
                except Exception as e:  # pragma: no cover (backend-specific)
                    last_err = e
                    if attempt >= max(1, int(self.config.bind_retries)) + 1:
                        break
                    await asyncio.sleep(0.5 * attempt)

            raise RuntimeError(f"Failed to bind PredicateBrowserUsePlugin: {last_err}") from last_err

    def _effective_snapshot_options(self) -> SnapshotOptions:
        base = self.config.snapshot_options
        effective = SnapshotOptions(**base.model_dump())
        if self.config.predicate_api_key:
            effective.predicate_api_key = self.config.predicate_api_key
            effective.sentience_api_key = self.config.predicate_api_key
            if effective.use_api is None:
                effective.use_api = True
        if self.config.use_api is not None:
            effective.use_api = bool(self.config.use_api)
        return effective

    async def _maybe_get_current_url(self, agent: Any) -> str | None:
        session = getattr(agent, "browser_session", None)
        if session is None:
            return None
        fn = getattr(session, "get_current_page_url", None)
        if not callable(fn):
            return None
        try:
            v = fn()
            return await v if asyncio.iscoroutine(v) else str(v)
        except Exception:
            return None

    async def _wait_for_extension_ready(self, *, timeout_ms: int) -> None:
        """
        Wait until window.sentience.snapshot is available.
        """
        assert self.runtime is not None
        backend = self.runtime.backend
        deadline = time.monotonic() + max(0.0, float(timeout_ms) / 1000.0)

        async def _eval_with_timeout(expr: str, *, timeout_s: float = 2.0) -> Any:
            task = asyncio.create_task(backend.eval(expr))
            done, _pending = await asyncio.wait({task}, timeout=timeout_s)
            if task not in done:
                task.cancel()
                return "__EVAL_TIMEOUT__"
            try:
                return task.result()
            except Exception:
                return "__EVAL_ERROR__"

        last = None
        while time.monotonic() <= deadline:
            # Best-effort refresh execution context to avoid stale observations.
            try:
                reset = getattr(backend, "reset_execution_context", None)
                if callable(reset):
                    reset()
            except Exception:
                pass

            last = await _eval_with_timeout(
                "typeof window.sentience !== 'undefined' && typeof window.sentience.snapshot === 'function'"
            )
            if last not in ("__EVAL_TIMEOUT__", "__EVAL_ERROR__", False, None):
                return
            await asyncio.sleep(0.25)

        raise TimeoutError(
            f"Predicate extension not ready after {timeout_ms}ms (last={last})"
        )

    async def on_step_start(self, agent: Any) -> None:
        """
        Browser Use lifecycle hook: called at the beginning of each agent step.
        """
        session = getattr(agent, "browser_session", None)
        if session is None:
            raise RuntimeError("Browser Use agent has no `browser_session` attribute")

        await self.bind(browser_session=session)
        assert self.runtime is not None

        url = await self._maybe_get_current_url(agent)
        task = getattr(agent, "task", None)
        goal = str(task) if task is not None else "browser_use_step"
        if url:
            goal = f"{goal} @ {url}"

        # Keep steps stable even if Browser Use doesn't expose a step index.
        self._step_counter += 1
        self.runtime.begin_step(goal=goal, step_index=self.runtime.step_index + 1)

        # Best-effort readiness (avoid flakiness right after navigation).
        try:
            await self._wait_for_extension_ready(timeout_ms=int(self.config.wait_for_extension_ms))
        except Exception:
            # Non-fatal: snapshot() will retry; hook should not deadlock.
            pass

    async def wrap_step(
        self,
        agent: Any,
        step_coro: Awaitable[Any] | Callable[[], Awaitable[Any]],
    ) -> Any:
        """
        Convenience wrapper for Browser Use `agent.step()` flows.

        Browser Use step hooks are wired into `agent.run(...)`, but `agent.step()` does
        not accept hook parameters. This helper provides the same behavior:

        - await plugin.on_step_start(agent)
        - await agent.step()
        - await plugin.on_step_end(agent)

        It guarantees `on_step_end` runs via a `finally` block.
        """
        await self.on_step_start(agent)
        try:
            if callable(step_coro):
                return await step_coro()
            return await step_coro
        finally:
            await self.on_step_end(agent)

    async def on_step_end(self, agent: Any) -> None:
        """
        Browser Use lifecycle hook: called at the end of each agent step.
        """
        if self.runtime is None or self.dbg is None:
            # Bind lazily if hook is used standalone.
            session = getattr(agent, "browser_session", None)
            if session is None:
                raise RuntimeError("Browser Use agent has no `browser_session` attribute")
            await self.bind(browser_session=session)

        assert self.runtime is not None and self.dbg is not None

        results: list[AssertionResult] = []
        err: Exception | None = None
        try:
            if self.config.auto_snapshot_each_step:
                # Avoid injecting a very long Browser Use task string as the snapshot goal.
                # Callers can set `config.snapshot_options.goal` if they want goal-aware ranking.
                await self.dbg.snapshot()

            if self.config.auto_checks_each_step and self.config.auto_checks:
                for spec in self.config.auto_checks:
                    try:
                        h = self.dbg.check(spec.predicate, label=spec.label, required=spec.required)
                        if spec.eventually:
                            ok = await h.eventually(
                                timeout_s=spec.timeout_s,
                                poll_s=spec.poll_s,
                                max_snapshot_attempts=spec.max_snapshot_attempts,
                                min_confidence=spec.min_confidence,
                            )
                        else:
                            ok = h.once()
                        results.append(
                            AssertionResult(passed=bool(ok), reason="", details={"label": spec.label})
                        )
                        # `.once()` / `.eventually()` return booleans; they do not raise on failure.
                        # For required checks we treat a `False` result as a hard failure.
                        if spec.required and not bool(ok):
                            raise PredicateBrowserUseVerificationError(
                                f"Required check failed: {spec.label}",
                                results=results,
                            )
                    except Exception as e:
                        results.append(
                            AssertionResult(
                                passed=False,
                                reason=str(e),
                                details={"label": spec.label, "error_type": type(e).__name__},
                            )
                        )
                        raise
        except Exception as e:
            err = e
        finally:
            # Always attempt to close the step for trace completeness.
            try:
                await self.runtime.emit_step_end(
                    success=(err is None),
                    error=str(err) if err else None,
                )
            except Exception:
                pass

        if err is None:
            return

        if self.config.on_failure == "log":
            return

        if self.config.on_failure == "pause":
            pause = getattr(agent, "pause", None)
            if callable(pause):
                try:
                    pause()
                    return
                except Exception:
                    pass
            if isinstance(err, PredicateBrowserUseVerificationError):
                raise err
            raise PredicateBrowserUseVerificationError(str(err), results=results) from err

        # Default: raise
        if isinstance(err, PredicateBrowserUseVerificationError):
            raise err
        raise PredicateBrowserUseVerificationError(str(err), results=results) from err

    # ---------------------------------------------------------------------
    # Optional tools integration
    # ---------------------------------------------------------------------

    def register_tools(self, tools: Any) -> None:
        """
        Register Browser Use tools for explicit deterministic checks.

        This method must be called by user code that constructs `Tools()`.
        """
        # Import browser-use types lazily; keep this optional.
        try:
            import importlib

            browser_use = importlib.import_module("browser_use")
            ActionResult = getattr(browser_use, "ActionResult", None)
            BrowserSession = getattr(browser_use, "BrowserSession", None)
            if ActionResult is None or BrowserSession is None:
                raise ImportError("browser_use.ActionResult/BrowserSession not available")
        except Exception as e:  # pragma: no cover
            raise ImportError(
                "browser-use is required to register tools. Install with `predicatelabs[browser-use]`."
            ) from e

        if tools is None:
            raise ValueError("tools is required")

        @tools.action("Predicate: take a snapshot for deterministic verification")
        async def predicate_snapshot(  # type: ignore
            browser_session: Any,  # noqa: ARG001 (injected by browser-use)
            label: str | None = None,
            limit: int | None = None,
            screenshot: bool | None = None,
            show_overlay: bool | None = None,
        ) -> Any:
            await self.bind(browser_session=browser_session)
            assert self.runtime is not None
            opts = self._effective_snapshot_options()
            if label:
                opts.goal = label
            if limit is not None:
                opts.limit = int(limit)
            if screenshot is not None:
                opts.screenshot = bool(screenshot)
            if show_overlay is not None:
                opts.show_overlay = bool(show_overlay)
            snap = await self.runtime.snapshot(**opts.model_dump(exclude_none=True))
            return ActionResult(
                extracted_content=f"snapshot_ok url={snap.url} elements={len(snap.elements)}"
            )

        @tools.action("Predicate: deterministic check that URL contains text")
        async def predicate_check_url_contains(  # type: ignore
            text: str,
            browser_session: Any,
            label: str | None = None,
            required: bool = True,
            eventually: bool = True,
            timeout_s: float = 10.0,
        ) -> Any:
            from predicate.verification import url_contains

            await self.bind(browser_session=browser_session)
            assert self.dbg is not None
            lbl = label or f"url_contains:{text}"
            h = self.dbg.check(url_contains(text), label=lbl, required=bool(required))
            ok = await h.eventually(timeout_s=float(timeout_s)) if eventually else h.once()
            return ActionResult(extracted_content=f"check_ok={ok} label={lbl}")

        @tools.action("Predicate: deterministic check that selector exists")
        async def predicate_check_exists(  # type: ignore
            selector: str,
            browser_session: Any,
            label: str | None = None,
            required: bool = True,
            eventually: bool = True,
            timeout_s: float = 10.0,
        ) -> Any:
            from predicate.verification import exists

            await self.bind(browser_session=browser_session)
            assert self.dbg is not None
            lbl = label or f"exists:{selector}"
            h = self.dbg.check(exists(selector), label=lbl, required=bool(required))
            ok = await h.eventually(timeout_s=float(timeout_s)) if eventually else h.once()
            return ActionResult(extracted_content=f"check_ok={ok} label={lbl}")

    # ---------------------------------------------------------------------
    # Helpers for docs/tests (bounded summaries)
    # ---------------------------------------------------------------------

    @staticmethod
    def summarize_snapshot(snap: Snapshot, *, max_elements: int = 20) -> BrowserState:
        els: list[ElementSummary] = []
        for e in list(getattr(snap, "elements", []) or [])[: max(0, int(max_elements))]:
            els.append(
                ElementSummary(
                    id=int(getattr(e, "id", -1)),
                    role=str(getattr(e, "role", "")),
                    text=getattr(e, "text", None),
                    importance=getattr(e, "importance", None),
                    bbox=getattr(e, "bbox", None),
                )
            )
        return BrowserState(url=str(getattr(snap, "url", "")), elements=els)

