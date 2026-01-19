from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

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
    screenshot_path: Optional[str] = None
    frames_dir: Optional[str] = None
    snapshot_path: Optional[str] = None
    live_session_url: Optional[str] = None
    meta: Optional[dict[str, str]] = None


@dataclass
class CaptchaResolution:
    action: CaptchaAction
    message: Optional[str] = None
    handled_by: Optional[Literal["human", "customer_system", "unknown"]] = None
    timeout_ms: Optional[int] = None
    poll_ms: Optional[int] = None


CaptchaHandler = Callable[[CaptchaContext], CaptchaResolution | Awaitable[CaptchaResolution]]


@dataclass
class CaptchaOptions:
    policy: CaptchaPolicy = "abort"
    min_confidence: float = 0.7
    timeout_ms: int = 120_000
    poll_ms: int = 1_000
    max_retries_new_session: int = 1
    handler: Optional[CaptchaHandler] = None
    reset_session: Optional[Callable[[], Awaitable[None]]] = None


class CaptchaHandlingError(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
