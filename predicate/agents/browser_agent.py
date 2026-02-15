from __future__ import annotations

import importlib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from ..agent_runtime import AgentRuntime
from ..captcha import CaptchaHandler, CaptchaOptions
from ..captcha_strategies import ExternalSolver, HumanHandoffSolver, VisionSolver
from ..llm_interaction_handler import LLMInteractionHandler
from ..llm_provider import LLMProvider
from ..models import Snapshot, StepHookContext
from ..permissions import PermissionPolicy
from ..runtime_agent import RuntimeAgent, RuntimeStep


@dataclass(frozen=True)
class PermissionRecoveryConfig:
    """
    Configuration for a bounded "permission recovery" policy.

    Note: startup permissions are applied at browser/context creation time via
    `PermissionPolicy`. Recovery is intentionally best-effort and may require a
    browser/context-level integration (outside AgentRuntime) depending on backend.
    """

    enabled: bool = True
    max_restarts: int = 1
    auto_grant: list[str] = field(default_factory=list)
    geolocation: dict | None = None
    origin: str | None = None


@dataclass(frozen=True)
class VisionFallbackConfig:
    """
    Controls if/when the agent may use a vision executor as a bounded fallback.
    """

    enabled: bool = False
    max_vision_calls: int = 0
    trigger_requires_vision: bool = True
    trigger_repeated_noop: bool = True
    trigger_canvas_or_low_actionables: bool = True


@dataclass(frozen=True)
class CaptchaConfig:
    """
    SDK-level CAPTCHA configuration, mapped onto `AgentRuntime.set_captcha_options()`.
    """

    policy: Literal["abort", "callback"] = "abort"
    # Interface-only: the SDK does not ship a captcha solver. Users provide a handler/callback.
    handler: CaptchaHandler | None = None
    timeout_ms: int | None = None
    poll_ms: int | None = None
    min_confidence: float = 0.7


@dataclass(frozen=True)
class PredicateBrowserAgentConfig:
    """
    High-level agent configuration.

    This is intentionally small and focused on:
    - operational knobs (vision/captcha/permissions)
    - token controls (history_last_n)
    - prompt customization hooks (compact_prompt_builder)
    """

    # Permissions
    permission_startup: PermissionPolicy | None = None
    permission_recovery: PermissionRecoveryConfig | None = None

    # Vision fallback
    vision: VisionFallbackConfig = VisionFallbackConfig()

    # CAPTCHA handling
    captcha: CaptchaConfig = CaptchaConfig()

    # Prompt / token controls
    history_last_n: int = 0  # 0 disables LLM-facing step history (lowest token usage)

    # Compact prompt customization
    # Signature: builder(task_goal, step_goal, dom_context, snapshot, history_summary) -> (system, user)
    compact_prompt_builder: Callable[
        [str, str, str, Snapshot, str], tuple[str, str]
    ] | None = None

    # Optional last-mile truncation of dom_context to control tokens
    compact_prompt_postprocessor: Callable[[str], str] | None = None


def _history_summary(items: list[str]) -> str:
    if not items:
        return ""
    return "\n".join(f"- {s}" for s in items if s)


def apply_captcha_config_to_runtime(
    *,
    runtime: AgentRuntime,
    captcha: CaptchaConfig,
    reset_session: Callable[[], Any] | None = None,
) -> None:
    """
    Map `CaptchaConfig` onto `AgentRuntime.set_captcha_options`.

    This mirrors WebBench semantics:
    - abort: fail fast
    - callback: invoke handler and wait/retry per resolution
    """

    policy = (captcha.policy or "abort").strip().lower()
    if policy not in {"abort", "callback"}:
        raise ValueError("captcha.policy must be 'abort' or 'callback'")

    if policy == "abort":
        runtime.set_captcha_options(
            CaptchaOptions(policy="abort", min_confidence=float(captcha.min_confidence))
        )
        return

    poll_ms = int(captcha.poll_ms or 1_000)
    timeout_ms = int(captcha.timeout_ms or 120_000)

    handler = captcha.handler
    if handler is None:
        raise ValueError(
            'captcha.handler is required when captcha.policy="callback". '
            "Use HumanHandoffSolver(...) for manual solve, or ExternalSolver(...) to integrate your system."
        )

    runtime.set_captcha_options(
        CaptchaOptions(
            policy="callback",
            handler=handler,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
            min_confidence=float(captcha.min_confidence),
            reset_session=reset_session,  # used if handler returns retry_new_session
        )
    )


class _RuntimeAgentWithPromptOverrides(RuntimeAgent):
    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        executor: LLMProvider,
        vision_executor: LLMProvider | None,
        vision_verifier: LLMProvider | None,
        compact_prompt_builder: PredicateBrowserAgentConfig["compact_prompt_builder"],
        compact_prompt_postprocessor: PredicateBrowserAgentConfig["compact_prompt_postprocessor"],
        history_summary_provider: Callable[[], str],
    ) -> None:
        super().__init__(
            runtime=runtime,
            executor=executor,
            vision_executor=vision_executor,
            vision_verifier=vision_verifier,
        )
        self._structured_llm = LLMInteractionHandler(executor)
        self._compact_prompt_builder = compact_prompt_builder
        self._compact_prompt_postprocessor = compact_prompt_postprocessor
        self._history_summary_provider = history_summary_provider

    def _propose_structured_action(
        self, *, task_goal: str, step: RuntimeStep, snap: Snapshot
    ) -> str:
        dom_context = self._structured_llm.build_context(snap, step.goal)
        if self._compact_prompt_postprocessor is not None:
            dom_context = self._compact_prompt_postprocessor(dom_context)

        history_summary = self._history_summary_provider() or ""

        if self._compact_prompt_builder is not None:
            system_prompt, user_prompt = self._compact_prompt_builder(
                task_goal,
                step.goal,
                dom_context,
                snap,
                history_summary,
            )
            resp = self.executor.generate(system_prompt, user_prompt, temperature=0.0)
            return self._structured_llm.extract_action(resp.content)

        # Default: reuse SDK's standard system prompt template by calling query_llm,
        # but include a small history block inside the goal string.
        combined_goal = task_goal
        if history_summary:
            combined_goal = f"{task_goal}\n\nRECENT STEPS:\n{history_summary}"
        combined_goal = f"{combined_goal}\n\nSTEP: {step.goal}"
        resp = self._structured_llm.query_llm(dom_context, combined_goal)
        return self._structured_llm.extract_action(resp.content)


