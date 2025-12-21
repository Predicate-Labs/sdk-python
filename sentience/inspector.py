"""
Inspector tool - helps developers see what the agent "sees"
"""

from typing import Optional
from .browser import SentienceBrowser
from .snapshot import snapshot
from .query import find


class Inspector:
    """Inspector for debugging - shows element info on hover/click"""
    
    def __init__(self, browser: SentienceBrowser):
        self.browser = browser
        self._active = False
        self._last_element_id: Optional[int] = None
    
    def start(self) -> None:
        """Start inspection mode - prints element info on mouse move/click"""
        if not self.browser.page:
            raise RuntimeError("Browser not started. Call browser.start() first.")
        
        self._active = True
        
        # Inject inspector script into page
        self.browser.page.evaluate("""
            (() => {
                // Remove existing inspector if any
                if (window.__sentience_inspector_active) {
                    return;
                }
                
                window.__sentience_inspector_active = true;
                window.__sentience_last_element_id = null;
                
                // Get element at point
                function getElementAtPoint(x, y) {
                    const el = document.elementFromPoint(x, y);
                    if (!el) return null;
                    
                    // Find element in registry
                    if (window.sentience_registry) {
                        for (let i = 0; i < window.sentience_registry.length; i++) {
                            if (window.sentience_registry[i] === el) {
                                return i;
                            }
                        }
                    }
                    return null;
                }
                
                // Mouse move handler
                function handleMouseMove(e) {
                    if (!window.__sentience_inspector_active) return;
                    
                    const elementId = getElementAtPoint(e.clientX, e.clientY);
                    if (elementId === null || elementId === window.__sentience_last_element_id) {
                        return;
                    }
                    
                    window.__sentience_last_element_id = elementId;
                    
                    // Get element info from snapshot if available
                    if (window.sentience && window.sentience_registry) {
                        const el = window.sentience_registry[elementId];
                        if (el) {
                            const rect = el.getBoundingClientRect();
                            const text = el.getAttribute('aria-label') || 
                                        el.value || 
                                        el.placeholder || 
                                        el.alt || 
                                        (el.innerText || '').substring(0, 50);
                            
                            const role = el.getAttribute('role') || el.tagName.toLowerCase();
                            
                            console.log(`[Sentience Inspector] Element #${elementId}: role=${role}, text="${text}", bbox=(${Math.round(rect.x)}, ${Math.round(rect.y)}, ${Math.round(rect.width)}, ${Math.round(rect.height)})`);
                        }
                    }
                }
                
                // Click handler
                function handleClick(e) {
                    if (!window.__sentience_inspector_active) return;
                    
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const elementId = getElementAtPoint(e.clientX, e.clientY);
                    if (elementId === null) return;
                    
                    // Get full element info
                    if (window.sentience && window.sentience_registry) {
                        const el = window.sentience_registry[elementId];
                        if (el) {
                            const rect = el.getBoundingClientRect();
                            const info = {
                                id: elementId,
                                tag: el.tagName.toLowerCase(),
                                role: el.getAttribute('role') || 'generic',
                                text: el.getAttribute('aria-label') || 
                                      el.value || 
                                      el.placeholder || 
                                      el.alt || 
                                      (el.innerText || '').substring(0, 100),
                                bbox: {
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height)
                                },
                                attributes: {
                                    id: el.id || null,
                                    class: el.className || null,
                                    name: el.name || null,
                                    type: el.type || null
                                }
                            };
                            
                            console.log('[Sentience Inspector] Clicked element:', JSON.stringify(info, null, 2));
                            
                            // Also try to get from snapshot if available
                            window.sentience.snapshot({ limit: 100 }).then(snap => {
                                const element = snap.elements.find(el => el.id === elementId);
                                if (element) {
                                    console.log('[Sentience Inspector] Snapshot element:', JSON.stringify(element, null, 2));
                                }
                            }).catch(() => {});
                        }
                    }
                }
                
                // Add event listeners
                document.addEventListener('mousemove', handleMouseMove, true);
                document.addEventListener('click', handleClick, true);
                
                // Store cleanup function
                window.__sentience_inspector_cleanup = () => {
                    document.removeEventListener('mousemove', handleMouseMove, true);
                    document.removeEventListener('click', handleClick, true);
                    window.__sentience_inspector_active = false;
                };
                
                console.log('[Sentience Inspector] ✅ Inspection mode active. Hover elements to see info, click to see full details.');
            })();
        """)
    
    def stop(self) -> None:
        """Stop inspection mode"""
        if not self.browser.page:
            return
        
        self._active = False
        
        # Cleanup inspector
        self.browser.page.evaluate("""
            () => {
                if (window.__sentience_inspector_cleanup) {
                    window.__sentience_inspector_cleanup();
                }
            }
        """)
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()


def inspect(browser: SentienceBrowser) -> Inspector:
    """
    Create an inspector instance
    
    Args:
        browser: SentienceBrowser instance
    
    Returns:
        Inspector instance
    """
    return Inspector(browser)

