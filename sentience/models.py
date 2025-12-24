"""
Pydantic models for Sentience SDK - matches spec/snapshot.schema.json
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Union
from datetime import datetime


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
    background_color_name: Optional[str] = None
    is_clickable: bool


class Element(BaseModel):
    """Element from snapshot"""
    id: int
    role: str
    text: Optional[str] = None
    importance: int
    bbox: BBox
    visual_cues: VisualCues
    in_viewport: bool = True
    is_occluded: bool = False
    z_index: int = 0


class Snapshot(BaseModel):
    """Snapshot response from extension"""
    status: Literal["success", "error"]
    timestamp: Optional[str] = None
    url: str
    viewport: Optional[Viewport] = None
    elements: List[Element]
    screenshot: Optional[str] = None
    screenshot_format: Optional[Literal["png", "jpeg"]] = None
    error: Optional[str] = None
    requires_license: Optional[bool] = None

    def save(self, filepath: str) -> None:
        """Save snapshot as JSON file"""
        import json
        with open(filepath, 'w') as f:
            json.dump(self.model_dump(), f, indent=2)


class ActionResult(BaseModel):
    """Result of an action (click, type, press)"""
    success: bool
    duration_ms: int
    outcome: Optional[Literal["navigated", "dom_updated", "no_change", "error"]] = None
    url_changed: Optional[bool] = None
    snapshot_after: Optional[Snapshot] = None
    error: Optional[dict] = None


class WaitResult(BaseModel):
    """Result of wait_for operation"""
    found: bool
    element: Optional[Element] = None
    duration_ms: int
    timeout: bool


# ========== Agent Layer Models ==========

class ScreenshotConfig(BaseModel):
    """Screenshot format configuration"""
    format: Literal['png', 'jpeg'] = 'png'
    quality: Optional[int] = Field(None, ge=1, le=100)  # Only for JPEG (1-100)


class SnapshotFilter(BaseModel):
    """Filter options for snapshot elements"""
    min_area: Optional[int] = Field(None, ge=0)
    allowed_roles: Optional[List[str]] = None
    min_z_index: Optional[int] = None


class SnapshotOptions(BaseModel):
    """
    Configuration for snapshot calls.
    Matches TypeScript SnapshotOptions interface from sdk-ts/src/snapshot.ts
    """
    screenshot: Union[bool, ScreenshotConfig] = False  # Union type: boolean or config
    limit: int = Field(50, ge=1, le=500)
    filter: Optional[SnapshotFilter] = None
    use_api: Optional[bool] = None  # Force API vs extension

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
    element_id: Optional[int] = None
    text: Optional[str] = None
    key: Optional[str] = None
    outcome: Optional[Literal["navigated", "dom_updated", "no_change", "error"]] = None
    url_changed: Optional[bool] = None
    error: Optional[str] = None
    message: Optional[str] = None  # For FINISH action

    def __getitem__(self, key):
        """
        Support dict-style access for backward compatibility.
        This allows existing code using result["success"] to continue working.
        """
        import warnings
        warnings.warn(
            f"Dict-style access result['{key}'] is deprecated. Use result.{key} instead.",
            DeprecationWarning,
            stacklevel=2
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
    by_action: List[ActionTokenUsage]


class ActionHistory(BaseModel):
    """Single history entry from agent execution"""
    goal: str
    action: str  # The raw action string from LLM
    result: dict  # Will be AgentActionResult but stored as dict for flexibility
    success: bool
    attempt: int
    duration_ms: int

