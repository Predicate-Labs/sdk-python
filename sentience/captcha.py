from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Optional

from .models import CaptchaDiagnostics

CaptchaPolicy = Literal["abort", "callback"]
CaptchaAction = Literal["abort", "retry_new_session", "wait_until_cleared"]
CaptchaSource = Literal["extension", "gateway", "runtime"]


@dataclass
class CaptchaContext:
    run_id: str
    step_index: int
    url: str
    source: CaptchaSource
    captcha: CaptchaDiagnostics
    screenshot_path: str | None = None
    frames_dir: str | None = None
    snapshot_path: str | None = None
    live_session_url: str | None = None
    meta: dict[str, str] | None = None


@dataclass
class CaptchaResolution:
    action: CaptchaAction
    message: str | None = None
    handled_by: Literal["human", "customer_system", "unknown"] | None = None
    timeout_ms: int | None = None
    poll_ms: int | None = None


CaptchaHandler = Callable[[CaptchaContext], CaptchaResolution | Awaitable[CaptchaResolution]]


@dataclass
class CaptchaOptions:
    policy: CaptchaPolicy = "abort"
    min_confidence: float = 0.7
    timeout_ms: int = 120_000
    poll_ms: int = 1_000
    max_retries_new_session: int = 1
    handler: CaptchaHandler | None = None
    reset_session: Callable[[], Awaitable[None]] | None = None


class CaptchaHandlingError(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
