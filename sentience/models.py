"""
Pydantic models for Sentience SDK - matches spec/snapshot.schema.json
"""

from dataclasses import dataclass
from typing import Any, Literal, Optional

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

    # ML reranking metadata (optional - can be absent or null)
    rerank_index: int | None = None  # 0-based, The rank after ML reranking
    heuristic_index: int | None = None  # 0-based, Where it would have been without ML
    ml_probability: float | None = None  # Confidence score from ONNX model (0.0 - 1.0)
    ml_score: float | None = None  # Raw logit score (optional, for debugging)

    # Diff status for frontend Diff Overlay feature
    diff_status: Literal["ADDED", "REMOVED", "MODIFIED", "MOVED"] | None = None

    # Phase 1: Ordinal support fields for position-based selection
    center_x: float | None = None  # X coordinate of element center (viewport coords)
    center_y: float | None = None  # Y coordinate of element center (viewport coords)
    doc_y: float | None = None  # Y coordinate in document (center_y + scroll_y)
    group_key: str | None = None  # Geometric bucket key for ordinal grouping
    group_index: int | None = None  # Position within group (0-indexed, sorted by doc_y)


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
    # Phase 2: Dominant group key for ordinal selection
    dominant_group_key: str | None = None  # The most common group_key (main content group)

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

    For browser-use integration (where you don't have a SentienceBrowser),
    you can pass sentience_api_key directly in options:

        from sentience.models import SnapshotOptions
        options = SnapshotOptions(
            sentience_api_key="sk_pro_xxxxx",
            use_api=True,
            goal="Find the login button"
        )
    """

    screenshot: bool | ScreenshotConfig = False  # Union type: boolean or config
    limit: int = Field(50, ge=1, le=500)
    filter: SnapshotFilter | None = None
    use_api: bool | None = None  # Force API vs extension
    save_trace: bool = False  # Save raw_elements to JSON for benchmarking/training
    trace_path: str | None = None  # Path to save trace (default: "trace_{timestamp}.json")
    goal: str | None = None  # Optional goal/task description for the snapshot
    show_overlay: bool = False  # Show visual overlay highlighting elements in browser

    # API credentials (for browser-use integration without SentienceBrowser)
    sentience_api_key: str | None = None  # Sentience API key for Pro/Enterprise features

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


class ProxyConfig(BaseModel):
    """
    Proxy configuration for browser networking.

    Supports HTTP, HTTPS, and SOCKS5 proxies with optional authentication.
    """

    server: str = Field(
        ...,
        description="Proxy server URL including scheme and port (e.g., 'http://proxy.example.com:8080')",
    )
    username: str | None = Field(
        None,
        description="Username for proxy authentication (optional)",
    )
    password: str | None = Field(
        None,
        description="Password for proxy authentication (optional)",
    )

    def to_playwright_dict(self) -> dict:
        """
        Convert to Playwright proxy configuration format.

        Returns:
            Dict compatible with Playwright's proxy parameter
        """
        config = {"server": self.server}
        if self.username and self.password:
            config["username"] = self.username
            config["password"] = self.password
        return config


# ========== Storage State Models (Auth Injection) ==========


class Cookie(BaseModel):
    """
    Cookie definition for storage state injection.

    Matches Playwright's cookie format for storage_state.
    """

    name: str = Field(..., description="Cookie name")
    value: str = Field(..., description="Cookie value")
    domain: str = Field(..., description="Cookie domain (e.g., '.example.com')")
    path: str = Field(default="/", description="Cookie path")
    expires: float | None = Field(None, description="Expiration timestamp (Unix epoch)")
    httpOnly: bool = Field(default=False, description="HTTP-only flag")
    secure: bool = Field(default=False, description="Secure (HTTPS-only) flag")
    sameSite: Literal["Strict", "Lax", "None"] = Field(
        default="Lax", description="SameSite attribute"
    )


class LocalStorageItem(BaseModel):
    """
    LocalStorage item for a specific origin.

    Playwright stores localStorage as an array of {name, value} objects.
    """

    name: str = Field(..., description="LocalStorage key")
    value: str = Field(..., description="LocalStorage value")


class OriginStorage(BaseModel):
    """
    Storage state for a specific origin (localStorage).

    Represents localStorage data for a single domain.
    """

    origin: str = Field(..., description="Origin URL (e.g., 'https://example.com')")
    localStorage: list[LocalStorageItem] = Field(
        default_factory=list, description="LocalStorage items for this origin"
    )


class StorageState(BaseModel):
    """
    Complete browser storage state (cookies + localStorage).

    This is the format used by Playwright's storage_state() method.
    Can be saved to/loaded from JSON files for session injection.
    """

    cookies: list[Cookie] = Field(
        default_factory=list, description="Cookies to inject (global scope)"
    )
    origins: list[OriginStorage] = Field(
        default_factory=list, description="LocalStorage data per origin"
    )

    @classmethod
    def from_dict(cls, data: dict) -> "StorageState":
        """
        Create StorageState from dictionary (e.g., loaded from JSON).

        Args:
            data: Dictionary with 'cookies' and/or 'origins' keys

        Returns:
            StorageState instance
        """
        cookies = [
            Cookie(**cookie) if isinstance(cookie, dict) else cookie
            for cookie in data.get("cookies", [])
        ]
        origins = []
        for origin_data in data.get("origins", []):
            if isinstance(origin_data, dict):
                # Handle localStorage as array of {name, value} or as dict
                localStorage_data = origin_data.get("localStorage", [])
                if isinstance(localStorage_data, dict):
                    # Convert dict to list of LocalStorageItem
                    localStorage_items = [
                        LocalStorageItem(name=k, value=v) for k, v in localStorage_data.items()
                    ]
                else:
                    # Already a list
                    localStorage_items = [
                        LocalStorageItem(**item) if isinstance(item, dict) else item
                        for item in localStorage_data
                    ]
                origins.append(
                    OriginStorage(
                        origin=origin_data.get("origin", ""),
                        localStorage=localStorage_items,
                    )
                )
            else:
                origins.append(origin_data)
        return cls(cookies=cookies, origins=origins)

    def to_playwright_dict(self) -> dict:
        """
        Convert to Playwright-compatible dictionary format.

        Returns:
            Dictionary compatible with Playwright's storage_state parameter
        """
        return {
            "cookies": [cookie.model_dump() for cookie in self.cookies],
            "origins": [
                {
                    "origin": origin.origin,
                    "localStorage": [item.model_dump() for item in origin.localStorage],
                }
                for origin in self.origins
            ],
        }


# ========== Text Search Models (findTextRect) ==========


class TextRect(BaseModel):
    """
    Rectangle coordinates for text occurrence.
    Includes both absolute (page) and viewport-relative coordinates.
    """

    x: float = Field(..., description="Absolute X coordinate (page coordinate with scroll offset)")
    y: float = Field(..., description="Absolute Y coordinate (page coordinate with scroll offset)")
    width: float = Field(..., description="Rectangle width in pixels")
    height: float = Field(..., description="Rectangle height in pixels")
    left: float = Field(..., description="Absolute left position (same as x)")
    top: float = Field(..., description="Absolute top position (same as y)")
    right: float = Field(..., description="Absolute right position (x + width)")
    bottom: float = Field(..., description="Absolute bottom position (y + height)")


class ViewportRect(BaseModel):
    """Viewport-relative rectangle coordinates (without scroll offset)"""

    x: float = Field(..., description="Viewport-relative X coordinate")
    y: float = Field(..., description="Viewport-relative Y coordinate")
    width: float = Field(..., description="Rectangle width in pixels")
    height: float = Field(..., description="Rectangle height in pixels")


class TextContext(BaseModel):
    """Context text surrounding a match"""

    before: str = Field(..., description="Text before the match (up to 20 chars)")
    after: str = Field(..., description="Text after the match (up to 20 chars)")


class TextMatch(BaseModel):
    """A single text match with its rectangle and context"""

    text: str = Field(..., description="The matched text")
    rect: TextRect = Field(..., description="Absolute rectangle coordinates (with scroll offset)")
    viewport_rect: ViewportRect = Field(
        ..., description="Viewport-relative rectangle (without scroll offset)"
    )
    context: TextContext = Field(..., description="Surrounding text context")
    in_viewport: bool = Field(..., description="Whether the match is currently visible in viewport")


class TextRectSearchResult(BaseModel):
    """
    Result of findTextRect operation.
    Returns all occurrences of text on the page with their exact pixel coordinates.
    """

    status: Literal["success", "error"]
    query: str | None = Field(None, description="The search text that was queried")
    case_sensitive: bool | None = Field(None, description="Whether search was case-sensitive")
    whole_word: bool | None = Field(None, description="Whether whole-word matching was used")
    matches: int | None = Field(None, description="Number of matches found")
    results: list[TextMatch] | None = Field(
        None, description="List of text matches with coordinates"
    )
    viewport: Viewport | None = Field(None, description="Current viewport dimensions")
    error: str | None = Field(None, description="Error message if status is 'error'")


class ReadResult(BaseModel):
    """Result of read() or read_async() operation"""

    status: Literal["success", "error"]
    url: str
    format: Literal["raw", "text", "markdown"]
    content: str
    length: int
    error: str | None = None


class TraceStats(BaseModel):
    """Execution statistics for trace completion"""

    total_steps: int
    total_events: int
    duration_ms: int | None = None
    final_status: Literal["success", "failure", "partial", "unknown"]
    started_at: str | None = None
    ended_at: str | None = None


class StepExecutionResult(BaseModel):
    """Result of executing a single step in ConversationalAgent"""

    success: bool
    action: str
    data: dict[str, Any]  # Flexible data field for step-specific results
    error: str | None = None


class ExtractionResult(BaseModel):
    """Result of extracting information from a page"""

    found: bool
    data: dict[str, Any]  # Extracted data fields
    summary: str  # Brief description of what was found


@dataclass
class ScreenshotMetadata:
    """
    Metadata for a stored screenshot.

    Used by CloudTraceSink to track screenshots before upload.
    All fields are required for type safety.
    """

    sequence: int
    format: Literal["png", "jpeg"]
    size_bytes: int
    step_id: str | None
    filepath: str
