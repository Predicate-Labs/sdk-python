"""
Recorder - captures user actions into a trace
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from .browser import SentienceBrowser
from .models import Snapshot, Element
from .snapshot import snapshot
from .query import find


class TraceStep:
    """A single step in a trace"""
    
    def __init__(
        self,
        ts: int,
        type: str,
        selector: Optional[str] = None,
        element_id: Optional[int] = None,
        text: Optional[str] = None,
        key: Optional[str] = None,
        url: Optional[str] = None,
        snapshot: Optional[Snapshot] = None,
    ):
        self.ts = ts
        self.type = type
        self.selector = selector
        self.element_id = element_id
        self.text = text
        self.key = key
        self.url = url
        self.snapshot = snapshot
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "ts": self.ts,
            "type": self.type,
        }
        if self.selector is not None:
            result["selector"] = self.selector
        if self.element_id is not None:
            result["element_id"] = self.element_id
        if self.text is not None:
            result["text"] = self.text
        if self.key is not None:
            result["key"] = self.key
        if self.url is not None:
            result["url"] = self.url
        if self.snapshot is not None:
            result["snapshot"] = self.snapshot.model_dump()
        return result


class Trace:
    """Trace of user actions"""
    
    def __init__(self, start_url: str):
        self.version = "1.0.0"
        self.created_at = datetime.now().isoformat()
        self.start_url = start_url
        self.steps: List[TraceStep] = []
        self._start_time = datetime.now()
    
    def add_step(self, step: TraceStep) -> None:
        """Add a step to the trace"""
        self.steps.append(step)
    
    def add_navigation(self, url: str) -> None:
        """Add navigation step"""
        ts = int((datetime.now() - self._start_time).total_seconds() * 1000)
        step = TraceStep(ts=ts, type="navigation", url=url)
        self.add_step(step)
    
    def add_click(self, element_id: int, selector: Optional[str] = None) -> None:
        """Add click step"""
        ts = int((datetime.now() - self._start_time).total_seconds() * 1000)
        step = TraceStep(ts=ts, type="click", element_id=element_id, selector=selector)
        self.add_step(step)
    
    def add_type(self, element_id: int, text: str, selector: Optional[str] = None, mask: bool = False) -> None:
        """Add type step"""
        ts = int((datetime.now() - self._start_time).total_seconds() * 1000)
        # Mask sensitive data if requested
        masked_text = "***" if mask else text
        step = TraceStep(ts=ts, type="type", element_id=element_id, text=masked_text, selector=selector)
        self.add_step(step)
    
    def add_press(self, key: str) -> None:
        """Add press key step"""
        ts = int((datetime.now() - self._start_time).total_seconds() * 1000)
        step = TraceStep(ts=ts, type="press", key=key)
        self.add_step(step)
    
    def save(self, filepath: str) -> None:
        """Save trace to JSON file"""
        data = {
            "version": self.version,
            "created_at": self.created_at,
            "start_url": self.start_url,
            "steps": [step.to_dict() for step in self.steps],
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'Trace':
        """Load trace from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        trace = cls(data["start_url"])
        trace.version = data["version"]
        trace.created_at = data["created_at"]
        
        for step_data in data["steps"]:
            snapshot_data = step_data.get("snapshot")
            snapshot_obj = None
            if snapshot_data:
                snapshot_obj = Snapshot(**snapshot_data)
            
            step = TraceStep(
                ts=step_data["ts"],
                type=step_data["type"],
                selector=step_data.get("selector"),
                element_id=step_data.get("element_id"),
                text=step_data.get("text"),
                key=step_data.get("key"),
                url=step_data.get("url"),
                snapshot=snapshot_obj,
            )
            trace.steps.append(step)
        
        return trace


