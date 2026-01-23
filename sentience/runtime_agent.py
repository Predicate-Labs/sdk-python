"""
AgentRuntime-backed agent with optional vision executor fallback.

This module intentionally keeps the control plane verification-first:
- Actions may be proposed by either a structured executor (DOM snapshot prompt)
  or a vision executor (screenshot prompt).
- Verification is always executed via AgentRuntime predicates.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .agent_runtime import AgentRuntime
from .backends import actions as backend_actions
from .llm_interaction_handler import LLMInteractionHandler
from .llm_provider import LLMProvider
from .models import BBox, Snapshot
from .verification import AssertContext, AssertOutcome, Predicate


@dataclass(frozen=True)
class StepVerification:
    predicate: Predicate
    label: str
    required: bool = True
    eventually: bool = True
    timeout_s: float = 10.0
    poll_s: float = 0.25
    max_snapshot_attempts: int = 3
    min_confidence: float | None = None


@dataclass(frozen=True)
class RuntimeStep:
    goal: str
    intent: str | None = None
    verifications: list[StepVerification] = field(default_factory=list)

    # Snapshot quality policy (handled at agent layer; SDK core unchanged).
    snapshot_limit_base: int = 60
    snapshot_limit_step: int = 40
    snapshot_limit_max: int = 220
    max_snapshot_attempts: int = 3
    min_confidence: float | None = None
    min_actionables: int | None = None

    # Vision executor fallback (bounded).
    vision_executor_enabled: bool = True
    max_vision_executor_attempts: int = 1


class RuntimeAgent:
    """
    A thin orchestration layer over AgentRuntime:
    - snapshot (with limit ramp)
    - propose action (structured executor; optionally vision executor fallback)
    - execute action (backend-agnostic primitives)
    - verify (AgentRuntime predicates)
    """

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        executor: LLMProvider,
        vision_executor: LLMProvider | None = None,
        vision_verifier: LLMProvider | None = None,
        short_circuit_canvas: bool = True,
    ) -> None:
        self.runtime = runtime
        self.executor = executor
        self.vision_executor = vision_executor
        self.vision_verifier = vision_verifier
        self.short_circuit_canvas = short_circuit_canvas

        self._structured_llm = LLMInteractionHandler(executor)

    async def run_step(
        self,
        *,
        task_goal: str,
        step: RuntimeStep,
    ) -> bool:
        self.runtime.begin_step(step.goal)
        emitted = False
        ok = False
        try:
            snap = await self._snapshot_with_ramp(step=step)

            if await self._should_short_circuit_to_vision(step=step, snap=snap):
                ok = await self._vision_executor_attempt(
                    task_goal=task_goal, step=step, snap=snap
                )
                return ok

            # 1) Structured executor attempt.
            action = self._propose_structured_action(
                task_goal=task_goal, step=step, snap=snap
            )
            await self._execute_action(action=action, snap=snap)
            ok = await self._apply_verifications(step=step)
            if ok:
                return True

            # 2) Optional vision executor fallback (bounded).
            if step.vision_executor_enabled and step.max_vision_executor_attempts > 0:
                ok = await self._vision_executor_attempt(
                    task_goal=task_goal, step=step, snap=snap
                )
                return ok

            return False
        except Exception as exc:
            try:
                await self.runtime.emit_step_end(
                    success=False,
                    error=str(exc),
                    outcome="exception",
                    verify_passed=False,
                )
                emitted = True
            except Exception:
                pass
            raise
        finally:
            if not emitted:
                try:
                    await self.runtime.emit_step_end(
                        success=ok,
                        outcome=("ok" if ok else "verification_failed"),
                        verify_passed=ok,
                    )
                except Exception:
                    pass

    async def _snapshot_with_ramp(self, *, step: RuntimeStep) -> Snapshot:
        limit = step.snapshot_limit_base
        last: Snapshot | None = None

        for _attempt in range(max(1, step.max_snapshot_attempts)):
            last = await self.runtime.snapshot(limit=limit, goal=step.goal)
            if last is None:
                limit = min(step.snapshot_limit_max, limit + step.snapshot_limit_step)
                continue

            if step.min_confidence is not None:
                conf = getattr(getattr(last, "diagnostics", None), "confidence", None)
                if isinstance(conf, (int, float)) and conf < step.min_confidence:
                    limit = min(step.snapshot_limit_max, limit + step.snapshot_limit_step)
                    continue

            if step.min_actionables is not None:
                if self._count_actionables(last) < step.min_actionables:
                    limit = min(step.snapshot_limit_max, limit + step.snapshot_limit_step)
                    continue

            return last

        # If we didn't return early, use last snapshot (may be low quality).
        if last is None:
            raise RuntimeError("snapshot() returned None repeatedly")
        return last

    def _propose_structured_action(
        self, *, task_goal: str, step: RuntimeStep, snap: Snapshot
    ) -> str:
        dom_context = self._structured_llm.build_context(snap, step.goal)
        combined_goal = f"{task_goal}\n\nSTEP: {step.goal}"
        resp = self._structured_llm.query_llm(dom_context, combined_goal)
        return self._structured_llm.extract_action(resp.content)

    async def _vision_executor_attempt(
        self,
        *,
        task_goal: str,
        step: RuntimeStep,
        snap: Snapshot | None,
    ) -> bool:
        if not self.vision_executor or not self.vision_executor.supports_vision():
            return False

        url = await self._get_url_for_prompt()
        image_b64 = await self._screenshot_base64_png()
        system_prompt, user_prompt = self._vision_executor_prompts(
            task_goal=task_goal,
            step=step,
            url=url,
            snap=snap,
        )

        resp = self.vision_executor.generate_with_image(
            system_prompt,
            user_prompt,
            image_b64,
            temperature=0.0,
        )

        action = self._extract_action_from_text(resp.content)
        await self._execute_action(action=action, snap=snap)
        # Important: vision executor fallback is a *retry* of the same step.
        # Clear prior step assertions so required_assertions_passed reflects the final attempt.
        self.runtime.flush_assertions()
        return await self._apply_verifications(step=step)

    async def _apply_verifications(self, *, step: RuntimeStep) -> bool:
        if not step.verifications:
            # No explicit verifications provided: treat as pass.
            return True

        all_ok = True
        for v in step.verifications:
            if v.eventually:
                ok = await self.runtime.check(
                    v.predicate, label=v.label, required=v.required
                ).eventually(
                    timeout_s=v.timeout_s,
                    poll_s=v.poll_s,
                    max_snapshot_attempts=v.max_snapshot_attempts,
                    min_confidence=v.min_confidence,
                    vision_provider=self.vision_verifier,
                )
            else:
                ok = self.runtime.assert_(v.predicate, label=v.label, required=v.required)
            all_ok = all_ok and ok

        # Respect required verifications semantics.
        return self.runtime.required_assertions_passed() and all_ok

    async def _execute_action(self, *, action: str, snap: Snapshot | None) -> None:
        url = None
        try:
            url = await self.runtime.get_url()
        except Exception:
            url = getattr(snap, "url", None)

        await self.runtime.record_action(action, url=url)

        # Coordinate-backed execution (by snapshot id or explicit coordinates).
        kind, payload = self._parse_action(action)

        if kind == "finish":
            return

        if kind == "press":
            await self._press_key_best_effort(payload["key"])
            await self._stabilize_best_effort()
            return

        if kind == "click_xy":
            await backend_actions.click(self.runtime.backend, (payload["x"], payload["y"]))
            await self._stabilize_best_effort()
            return

        if kind == "click_rect":
            bbox = BBox(x=payload["x"], y=payload["y"], width=payload["w"], height=payload["h"])
            await backend_actions.click(self.runtime.backend, bbox)
            await self._stabilize_best_effort()
            return

        if snap is None:
            raise RuntimeError("Cannot execute CLICK(id)/TYPE(id, ...) without a snapshot")

        if kind == "click":
            el = self._find_element(snap, payload["id"])
            if el is None:
                raise RuntimeError(f"Element id {payload['id']} not found in snapshot")
            await backend_actions.click(self.runtime.backend, el.bbox)
            await self._stabilize_best_effort()
            return

        if kind == "type":
            el = self._find_element(snap, payload["id"])
            if el is None:
                raise RuntimeError(f"Element id {payload['id']} not found in snapshot")
            await backend_actions.type_text(self.runtime.backend, payload["text"], target=el.bbox)
            await self._stabilize_best_effort()
            return

        raise ValueError(f"Unknown action kind: {kind}")

    async def _stabilize_best_effort(self) -> None:
        try:
            await self.runtime.backend.wait_ready_state(state="interactive", timeout_ms=15000)
        except Exception:
            return

    async def _press_key_best_effort(self, key: str) -> None:
        # BrowserBackend does not expose a dedicated keypress primitive; do best-effort JS events.
        key_esc = key.replace("\\", "\\\\").replace("'", "\\'")
        await self.runtime.backend.eval(
            f"""
            (() => {{
              const el = document.activeElement || document.body;
              const down = new KeyboardEvent('keydown', {{key: '{key_esc}', bubbles: true}});
              const up = new KeyboardEvent('keyup', {{key: '{key_esc}', bubbles: true}});
              el.dispatchEvent(down);
              el.dispatchEvent(up);
              return true;
            }})()
            """
        )

    async def _screenshot_base64_png(self) -> str:
        png = await self.runtime.backend.screenshot_png()
        return base64.b64encode(png).decode("utf-8")

    async def _get_url_for_prompt(self) -> str | None:
        try:
            return await self.runtime.get_url()
        except Exception:
            return getattr(self.runtime.last_snapshot, "url", None)

    async def _should_short_circuit_to_vision(
        self, *, step: RuntimeStep, snap: Snapshot | None
    ) -> bool:
        if not (
            step.vision_executor_enabled
            and self.vision_executor
            and self.vision_executor.supports_vision()
        ):
            return False

        if snap is None:
            return True

        if (
            step.min_actionables is not None
            and self._count_actionables(snap) < step.min_actionables
        ):
            if self.short_circuit_canvas:
                try:
                    n_canvas = await self.runtime.backend.eval(
                        "document.querySelectorAll('canvas').length"
                    )
                    if isinstance(n_canvas, (int, float)) and n_canvas > 0:
                        return True
                except Exception:
                    pass

        return False

    def _vision_executor_prompts(
        self,
        *,
        task_goal: str,
        step: RuntimeStep,
        url: str | None,
        snap: Snapshot | None,
    ) -> tuple[str, str]:
        # Include URL as text: screenshots generally don't include browser chrome reliably.
        verify_targets = self._verification_targets_human(step.verifications)

        snapshot_summary = ""
        if snap is not None:
            snapshot_summary = (
                f"\n\nStructured snapshot summary:\n"
                f"- url: {getattr(snap, 'url', None)}\n"
                f"- elements: {len(getattr(snap, 'elements', []) or [])}\n"
            )

        system_prompt = f"""You are a vision-capable web automation executor.

