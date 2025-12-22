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
        "importance>500"
        "text^='Sign'"
        "text$='in'"
    """
    query: Dict[str, Any] = {}
    
    # Match patterns like: key=value, key~'value', key!="value", key>123, key^='prefix', key$='suffix'
    # Updated regex to support: =, !=, ~, ^=, $=, >, >=, <, <=
    # Supports dot notation: attr.id, css.color
    # Note: Handle ^= and $= first (before single char operators) to avoid regex conflicts
    # Pattern matches: key, operator (including ^= and $=), and value (quoted or unquoted)
    pattern = r'([\w.]+)(\^=|\$=|>=|<=|!=|[=~<>])((?:\'[^\']+\'|\"[^\"]+\"|[^\s]+))'
    matches = re.findall(pattern, selector)
    
    for key, op, value in matches:
        # Remove quotes from value
        value = value.strip().strip('"\'')
        
        # Handle numeric comparisons
        is_numeric = False
        try:
            numeric_value = float(value)
            is_numeric = True
        except ValueError:
            pass
        
        if op == '!=':
            if key == "role":
                query["role_exclude"] = value
            elif key == "clickable":
                query["clickable"] = False
            elif key == "visible":
                query["visible"] = False
        elif op == '~':
            # Substring match (case-insensitive)
            if key == "text" or key == "name":
                query["text_contains"] = value
        elif op == '^=':
            # Prefix match
            if key == "text" or key == "name":
                query["text_prefix"] = value
        elif op == '$=':
            # Suffix match
            if key == "text" or key == "name":
                query["text_suffix"] = value
        elif op == '>':
            # Greater than
            if is_numeric:
                if key == "importance":
                    query["importance_min"] = numeric_value + 0.0001  # Exclusive
                elif key.startswith("bbox."):
                    query[f"{key}_min"] = numeric_value + 0.0001
                elif key == "z_index":
                    query["z_index_min"] = numeric_value + 0.0001
            elif key.startswith("attr.") or key.startswith("css."):
                query[f"{key}_gt"] = value
        elif op == '>=':
            # Greater than or equal
            if is_numeric:
                if key == "importance":
                    query["importance_min"] = numeric_value
                elif key.startswith("bbox."):
                    query[f"{key}_min"] = numeric_value
                elif key == "z_index":
                    query["z_index_min"] = numeric_value
            elif key.startswith("attr.") or key.startswith("css."):
                query[f"{key}_gte"] = value
        elif op == '<':
            # Less than
            if is_numeric:
                if key == "importance":
                    query["importance_max"] = numeric_value - 0.0001  # Exclusive
                elif key.startswith("bbox."):
                    query[f"{key}_max"] = numeric_value - 0.0001
                elif key == "z_index":
                    query["z_index_max"] = numeric_value - 0.0001
            elif key.startswith("attr.") or key.startswith("css."):
                query[f"{key}_lt"] = value
        elif op == '<=':
            # Less than or equal
            if is_numeric:
                if key == "importance":
                    query["importance_max"] = numeric_value
                elif key.startswith("bbox."):
                    query[f"{key}_max"] = numeric_value
                elif key == "z_index":
                    query["z_index_max"] = numeric_value
            elif key.startswith("attr.") or key.startswith("css."):
                query[f"{key}_lte"] = value
        elif op == '=':
            # Exact match
            if key == "role":
                query["role"] = value
            elif key == "clickable":
                query["clickable"] = value.lower() == "true"
            elif key == "visible":
                query["visible"] = value.lower() == "true"
            elif key == "tag":
                query["tag"] = value
            elif key == "name" or key == "text":
                query["text"] = value
            elif key == "importance" and is_numeric:
                query["importance"] = numeric_value
            elif key.startswith("attr."):
                # Dot notation for attributes: attr.id="submit-btn"
                attr_key = key[5:]  # Remove "attr." prefix
                if "attr" not in query:
                    query["attr"] = {}
                query["attr"][attr_key] = value
            elif key.startswith("css."):
                # Dot notation for CSS: css.color="red"
                css_key = key[4:]  # Remove "css." prefix
                if "css" not in query:
                    query["css"] = {}
                query["css"][css_key] = value
    
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
    
    # Visible (using in_viewport and !is_occluded)
    if "visible" in query:
        is_visible = element.in_viewport and not element.is_occluded
        if is_visible != query["visible"]:
            return False
    
    # Tag (not yet in Element model, but prepare for future)
    if "tag" in query:
        # For now, this will always fail since tag is not in Element model
        # This is a placeholder for future implementation
        pass
    
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
    
    # Text prefix match
    if "text_prefix" in query:
        if not element.text:
            return False
        if not element.text.lower().startswith(query["text_prefix"].lower()):
            return False
    
    # Text suffix match
    if "text_suffix" in query:
        if not element.text:
            return False
        if not element.text.lower().endswith(query["text_suffix"].lower()):
            return False
    
    # Importance filtering
    if "importance" in query:
        if element.importance != query["importance"]:
            return False
    if "importance_min" in query:
        if element.importance < query["importance_min"]:
            return False
    if "importance_max" in query:
        if element.importance > query["importance_max"]:
            return False
    
    # BBox filtering (spatial)
    if "bbox.x_min" in query:
        if element.bbox.x < query["bbox.x_min"]:
            return False
    if "bbox.x_max" in query:
        if element.bbox.x > query["bbox.x_max"]:
            return False
    if "bbox.y_min" in query:
        if element.bbox.y < query["bbox.y_min"]:
            return False
    if "bbox.y_max" in query:
        if element.bbox.y > query["bbox.y_max"]:
            return False
    if "bbox.width_min" in query:
        if element.bbox.width < query["bbox.width_min"]:
            return False
    if "bbox.width_max" in query:
        if element.bbox.width > query["bbox.width_max"]:
            return False
    if "bbox.height_min" in query:
        if element.bbox.height < query["bbox.height_min"]:
            return False
    if "bbox.height_max" in query:
        if element.bbox.height > query["bbox.height_max"]:
            return False
    
    # Z-index filtering
    if "z_index_min" in query:
        if element.z_index < query["z_index_min"]:
            return False
    if "z_index_max" in query:
        if element.z_index > query["z_index_max"]:
            return False
    
    # In viewport filtering
    if "in_viewport" in query:
        if element.in_viewport != query["in_viewport"]:
            return False
    
    # Occlusion filtering
    if "is_occluded" in query:
        if element.is_occluded != query["is_occluded"]:
            return False
    
    # Attribute filtering (dot notation: attr.id="submit-btn")
    if "attr" in query:
        # This requires DOM access, which is not available in the Element model
        # This is a placeholder for future implementation when we add DOM access
        pass
    
    # CSS property filtering (dot notation: css.color="red")
    if "css" in query:
        # This requires DOM access, which is not available in the Element model
        # This is a placeholder for future implementation when we add DOM access
        pass
    
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

