"""
Pydantic models for Sentience SDK - matches spec/snapshot.schema.json
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
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

