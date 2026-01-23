from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

VisionActionKind = Literal["click_xy", "click_rect", "press", "type", "finish"]


@dataclass(frozen=True)
class VisionExecutorAction:
    kind: VisionActionKind
    args: dict[str, Any]


def parse_vision_executor_action(text: str) -> VisionExecutorAction:
    """
    Parse a vision-executor action string into a structured action.

    Supported formats:
    - CLICK_XY(x, y)
    - CLICK_RECT(x, y, w, h)
    - PRESS("key")
    - TYPE("text")
    - FINISH()
    """
    t = re.sub(r"```[\w]*\n?", "", (text or "")).strip()
    if re.match(r"FINISH\s*\(\s*\)\s*$", t, re.IGNORECASE):
        return VisionExecutorAction("finish", {})
    if m := re.match(r'PRESS\s*\(\s*["\']([^"\']+)["\']\s*\)\s*$', t, re.IGNORECASE):
        return VisionExecutorAction("press", {"key": m.group(1)})
    if m := re.match(r'TYPE\s*\(\s*["\']([\s\S]*?)["\']\s*\)\s*$', t, re.IGNORECASE):
        return VisionExecutorAction("type", {"text": m.group(1)})
    if m := re.match(
        r"CLICK_XY\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)\s*$",
        t,
        re.IGNORECASE,
    ):
        return VisionExecutorAction("click_xy", {"x": float(m.group(1)), "y": float(m.group(2))})
    if m := re.match(
        r"CLICK_RECT\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)\s*$",
        t,
        re.IGNORECASE,
    ):
        return VisionExecutorAction(
            "click_rect",
            {
                "x": float(m.group(1)),
                "y": float(m.group(2)),
                "w": float(m.group(3)),
                "h": float(m.group(4)),
            },
        )
    raise ValueError(f"unrecognized vision action: {t[:200]}")


async def execute_vision_executor_action(
    *,
    backend: Any,
    page: Any | None,
    action: VisionExecutorAction,
) -> None:
    """
    Execute a parsed vision action using a BrowserBackend (and optional Playwright Page).
    """
    if action.kind == "click_xy":
        await backend.mouse_click(float(action.args["x"]), float(action.args["y"]))
        return
    if action.kind == "click_rect":
        cx = float(action.args["x"]) + float(action.args["w"]) / 2.0
        cy = float(action.args["y"]) + float(action.args["h"]) / 2.0
        await backend.mouse_click(cx, cy)
        return
    if action.kind == "press":
        if page is None:
            raise RuntimeError("PRESS requires a Playwright Page")
        await page.keyboard.press(str(action.args["key"]))
        return
    if action.kind == "type":
        await backend.type_text(str(action.args["text"]))
        return
    if action.kind == "finish":
        return
    raise ValueError(f"unknown vision action kind: {action.kind}")