class Recorder:
    """Recorder for capturing user actions"""
    
    def __init__(self, browser: SentienceBrowser, capture_snapshots: bool = False):
        self.browser = browser
        self.capture_snapshots = capture_snapshots
        self.trace: Optional[Trace] = None
        self._active = False
        self._mask_patterns: List[str] = []  # Patterns to mask (e.g., "password", "email")
    
    def start(self) -> None:
        """Start recording"""
        if not self.browser.page:
            raise RuntimeError("Browser not started. Call browser.start() first.")
        
        self._active = True
        start_url = self.browser.page.url
        self.trace = Trace(start_url)
        
        # Set up event listeners in the browser
        self._setup_listeners()
    
    def stop(self) -> None:
        """Stop recording"""
        self._active = False
        self._cleanup_listeners()
    
    def add_mask_pattern(self, pattern: str) -> None:
        """Add a pattern to mask in recorded text (e.g., "password", "email")"""
        self._mask_patterns.append(pattern.lower())
    
    def _should_mask(self, text: str) -> bool:
        """Check if text should be masked"""
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in self._mask_patterns)
    
    def _setup_listeners(self) -> None:
        """Set up event listeners to capture actions"""
        # Note: We'll capture actions through the SDK methods rather than DOM events
        # This is cleaner and more reliable
        pass
    
    def _cleanup_listeners(self) -> None:
        """Clean up event listeners"""
        pass
    
    def _infer_selector(self, element_id: int) -> Optional[str]:
        """
        Infer a semantic selector for an element
        
        Uses heuristics to build a robust selector:
        - role=... text~"..."
        - If text empty: use name/aria-label/placeholder
        - Include clickable=true when relevant
        - Validate against snapshot (should match 1 element)
        """
        try:
            # Take a snapshot to get element info
            snap = snapshot(self.browser)
            
            # Find the element in the snapshot
            element = None
            for el in snap.elements:
                if el.id == element_id:
                    element = el
                    break
            
            if not element:
                return None
            
            # Build candidate selector
            parts = []
            
            # Add role
            if element.role and element.role != 'generic':
                parts.append(f"role={element.role}")
            
            # Add text if available
            if element.text:
                # Use contains match for text
                text_part = element.text.replace('"', '\\"')[:50]  # Limit length
                parts.append(f'text~"{text_part}"')
            else:
                # Try to get name/aria-label/placeholder from DOM
                try:
                    el = self.browser.page.evaluate(f"""
                        () => {{
                            const el = window.sentience_registry[{element_id}];
                            if (!el) return null;
                            return {{
                                name: el.name || null,
                                ariaLabel: el.getAttribute('aria-label') || null,
                                placeholder: el.placeholder || null
                            }};
                        }}
                    """)
                    
                    if el:
                        if el.get('name'):
                            parts.append(f'name="{el["name"]}"')
                        elif el.get('ariaLabel'):
                            parts.append(f'text~"{el["ariaLabel"]}"')
                        elif el.get('placeholder'):
                            parts.append(f'text~"{el["placeholder"]}"')
                except Exception:
                    pass
            
            # Add clickable if relevant
            if element.visual_cues.is_clickable:
                parts.append("clickable=true")
            
            if not parts:
                return None
            
            selector = " ".join(parts)
            
            # Validate selector - should match exactly 1 element
            matches = [el for el in snap.elements if self._match_element(el, selector)]
            
            if len(matches) == 1:
                return selector
            elif len(matches) > 1:
                # Add more constraints (importance threshold, near-center)
                # For now, just return the selector with a note
                return selector
            else:
                # Selector doesn't match - return None (will use element_id)
                return None
        
        except Exception:
            return None
    
    def _match_element(self, element: Element, selector: str) -> bool:
        """Simple selector matching (basic implementation)"""
        # This is a simplified version - in production, use the full query engine
        from .query import parse_selector, match_element
        try:
            query_dict = parse_selector(selector)
            return match_element(element, query_dict)
        except Exception:
            return False
    
    def record_navigation(self, url: str) -> None:
        """Record a navigation event"""
        if self._active and self.trace:
            self.trace.add_navigation(url)
    
    def record_click(self, element_id: int, selector: Optional[str] = None) -> None:
        """Record a click event with smart selector inference"""
        if self._active and self.trace:
            # If no selector provided, try to infer one
            if selector is None:
                selector = self._infer_selector(element_id)
            
            # Optionally capture snapshot
            if self.capture_snapshots:
                try:
                    snap = snapshot(self.browser)
                    step = TraceStep(
                        ts=int((datetime.now() - self.trace._start_time).total_seconds() * 1000),
                        type="click",
                        element_id=element_id,
                        selector=selector,
                        snapshot=snap,
                    )
                    self.trace.add_step(step)
                except Exception:
                    # If snapshot fails, just record without it
                    self.trace.add_click(element_id, selector)
            else:
                self.trace.add_click(element_id, selector)
    
    def record_type(self, element_id: int, text: str, selector: Optional[str] = None) -> None:
        """Record a type event with smart selector inference"""
        if self._active and self.trace:
            # If no selector provided, try to infer one
            if selector is None:
                selector = self._infer_selector(element_id)
            
            mask = self._should_mask(text)
            self.trace.add_type(element_id, text, selector, mask=mask)
    
    def record_press(self, key: str) -> None:
        """Record a key press event"""
        if self._active and self.trace:
            self.trace.add_press(key)
    
    def save(self, filepath: str) -> None:
        """Save trace to file"""
        if not self.trace:
            raise RuntimeError("No trace to save. Start recording first.")
        self.trace.save(filepath)
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()


def record(browser: SentienceBrowser, capture_snapshots: bool = False) -> Recorder:
    """
    Create a recorder instance
    
    Args:
        browser: SentienceBrowser instance
        capture_snapshots: Whether to capture snapshots at each step
    
    Returns:
        Recorder instance
    """
    return Recorder(browser, capture_snapshots=capture_snapshots)