TASK GOAL:
{task_goal}

STEP GOAL:
{step.goal}

CURRENT URL (text):
{url or "(unknown)"}

VERIFICATION TARGETS (text):
{verify_targets or "(none provided)"}
{snapshot_summary}

RESPONSE FORMAT:
Return ONLY ONE of:
- CLICK(id)
- TYPE(id, "text")
- CLICK_XY(x, y)
- CLICK_RECT(x, y, w, h)
- PRESS("key")
- FINISH()

No explanations, no markdown.
"""

        user_prompt = "From the screenshot, return the single best next action:"
        return system_prompt, user_prompt

    def _verification_targets_human(self, verifications: list[StepVerification]) -> str:
        if not verifications:
            return ""
        lines: list[str] = []
        for v in verifications:
            req = "required" if v.required else "optional"
            lines.append(f"- {v.label} ({req})")
        return "\n".join(lines)

    def _count_actionables(self, snap: Snapshot) -> int:
        n = 0
        for el in snap.elements or []:
            cues = getattr(el, "visual_cues", None)
            clickable = bool(getattr(cues, "is_clickable", False))
            if clickable:
                n += 1
        return n

    def _find_element(self, snap: Snapshot, element_id: int) -> Any | None:
        for el in snap.elements or []:
            if getattr(el, "id", None) == element_id:
                return el
        return None

    def _parse_action(
        self,
        action: str,
    ) -> tuple[
        Literal["click", "type", "press", "finish", "click_xy", "click_rect"], dict[str, Any]
    ]:
        action = action.strip()

        if re.match(r"FINISH\s*\(\s*\)\s*$", action, re.IGNORECASE):
            return "finish", {}

        if m := re.match(
            r"CLICK_XY\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)\s*$",
            action,
            re.IGNORECASE,
        ):
            return "click_xy", {"x": float(m.group(1)), "y": float(m.group(2))}

        if m := re.match(
            r"CLICK_RECT\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)\s*$",
            action,
            re.IGNORECASE,
        ):
            return "click_rect", {
                "x": float(m.group(1)),
                "y": float(m.group(2)),
                "w": float(m.group(3)),
                "h": float(m.group(4)),
            }

        if m := re.match(r"CLICK\s*\(\s*(\d+)\s*\)\s*$", action, re.IGNORECASE):
            return "click", {"id": int(m.group(1))}

        if m := re.match(
            r'TYPE\s*\(\s*(\d+)\s*,\s*["\']([^"\']*)["\']\s*\)\s*$',
            action,
            re.IGNORECASE,
        ):
            return "type", {"id": int(m.group(1)), "text": m.group(2)}

        if m := re.match(r'PRESS\s*\(\s*["\']([^"\']+)["\']\s*\)\s*$', action, re.IGNORECASE):
            return "press", {"key": m.group(1)}

        raise ValueError(f"Unknown action format: {action}")

    def _extract_action_from_text(self, text: str) -> str:
        # Keep consistent with LLMInteractionHandler.extract_action, but without DOM context dependency.
        text = re.sub(r"```[\w]*\n?", "", text).strip()
        pat = r'(CLICK_XY\s*\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)|CLICK_RECT\s*\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)|CLICK\s*\(\s*\d+\s*\)|TYPE\s*\(\s*\d+\s*,\s*["\'].*?["\']\s*\)|PRESS\s*\(\s*["\'].*?["\']\s*\)|FINISH\s*\(\s*\))'
        m = re.search(pat, text, re.IGNORECASE)
        return m.group(1) if m else text