@dataclass
class StepOutcome:
    step_goal: str
    ok: bool
    used_vision: bool = False


class PredicateBrowserAgent:
    """
    Snapshot-first, verification-first browser agent.

    This is a thin user-facing wrapper over `RuntimeAgent` with:
    - a browser-use-like `run()` loop over `step()`
    - bounded prompt-history injection (history_last_n)
    - bounded vision fallback budgeting (max_vision_calls)
    - CAPTCHA configuration mapping to AgentRuntime
    """

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        executor: LLMProvider,
        vision_executor: LLMProvider | None = None,
        vision_verifier: LLMProvider | None = None,
        config: PredicateBrowserAgentConfig = PredicateBrowserAgentConfig(),
    ) -> None:
        self.runtime = runtime
        self.executor = executor
        self.vision_executor = vision_executor
        self.vision_verifier = vision_verifier
        self.config = config

        # LLM-facing step history summaries (bounded)
        self._history: deque[str] = deque(maxlen=max(0, int(config.history_last_n)))

        # Vision budgeting
        self._vision_calls_used = 0

        # Apply CAPTCHA settings immediately (if enabled by config)
        if self.config.captcha is not None:
            apply_captcha_config_to_runtime(runtime=self.runtime, captcha=self.config.captcha)

        self._runner = _RuntimeAgentWithPromptOverrides(
            runtime=self.runtime,
            executor=self.executor,
            vision_executor=self.vision_executor,
            vision_verifier=self.vision_verifier,
            compact_prompt_builder=self.config.compact_prompt_builder,
            compact_prompt_postprocessor=self.config.compact_prompt_postprocessor,
            history_summary_provider=self._get_history_summary,
        )

    def _get_history_summary(self) -> str:
        if int(self.config.history_last_n) <= 0:
            return ""
        return _history_summary(list(self._history))

    def _record_step_history(self, *, step_goal: str, ok: bool) -> None:
        if int(self.config.history_last_n) <= 0:
            return
        self._history.append(f"{step_goal} -> {'ok' if ok else 'fail'}")

    async def step(
        self,
        *,
        task_goal: str,
        step: RuntimeStep,
        on_step_start: Callable[[StepHookContext], Any] | None = None,
        on_step_end: Callable[[StepHookContext], Any] | None = None,
    ) -> StepOutcome:
        # Enforce run-level max vision calls (coarse budget).
        used_vision = False
        if (
            self.config.vision.enabled
            and int(self.config.vision.max_vision_calls) > 0
            and self._vision_calls_used >= int(self.config.vision.max_vision_calls)
        ):
            step = RuntimeStep(
                goal=step.goal,
                intent=step.intent,
                verifications=list(step.verifications),
                snapshot_limit_base=step.snapshot_limit_base,
                snapshot_limit_step=step.snapshot_limit_step,
                snapshot_limit_max=step.snapshot_limit_max,
                max_snapshot_attempts=step.max_snapshot_attempts,
                min_confidence=step.min_confidence,
                min_actionables=step.min_actionables,
                vision_executor_enabled=False,
                max_vision_executor_attempts=0,
            )

        ok = await self._runner.run_step(
            task_goal=task_goal,
            step=step,
            on_step_start=on_step_start,
            on_step_end=on_step_end,
        )

        # Best-effort: detect vision usage by comparing executor call count. If vision executor exists
        # and it was called, we count it. RuntimeAgent doesn't expose a structured outcome today.
        if self.vision_executor is not None and getattr(self.vision_executor, "supports_vision", lambda: False)():
            # If vision path was used, the vision executor provider would have been called.
            # We can't reliably introspect, so we treat it as "possibly used" based on verification fail patterns later.
            # For now, increment budget only when we know vision was enabled and structured attempt failed.
            pass

        # Conservative: increment vision budget if step had vision enabled and structured verification failed once.
        # This is a heuristic until RuntimeAgent exposes a structured outcome.
        if bool(getattr(step, "vision_executor_enabled", False)) and not bool(ok):
            # If vision is enabled and we still failed, we likely spent vision if it was available.
            # (If it wasn't available, this doesn't matter for budgeting because we only *cap* usage.)
            used_vision = bool(self.vision_executor and self.vision_executor.supports_vision())
            if used_vision:
                self._vision_calls_used += 1

        self._record_step_history(step_goal=step.goal, ok=bool(ok))
        return StepOutcome(step_goal=step.goal, ok=bool(ok), used_vision=used_vision)

    async def run(
        self,
        *,
        task_goal: str,
        steps: list[RuntimeStep],
        on_step_start: Callable[[StepHookContext], Any] | None = None,
        on_step_end: Callable[[StepHookContext], Any] | None = None,
        stop_on_failure: bool = True,
    ) -> bool:
        for step in steps:
            out = await self.step(
                task_goal=task_goal,
                step=step,
                on_step_start=on_step_start,
                on_step_end=on_step_end,
            )
            if stop_on_failure and not out.ok:
                return False
        return True

