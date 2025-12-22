# Sentience Query DSL Guide

The Sentience Query DSL (Domain-Specific Language) allows you to find elements on a webpage using semantic properties instead of brittle CSS selectors. This guide covers all supported operators, fields, and usage patterns.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Basic Syntax](#basic-syntax)
3. [Operators](#operators)
4. [Fields](#fields)
5. [Query Examples](#query-examples)
6. [Free Tier vs Pro/Enterprise](#free-tier-vs-proenterprise)
7. [Best Practices](#best-practices)
8. [API Reference](#api-reference)

---

## Quick Start

```python
from sentience import SentienceBrowser, snapshot, query, find

with SentienceBrowser() as browser:
    browser.page.goto("https://example.com")
    browser.page.wait_for_load_state("networkidle")
    
    snap = snapshot(browser)
    
    # Find all buttons
    buttons = query(snap, "role=button")
    
    # Find button with specific text
    sign_in = find(snap, "role=button text~'Sign in'")
    
    # Find high-importance elements (Pro/Enterprise only)
    important = query(snap, "importance>500")
```

---

## Basic Syntax

A selector is a sequence of **terms** separated by whitespace (implicit AND). Each term is a comparison: `field operator value`.

### Simple Examples

```python
# Single condition
"role=button"

# Multiple conditions (AND)
"role=button text~'Sign in' clickable=true"

# Negation
"role!=link"

# Numeric comparison
"importance>500"
```

### Value Types

- **Strings**: Use quotes for values with spaces: `text~'Sign in'` or `text~"Sign in"`
- **Barewords**: No quotes needed for single words: `role=button`
- **Booleans**: `true` or `false`: `clickable=true`
- **Numbers**: Integers or floats: `importance>500`, `bbox.x>100.5`

---

## Operators

### Comparison Operators

| Operator | Description | Example | Use Case |
|----------|-------------|---------|----------|
| `=` | Exact match | `role=button` | Match exact value |
| `!=` | Not equal | `role!=link` | Exclude specific values |
| `~` | Contains (case-insensitive) | `text~'Sign in'` | Text substring matching |
| `^=` | Starts with | `text^='Sign'` | Prefix matching |
| `$=` | Ends with | `text$='in'` | Suffix matching |
| `>` | Greater than | `importance>500` | Numeric comparisons |
| `>=` | Greater than or equal | `importance>=1000` | Numeric comparisons |
| `<` | Less than | `importance<300` | Numeric comparisons |
| `<=` | Less than or equal | `importance<=200` | Numeric comparisons |

### Operator Examples

```python
# Exact match
query(snap, "role=button")
query(snap, "clickable=true")

# Contains (case-insensitive)
query(snap, "text~'sign in'")  # Matches "Sign In", "SIGN IN", "sign in"

# Prefix matching
query(snap, "text^='Sign'")    # Matches "Sign In", "Sign Out", "Sign Up"

# Suffix matching
query(snap, "text$='In'")      # Matches "Sign In", "Log In"

# Numeric comparisons
query(snap, "importance>500")      # Importance greater than 500
query(snap, "importance>=1000")   # Importance greater than or equal to 1000
query(snap, "importance<300")      # Importance less than 300
query(snap, "importance<=200")     # Importance less than or equal to 200

# Spatial comparisons
query(snap, "bbox.x>100")          # X position greater than 100
query(snap, "bbox.width>=50")      # Width greater than or equal to 50
query(snap, "bbox.y<500")          # Y position less than 500
```

---

## Fields

### Core Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `role` | string | Semantic role (button, link, textbox, etc.) | `role=button` |
| `text` | string | Visible text content | `text~'Sign in'` |
| `name` | string | Accessible name (aria-label, placeholder) | `name~'email'` |
| `clickable` | boolean | Whether element is clickable | `clickable=true` |
| `visible` | boolean | Whether element is visible (in viewport and not occluded) | `visible=true` |
| `importance` | number | Importance score (Pro/Enterprise only) | `importance>500` |
| `tag` | string | HTML tag name (future) | `tag=button` |

### Spatial Fields (BBox)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `bbox.x` | number | X coordinate (left edge) | `bbox.x>100` |
| `bbox.y` | number | Y coordinate (top edge) | `bbox.y<500` |
| `bbox.width` | number | Element width | `bbox.width>50` |
| `bbox.height` | number | Element height | `bbox.height>30` |

### Visibility Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `in_viewport` | boolean | Whether element is in viewport | `in_viewport=true` |
| `is_occluded` | boolean | Whether element is covered by overlay | `is_occluded=false` |
| `z_index` | number | CSS z-index value | `z_index>10` |

### Visual Cues (Nested)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `visual_cues.is_clickable` | boolean | Clickable detection | Use `clickable=true` instead |
| `visual_cues.is_primary` | boolean | Primary action detection (Pro/Enterprise only) | Not directly queryable |
| `visual_cues.background_color_name` | string | Color name (Pro/Enterprise only) | Not directly queryable |

**Note**: Visual cues fields are not directly queryable. Use the top-level `clickable` field instead.

### Future Fields (Placeholder)

| Field | Type | Description | Status |
|-------|------|-------------|--------|
| `attr.*` | string | HTML attributes (dot notation) | Parser ready, matching pending |
| `css.*` | string | CSS properties (dot notation) | Parser ready, matching pending |

---

## Query Examples

### Basic Queries

```python
# Find all buttons
buttons = query(snap, "role=button")

# Find button with specific text
sign_in = find(snap, "role=button text~'Sign in'")

# Find clickable links
clickable_links = query(snap, "role=link clickable=true")

# Find visible elements only
visible = query(snap, "visible=true")

# Exclude generic elements
actionable = query(snap, "role!=generic")
```

### Text Matching

```python
# Contains (case-insensitive)
query(snap, "text~'sign in'")      # Matches "Sign In", "SIGN IN", etc.

# Prefix
query(snap, "text^='Sign'")        # Matches "Sign In", "Sign Out", "Sign Up"

# Suffix
query(snap, "text$='In'")          # Matches "Sign In", "Log In"

# Combined
query(snap, "role=button text^='Submit'")
```

### Numeric Comparisons

```python
# Importance filtering (Pro/Enterprise only)
high_importance = query(snap, "importance>500")
medium_importance = query(snap, "importance>=200 importance<=500")

# Spatial filtering
right_side = query(snap, "bbox.x>500")
large_elements = query(snap, "bbox.width>100 bbox.height>50")

# Z-index filtering
above_overlay = query(snap, "z_index>10")
```

### Combined Queries

```python
# Multiple conditions (AND)
query(snap, "role=button importance>500 clickable=true")

# Spatial region
query(snap, "bbox.x>100 bbox.x<200 bbox.y>50 bbox.y<150")

# Visibility + importance
query(snap, "visible=true importance>300")

# Text + spatial
query(snap, "text~'Submit' bbox.x>400")
```

### Real-World Examples

```python
# Find primary submit button
submit = find(snap, "role=button text~'Submit' clickable=true")

# Find email input field
email = find(snap, "role=textbox name~'email'")

# Find all links in viewport
visible_links = query(snap, "role=link in_viewport=true")

# Find high-importance buttons (Pro/Enterprise)
primary_actions = query(snap, "role=button importance>800 clickable=true")

# Find elements in specific region (top-right)
top_right = query(snap, "bbox.x>800 bbox.y<100")

# Find large clickable elements
large_clickable = query(snap, "clickable=true bbox.width>100 bbox.height>40")
```

---

## Free Tier vs Pro/Enterprise

### Free Tier (WASM Extension)

**Available Fields:**
- ✅ `role`, `text`, `name`, `clickable`, `visible`
- ✅ `bbox.*` (spatial fields)
- ✅ `in_viewport`, `is_occluded`, `z_index`

**Limited Fields:**
- ⚠️ `importance` - Always `0` (not useful for filtering)
- ⚠️ `visual_cues.is_primary` - Always `false`
- ⚠️ `visual_cues.background_color_name` - Always `None`

**Example (Free Tier):**
```python
# ✅ Works - Basic role and text matching
query(snap, "role=button text~'Sign in'")

# ✅ Works - Spatial filtering
query(snap, "bbox.x>100 bbox.y<500")

# ⚠️ Works but not useful - All importance is 0
query(snap, "importance>500")  # Returns empty (all importance = 0)
```

### Pro/Enterprise Tier (Server API)

**All Fields Available:**
- ✅ `importance` - Proprietary scoring (e.g., 1250)
- ✅ `visual_cues.is_primary` - Primary action detection
- ✅ `visual_cues.background_color_name` - Color analysis
- ✅ All free tier fields

**Example (Pro/Enterprise):**
```python
# ✅ Works - Importance filtering
query(snap, "importance>500")      # Returns high-importance elements
query(snap, "importance>=1000")    # Returns very important elements

# ✅ Works - Combined with importance
query(snap, "role=button importance>800 clickable=true")
```

**Note**: To use Pro/Enterprise tier, set `api_key` when creating the browser:

```python
browser = SentienceBrowser(api_key="your-api-key")
snap = snapshot(browser)  # Uses server-side API
```

---

## Best Practices

### 1. Use Semantic Roles

✅ **Good**: `role=button text~'Submit'`  
❌ **Avoid**: CSS selectors (not supported)

### 2. Combine Multiple Conditions

✅ **Good**: `role=button clickable=true text~'Sign in'`  
❌ **Avoid**: Single condition if multiple elements match

### 3. Use Text Matching Wisely

✅ **Good**: `text~'Sign in'` (case-insensitive, flexible)  
✅ **Good**: `text^='Sign'` (prefix matching)  
❌ **Avoid**: `text='Sign In'` (exact match, too brittle)

### 4. Filter by Visibility

✅ **Good**: `visible=true` or `in_viewport=true` for actionable elements  
✅ **Good**: `is_occluded=false` to exclude covered elements

### 5. Use Importance (Pro/Enterprise)

✅ **Good**: `importance>500` to find high-priority elements  
✅ **Good**: Combine with role: `role=button importance>800`

### 6. Spatial Filtering

✅ **Good**: `bbox.x>100` to find elements in specific regions  
✅ **Good**: Combine with other conditions: `role=button bbox.x>400`

### 7. Query Performance

- ✅ Use `find()` instead of `query()[0]` for single elements
- ✅ Add `visible=true` to reduce result set size
- ✅ Use specific conditions to narrow results
- ⚠️ Avoid `importance` queries on free tier (all values are 0)

---

## API Reference

### `query(snapshot, selector) -> List[Element]`

Query elements from snapshot using semantic selector.

**Parameters:**
- `snapshot` (Snapshot): Snapshot object from `snapshot()`
- `selector` (str | dict): DSL selector string or query dict

**Returns:**
- `List[Element]`: Matching elements, sorted by importance (descending)

**Example:**
```python
results = query(snap, "role=button importance>500")
for element in results:
    print(f"Found: {element.text} (importance: {element.importance})")
```

### `find(snapshot, selector) -> Optional[Element]`

Find single best matching element.

**Parameters:**
- `snapshot` (Snapshot): Snapshot object from `snapshot()`
- `selector` (str | dict): DSL selector string or query dict

**Returns:**
- `Optional[Element]`: Best matching element (highest importance) or `None`

**Example:**
```python
button = find(snap, "role=button text~'Submit'")
if button:
    click(browser, button.id)
```

### `parse_selector(selector) -> Dict[str, Any]`

Parse DSL selector string into structured query dictionary.

**Parameters:**
- `selector` (str): DSL selector string

**Returns:**
- `Dict[str, Any]`: Structured query dictionary

**Example:**
```python
query_dict = parse_selector("role=button text~'Sign in'")
# Returns: {"role": "button", "text_contains": "Sign in"}
```

---

## Common Patterns

### Find Primary Action Button

```python
# Pro/Enterprise: Use importance
button = find(snap, "role=button importance>800 clickable=true")

# Free tier: Use text and position
button = find(snap, "role=button text~'Submit' bbox.y<200")
```

### Find Form Inputs

```python
# Email field
email = find(snap, "role=textbox name~'email'")

# Password field
password = find(snap, "role=textbox name~'password'")

# All text inputs
inputs = query(snap, "role=textbox")
```

### Find Navigation Links

```python
# All links
links = query(snap, "role=link")

# Visible links only
visible_links = query(snap, "role=link in_viewport=true")

# Links with specific text
about_link = find(snap, "role=link text~'About'")
```

### Find Elements in Region

```python
# Top-left corner
top_left = query(snap, "bbox.x<200 bbox.y<200")

# Right side
right_side = query(snap, "bbox.x>800")

# Center region
center = query(snap, "bbox.x>400 bbox.x<600 bbox.y>300 bbox.y<500")
```

---

## Troubleshooting

### No Results Returned

**Problem**: Query returns empty list

**Solutions**:
- Check if field exists: Free tier `importance` is always 0
- Verify text matching: Use `~` (contains) instead of `=` (exact)
- Check visibility: Add `visible=true` or `in_viewport=true`
- Use less specific conditions: Remove some terms

### Too Many Results

**Problem**: Query returns too many elements

**Solutions**:
- Add more specific conditions
- Use `importance` filtering (Pro/Enterprise)
- Add spatial constraints (`bbox.x`, `bbox.y`)
- Use `find()` instead of `query()` for single element

### Query Syntax Errors

**Problem**: Parser fails or returns unexpected results

**Solutions**:
- Quote values with spaces: `text~'Sign in'` not `text~Sign in`
- Use correct operators: `~` for contains, `=` for exact
- Check field names: Use `role`, `text`, `clickable`, not `element.role`
- Verify numeric comparisons: Use `>`, `>=`, `<`, `<=` for numbers

---

## See Also

- [Snapshot API Documentation](../README.md#snapshot)
- [Examples](../examples/query_demo.py)
- [Type Definitions](../../spec/sdk-types.md)
- [Snapshot Schema](../../spec/snapshot.schema.json)

