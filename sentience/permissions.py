from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PermissionDefault = Literal["clear", "deny", "grant"]


@dataclass
class PermissionPolicy:
    """
    Browser permission handling policy applied on context creation.
    """

    default: PermissionDefault = "clear"
    auto_grant: list[str] = field(default_factory=list)
    geolocation: dict | None = None
    origin: str | None = None
