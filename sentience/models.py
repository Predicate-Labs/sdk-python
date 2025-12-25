"""
Pydantic models for Sentience SDK - matches spec/snapshot.schema.json
"""

from typing import Literal

from pydantic import BaseModel, Field


class BBox(BaseModel):
    """Bounding box coordinates"""

    x: float
    y: float
    width: float
    height: float


class Viewport(BaseModel):
    """Viewport dimensions"""

    width: float
    height: float


class VisualCues(BaseModel):
    """Visual analysis cues"""

    is_primary: bool
    background_color_name: str | None = None
    is_clickable: bool


class Element(BaseModel):
    """Element from snapshot"""

    id: int
    role: str
    text: str | None = None
    importance: int
    bbox: BBox
    visual_cues: VisualCues
    in_viewport: bool = True
    is_occluded: bool = False
    z_index: int = 0


class Snapshot(BaseModel):
    """Snapshot response from extension"""

    status: Literal["success", "error"]
    timestamp: str | None = None
    url: str
    viewport: Viewport | None = None
    elements: list[Element]
    screenshot: str | None = None
    screenshot_format: Literal["png", "jpeg"] | None = None
    error: str | None = None
    requires_license: bool | None = None

    def save(self, filepath: str) -> None:
        """Save snapshot as JSON file"""
        import json

        with open(filepath, "w") as f:
            json.dump(self.model_dump(), f, indent=2)


class ActionResult(BaseModel):
    """Result of an action (click, type, press)"""

    success: bool
    duration_ms: int
    outcome: Literal["navigated", "dom_updated", "no_change", "error"] | None = None
    url_changed: bool | None = None
    snapshot_after: Snapshot | None = None
    error: dict | None = None


class WaitResult(BaseModel):
    """Result of wait_for operation"""

    found: bool
    element: Element | None = None
    duration_ms: int
    timeout: bool


# ========== Agent Layer Models ==========


class ScreenshotConfig(BaseModel):
    """Screenshot format configuration"""

    format: Literal["png", "jpeg"] = "png"
    quality: int | None = Field(None, ge=1, le=100)  # Only for JPEG (1-100)


class SnapshotFilter(BaseModel):
    """Filter options for snapshot elements"""

    min_area: int | None = Field(None, ge=0)
    allowed_roles: list[str] | None = None
    min_z_index: int | None = None


class SnapshotOptions(BaseModel):
    """
    Configuration for snapshot calls.
    Matches TypeScript SnapshotOptions interface from sdk-ts/src/snapshot.ts
    """

    screenshot: bool | ScreenshotConfig = False  # Union type: boolean or config
    limit: int = Field(50, ge=1, le=500)
    filter: SnapshotFilter | None = None
    use_api: bool | None = None  # Force API vs extension
    save_trace: bool = False  # Save raw_elements to JSON for benchmarking/training
    trace_path: str | None = None  # Path to save trace (default: "trace_{timestamp}.json")

    class Config:
        arbitrary_types_allowed = True


class AgentActionResult(BaseModel):
    """Result of a single agent action (from agent.act())"""

    success: bool
    action: Literal["click", "type", "press", "finish", "error"]
    goal: str
    duration_ms: int
    attempt: int

    # Optional fields based on action type
    element_id: int | None = None
    text: str | None = None
    key: str | None = None
    outcome: Literal["navigated", "dom_updated", "no_change", "error"] | None = None
    url_changed: bool | None = None
    error: str | None = None
    message: str | None = None  # For FINISH action

    def __getitem__(self, key):
        """
        Support dict-style access for backward compatibility.
        This allows existing code using result["success"] to continue working.
        """
        import warnings

        warnings.warn(
            f"Dict-style access result['{key}'] is deprecated. Use result.{key} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(self, key)


class ActionTokenUsage(BaseModel):
    """Token usage for a single action"""

    goal: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


class TokenStats(BaseModel):
    """Token usage statistics for an agent session"""

    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    by_action: list[ActionTokenUsage]


class ActionHistory(BaseModel):
    """Single history entry from agent execution"""

    goal: str
    action: str  # The raw action string from LLM
    result: dict  # Will be AgentActionResult but stored as dict for flexibility
    success: bool
    attempt: int
    duration_ms: int
