from __future__ import annotations

import inspect
from collections.abc import Callable

from .captcha import CaptchaContext, CaptchaHandler, CaptchaResolution


def HumanHandoffSolver(
    *,
    message: str | None = None,
    handled_by: str | None = "human",
    timeout_ms: int | None = None,
    poll_ms: int | None = None,
) -> CaptchaHandler:
    async def _handler(_ctx: CaptchaContext) -> CaptchaResolution:
        return CaptchaResolution(
            action="wait_until_cleared",
            message=message or "Solve CAPTCHA in the live session, then resume.",
            handled_by=handled_by,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
        )

    return _handler


def VisionSolver(
    *,
    message: str | None = None,
    handled_by: str | None = "customer_system",
    timeout_ms: int | None = None,
    poll_ms: int | None = None,
) -> CaptchaHandler:
    async def _handler(_ctx: CaptchaContext) -> CaptchaResolution:
        return CaptchaResolution(
            action="wait_until_cleared",
            message=message or "Waiting for CAPTCHA to clear (vision verification).",
            handled_by=handled_by,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
        )

    return _handler


def ExternalSolver(
    resolver: Callable[[CaptchaContext], None | bool | dict],
    *,
    message: str | None = None,
    handled_by: str | None = "customer_system",
    timeout_ms: int | None = None,
    poll_ms: int | None = None,
) -> CaptchaHandler:
    async def _handler(ctx: CaptchaContext) -> CaptchaResolution:
        result = resolver(ctx)
        if inspect.isawaitable(result):
            await result
        return CaptchaResolution(
            action="wait_until_cleared",
            message=message or "External solver invoked; waiting for clearance.",
            handled_by=handled_by,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
        )

    return _handler
