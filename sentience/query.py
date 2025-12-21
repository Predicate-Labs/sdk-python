"""
Query engine v1 - semantic selector matching
"""

import re
from typing import List, Optional, Union, Dict, Any
from .models import Snapshot, Element


def parse_selector(selector: str) -> Dict[str, Any]:
    """
    Parse string DSL selector into structured query
    
    Examples:
        "role=button text~'Sign in'"
        "role=textbox name~'email'"
        "clickable=true role=link"
        "role!=link"
    """
    query: Dict[str, Any] = {}
    
    # Match patterns like: key=value, key~'value', key!="value"
    # This regex matches: key, operator (=, ~, !=), and value (quoted or unquoted)
    pattern = r'(\w+)([=~!]+)((?:\'[^\']+\'|\"[^\"]+\"|[^\s]+))'
    matches = re.findall(pattern, selector)
    
    for key, op, value in matches:
        # Remove quotes from value
        value = value.strip().strip('"\'')
        
        if op == '!=':
            if key == "role":
                query["role_exclude"] = value
            elif key == "clickable":
                query["clickable"] = False
        elif op == '~':
            if key == "text" or key == "name":
                query["text_contains"] = value
        elif op == '=':
            if key == "role":
                query["role"] = value
            elif key == "clickable":
                query["clickable"] = value.lower() == "true"
            elif key == "name" or key == "text":
                query["text"] = value
    
    return query


def match_element(element: Element, query: Dict[str, Any]) -> bool:
    """Check if element matches query criteria"""
    
    # Role exact match
    if "role" in query:
        if element.role != query["role"]:
            return False
    
    # Role exclusion
    if "role_exclude" in query:
        if element.role == query["role_exclude"]:
            return False
    
    # Clickable
    if "clickable" in query:
        if element.visual_cues.is_clickable != query["clickable"]:
            return False
    
    # Text exact match
    if "text" in query:
        if not element.text or element.text != query["text"]:
            return False
    
    # Text contains (case-insensitive)
    if "text_contains" in query:
        if not element.text:
            return False
        if query["text_contains"].lower() not in element.text.lower():
            return False
    
    return True


def query(snapshot: Snapshot, selector: Union[str, Dict[str, Any]]) -> List[Element]:
    """
    Query elements from snapshot using semantic selector
    
    Args:
        snapshot: Snapshot object
        selector: String DSL (e.g., "role=button text~'Sign in'") or dict query
    
    Returns:
        List of matching elements, sorted by importance (descending)
    """
    # Parse selector if string
    if isinstance(selector, str):
        query_dict = parse_selector(selector)
    else:
        query_dict = selector
    
    # Filter elements
    matches = [el for el in snapshot.elements if match_element(el, query_dict)]
    
    # Sort by importance (descending)
    matches.sort(key=lambda el: el.importance, reverse=True)
    
    return matches


def find(snapshot: Snapshot, selector: Union[str, Dict[str, Any]]) -> Optional[Element]:
    """
    Find single element matching selector (best match by importance)
    
    Args:
        snapshot: Snapshot object
        selector: String DSL or dict query
    
    Returns:
        Best matching element or None
    """
    results = query(snapshot, selector)
    return results[0] if results else None

