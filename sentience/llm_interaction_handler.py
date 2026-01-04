"""
LLM Interaction Handler for Sentience Agent.

Handles all LLM-related operations: context building, querying, and response parsing.
This separates LLM interaction concerns from action execution.
"""

import re

from .llm_provider import LLMProvider, LLMResponse
from .models import Snapshot


class LLMInteractionHandler:
    """
    Handles LLM queries and response parsing for Sentience Agent.

    This class encapsulates all LLM interaction logic, making it easier to:
    - Test LLM interactions independently
    - Swap LLM providers without changing agent code
    - Modify prompt templates in one place
    """

    def __init__(self, llm: LLMProvider):
        """
        Initialize LLM interaction handler.

        Args:
            llm: LLM provider instance (OpenAIProvider, AnthropicProvider, etc.)
        """
        self.llm = llm

    def build_context(self, snap: Snapshot, goal: str | None = None) -> str:
        """
        Convert snapshot elements to token-efficient prompt string.

        Format: [ID] <role> "text" {cues} @ position size:WxH importance:score [status]

        Args:
            snap: Snapshot object
            goal: Optional user goal (for context, currently unused but kept for API consistency)

        Returns:
            Formatted element context string
        """
        lines = []
        for el in snap.elements:
            # Skip REMOVED elements - they're not actionable and shouldn't be in LLM context
            if el.diff_status == "REMOVED":
                continue
            # Extract visual cues
            cues: list[str] = []
            if el.visual_cues.is_primary:
                cues.append("PRIMARY")
            if el.visual_cues.is_clickable:
                cues.append("CLICKABLE")
            if el.visual_cues.background_color_name:
                cues.append(f"color:{el.visual_cues.background_color_name}")

            # Format element line with improved readability
            # Ensure cues is defined before using it in f-string
            cues_str = f" {{{','.join(cues)}}}" if cues else ""

            # Better text handling - show truncation indicator
            text_preview = ""
            if el.text:
                if len(el.text) > 50:
                    text_preview = f'"{el.text[:50]}..."'
                else:
                    text_preview = f'"{el.text}"'

            # Build position and size info
            x, y = int(el.bbox.x), int(el.bbox.y)
            width, height = int(el.bbox.width), int(el.bbox.height)
            position_str = f"@ ({x},{y})"
            size_str = f"size:{width}x{height}"

            # Build status indicators (only include if relevant)
            status_parts = []
            if not el.in_viewport:
                status_parts.append("not_in_viewport")
            if el.is_occluded:
                status_parts.append("occluded")
            if el.diff_status:
                status_parts.append(f"diff:{el.diff_status}")
            status_str = f" [{','.join(status_parts)}]" if status_parts else ""

            # Format: [ID] <role> "text" {cues} @ (x,y) size:WxH importance:score [status]
            lines.append(
                f"[{el.id}] <{el.role}> {text_preview}{cues_str} "
                f"{position_str} {size_str} importance:{el.importance}{status_str}"
            )

        return "\n".join(lines)

    def query_llm(self, dom_context: str, goal: str) -> LLMResponse:
        """
        Query LLM with standardized prompt template.

        Args:
            dom_context: Formatted element context from build_context()
            goal: User goal

        Returns:
            LLMResponse from LLM provider
        """
        system_prompt = f"""You are an AI web automation agent.

GOAL: {goal}

VISIBLE ELEMENTS (sorted by importance):
{dom_context}

VISUAL CUES EXPLAINED:
After the text, you may see visual cues in curly braces like {{CLICKABLE}} or {{PRIMARY,CLICKABLE,color:white}}:
- PRIMARY: Main call-to-action element on the page
- CLICKABLE: Element is clickable/interactive
- color:X: Background color name (e.g., color:white, color:blue)
Multiple cues are comma-separated inside the braces: {{CLICKABLE,color:white}}

ELEMENT FORMAT EXPLAINED:
Each element line follows this format:
[ID] <role> "text" {{cues}} @ (x,y) size:WxH importance:score [status]

Example: [346] <button> "Computer Accessories" {{CLICKABLE,color:white}} @ (664,100) size:150x40 importance:811

Breaking down each part:
- [ID]: The number in brackets is the element ID - use this EXACT number in CLICK/TYPE commands
  Example: If you see [346], use CLICK(346) or TYPE(346, "text")
- <role>: Element type (button, link, textbox, etc.)
- "text": Visible text content (truncated with "..." if long)
- {{cues}}: Optional visual cues in curly braces (e.g., {{CLICKABLE}}, {{PRIMARY,CLICKABLE}}, {{CLICKABLE,color:white}})
  If no cues, this part is omitted entirely
- @ (x,y): Element position in pixels from top-left corner
- size:WxH: Element dimensions (width x height in pixels)
- importance: Score indicating element relevance (higher = more important)
- [status]: Optional status flags in brackets (not_in_viewport, occluded, diff:ADDED/MODIFIED/etc)

CRITICAL RESPONSE FORMAT:
You MUST respond with ONLY ONE of these exact action formats:
- CLICK(id) - Click element by ID (use the number from [ID] brackets)
- TYPE(id, "text") - Type text into element (use the number from [ID] brackets)
- PRESS("key") - Press keyboard key (Enter, Escape, Tab, ArrowDown, etc)
- FINISH() - Task complete

DO NOT include any explanation, reasoning, or natural language.
DO NOT use markdown formatting or code blocks.
DO NOT say "The next step is..." or anything similar.

CORRECT Examples (matching element IDs from the list above):
If element is [346] <button> "Click me" → respond: CLICK(346)
If element is [15] <textbox> "Search" → respond: TYPE(15, "magic mouse")
PRESS("Enter")
FINISH()

INCORRECT Examples (DO NOT DO THIS):
"The next step is to click..."
"I will type..."
```CLICK(42)```
"""

        user_prompt = "Return the single action command:"

        return self.llm.generate(system_prompt, user_prompt, temperature=0.0)

    def extract_action(self, response: str) -> str:
        """
        Extract action command from LLM response.

        Handles cases where the LLM adds extra explanation despite instructions.

        Args:
            response: Raw LLM response text

        Returns:
            Cleaned action command string (e.g., "CLICK(42)", "TYPE(15, \"text\")")
        """
        # Remove markdown code blocks if present
        response = re.sub(r"```[\w]*\n?", "", response)
        response = response.strip()

        # Try to find action patterns in the response
        # Pattern matches: CLICK(123), TYPE(123, "text"), PRESS("key"), FINISH()
        action_pattern = r'(CLICK\s*\(\s*\d+\s*\)|TYPE\s*\(\s*\d+\s*,\s*["\'].*?["\']\s*\)|PRESS\s*\(\s*["\'].*?["\']\s*\)|FINISH\s*\(\s*\))'

        match = re.search(action_pattern, response, re.IGNORECASE)
        if match:
            return match.group(1)

        # If no pattern match, return the original response (will likely fail parsing)
        return response
