"""
LLM Interaction Handler for Sentience Agent.

Handles all LLM-related operations: context building, querying, and response parsing.
This separates LLM interaction concerns from action execution.
"""

import re
from typing import Optional

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

        Format: [ID] <role> "text" {cues} @ (x,y) (Imp:score)

        Args:
            snap: Snapshot object
            goal: Optional user goal (for context, currently unused but kept for API consistency)

        Returns:
            Formatted element context string
        """
        lines = []
        for el in snap.elements:
            # Extract visual cues
            cues = []
            if el.visual_cues.is_primary:
                cues.append("PRIMARY")
            if el.visual_cues.is_clickable:
                cues.append("CLICKABLE")
            if el.visual_cues.background_color_name:
                cues.append(f"color:{el.visual_cues.background_color_name}")

            # Format element line
            cues_str = f" {{{','.join(cues)}}}" if cues else ""
            text_preview = (
                (el.text[:50] + "...") if el.text and len(el.text) > 50 else (el.text or "")
            )

            lines.append(
                f'[{el.id}] <{el.role}> "{text_preview}"{cues_str} '
                f"@ ({int(el.bbox.x)},{int(el.bbox.y)}) (Imp:{el.importance})"
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
- {{PRIMARY}}: Main call-to-action element on the page
- {{CLICKABLE}}: Element is clickable
- {{color:X}}: Background color name

CRITICAL RESPONSE FORMAT:
You MUST respond with ONLY ONE of these exact action formats:
- CLICK(id) - Click element by ID
- TYPE(id, "text") - Type text into element
- PRESS("key") - Press keyboard key (Enter, Escape, Tab, ArrowDown, etc)
- FINISH() - Task complete

DO NOT include any explanation, reasoning, or natural language.
DO NOT use markdown formatting or code blocks.
DO NOT say "The next step is..." or anything similar.

CORRECT Examples:
CLICK(42)
TYPE(15, "magic mouse")
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
