"""
Visual Agent - Uses labeled screenshots with vision-capable LLMs

This agent extends SentienceAgentAsync to use visual prompts:
1. Takes snapshot with screenshot enabled
2. Draws bounding boxes and labels element IDs on the screenshot
3. Uses anti-collision algorithm to position labels (4 sides + 4 corners)
4. Sends labeled screenshot to vision-capable LLM
5. Extracts element ID from LLM response
6. Clicks the element using click_async

Dependencies:
    - Pillow (PIL): Required for image processing and drawing bounding boxes
      Install with: pip install Pillow
"""

import base64
import hashlib
import io
import re
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .actions import click, click_async
from .agent import SentienceAgent, SentienceAgentAsync, _safe_tracer_call
from .async_api import AsyncSentienceBrowser
from .browser import SentienceBrowser
from .llm_provider import LLMProvider, LLMResponse
from .models import AgentActionResult, Element, Snapshot, SnapshotOptions
from .snapshot import snapshot
from .snapshot_diff import SnapshotDiff
from .trace_event_builder import TraceEventBuilder

# Only import PIL types for type checking, not at runtime
if TYPE_CHECKING:
    from PIL import Image, ImageDraw, ImageFont
else:
    # Create a dummy type for runtime when PIL is not available
    Image = None
    ImageDraw = None
    ImageFont = None

try:
    from PIL import Image as PILImage
    from PIL import ImageDraw as PILImageDraw
    from PIL import ImageFont as PILImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    # Define dummy values so type hints don't fail
    PILImage = None  # type: ignore
    PILImageDraw = None  # type: ignore
    PILImageFont = None  # type: ignore
    # Don't print warning here - it will be printed when the class is instantiated


class SentienceVisualAgentAsync(SentienceAgentAsync):
    """
    Async visual agent that uses labeled screenshots with vision-capable LLMs.

    Extends SentienceAgentAsync to override act() method with visual prompting.

    Requirements:
        - Pillow (PIL): Required for image processing and drawing bounding boxes
          Install with: pip install Pillow
        - Vision-capable LLM: Requires an LLM provider that supports vision (e.g., GPT-4o, Claude 3)
    """

    def __init__(
        self,
        browser: AsyncSentienceBrowser,
        llm: LLMProvider,
        default_snapshot_limit: int = 50,
        verbose: bool = True,
        tracer: Any | None = None,
        config: Any | None = None,
    ):
        """
        Initialize Visual Agent

        Args:
            browser: AsyncSentienceBrowser instance
            llm: LLM provider (must support vision, e.g., GPT-4o, Claude 3)
            default_snapshot_limit: Default maximum elements to include
            verbose: Print execution logs
            tracer: Optional Tracer instance
            config: Optional AgentConfig
        """
        super().__init__(browser, llm, default_snapshot_limit, verbose, tracer, config)

        if not PIL_AVAILABLE:
            raise ImportError(
                "PIL/Pillow is required for SentienceVisualAgentAsync. Install with: pip install Pillow"
            )

        # Track previous snapshot for diff computation
        self._previous_snapshot: Snapshot | None = None

    def _decode_screenshot(self, screenshot_data_url: str) -> "PILImage.Image":
        """
        Decode base64 screenshot data URL to PIL Image

        Args:
            screenshot_data_url: Base64-encoded data URL (e.g., "data:image/png;base64,...")

        Returns:
            PIL Image object
        """
        # Extract base64 data from data URL
        if screenshot_data_url.startswith("data:image/"):
            # Format: "data:image/png;base64,<base64_data>"
            base64_data = screenshot_data_url.split(",", 1)[1]
        else:
            # Assume it's already base64
            base64_data = screenshot_data_url

        # Decode base64 to bytes
        image_bytes = base64.b64decode(base64_data)

        # Create PIL Image from bytes
        return PILImage.open(io.BytesIO(image_bytes))

    def _find_label_position(
        self,
        bbox: dict[str, float],
        existing_labels: list[dict[str, Any]],
        image_width: int,
        image_height: int,
        label_width: int,
        label_height: int,
    ) -> tuple[float, float]:
        """
        Find best position for label using anti-collision algorithm.

        Tries 8 positions: 4 sides (top, bottom, left, right) + 4 corners (top-left, top-right, bottom-left, bottom-right)

        Args:
            bbox: Element bounding box {x, y, width, height}
            existing_labels: List of existing label positions {x, y, width, height}
            image_width: Screenshot width
            image_height: Screenshot height
            label_width: Label text width
            label_height: Label text height

        Returns:
            (x, y) position for label
        """
        x, y, width, height = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
        center_x = x + width / 2
        center_y = y + height / 2

        # Anti-collision algorithm
        # Define 8 candidate positions (4 sides + 4 corners)
        # Increased distance from element to avoid confusion (15px instead of 5px)
        label_offset = 15  # Increased from 5 to make labels more clearly separate
        candidates = [
            # 4 sides
            (center_x - label_width / 2, y - label_height - label_offset, "top"),  # Above element
            (center_x - label_width / 2, y + height + label_offset, "bottom"),  # Below element
            (
                x - label_width - label_offset,
                center_y - label_height / 2,
                "left",
            ),  # Left of element
            (x + width + label_offset, center_y - label_height / 2, "right"),  # Right of element
            # 4 corners
            (
                x - label_width - label_offset,
                y - label_height - label_offset,
                "top-left",
            ),  # Top-left corner
            (
                x + width + label_offset,
                y - label_height - label_offset,
                "top-right",
            ),  # Top-right corner
            (
                x - label_width - label_offset,
                y + height + label_offset,
                "bottom-left",
            ),  # Bottom-left corner
            (
                x + width + label_offset,
                y + height + label_offset,
                "bottom-right",
            ),  # Bottom-right corner
        ]

        # Check each candidate position for collisions
        for candidate_x, candidate_y, _ in candidates:
            # Check bounds
            if candidate_x < 0 or candidate_y < 0:
                continue
            if candidate_x + label_width > image_width or candidate_y + label_height > image_height:
                continue

            # Check collision with existing labels
            collision = False
            for existing in existing_labels:
                ex, ey, ew, eh = existing["x"], existing["y"], existing["width"], existing["height"]
                # Check if rectangles overlap
                if not (
                    candidate_x + label_width < ex
                    or candidate_x > ex + ew
                    or candidate_y + label_height < ey
                    or candidate_y > ey + eh
                ):
                    collision = True
                    break

            if not collision:
                return (candidate_x, candidate_y)

        # If all positions collide, use top position (may overlap but better than nothing)
        return (center_x - label_width / 2, y - label_height - 15)

    def _draw_labeled_screenshot(
        self,
        snapshot: Snapshot,
        elements: list[Element],
    ) -> "PILImage.Image":
        """
        Draw bounding boxes and labels on screenshot.

        Args:
            snapshot: Snapshot with screenshot data
            elements: List of elements to draw

        Returns:
            PIL Image with bounding boxes and labels
        """
        if not snapshot.screenshot:
            raise ValueError("Screenshot not available in snapshot")

        # Decode screenshot
        img = self._decode_screenshot(snapshot.screenshot)
        draw = PILImageDraw.Draw(img)

        # Try to load a font, fallback to default if not available
        try:
            # Try to use a system font
            font = PILImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        except:
            try:
                font = PILImageFont.truetype("arial.ttf", 16)
            except:
                # Use default font if system fonts not available
                font = PILImageFont.load_default()

        image_width, image_height = img.size
        existing_labels: list[dict[str, Any]] = []

        # Neon green color: #39FF14 (bright, vibrant green)
        neon_green = "#39FF14"

        # Draw bounding boxes and labels for each element
        for element in elements:
            bbox = element.bbox
            x, y, width, height = bbox.x, bbox.y, bbox.width, bbox.height

            # Draw bounding box rectangle (neon green with 2px width)
            draw.rectangle(
                [(x, y), (x + width, y + height)],
                outline=neon_green,
                width=2,
            )

            # Prepare label text (just the number - keep it simple and compact)
            label_text = str(element.id)

            # Measure label text size
            bbox_text = draw.textbbox((0, 0), label_text, font=font)
            label_width = bbox_text[2] - bbox_text[0]
            label_height = bbox_text[3] - bbox_text[1]

            # Find best position for label (anti-collision)
            label_x, label_y = self._find_label_position(
                {"x": x, "y": y, "width": width, "height": height},
                existing_labels,
                image_width,
                image_height,
                label_width + 8,  # Add padding
                label_height + 4,  # Add padding
            )

            # Calculate connection points for a clearer visual link
            # Connect from the nearest corner/edge of element to the label
            element_center_x = x + width / 2
            element_center_y = y + height / 2
            label_center_x = label_x + label_width / 2
            label_center_y = label_y + label_height / 2

            # Determine which edge of the element is closest to the label
            # and draw line from that edge point to the label
            dist_top = abs(label_center_y - y)
            dist_bottom = abs(label_center_y - (y + height))
            dist_left = abs(label_center_x - x)
            dist_right = abs(label_center_x - (x + width))

            min_dist = min(dist_top, dist_bottom, dist_left, dist_right)

            if min_dist == dist_top:
                # Label is above - connect from top edge
                line_start = (element_center_x, y)
            elif min_dist == dist_bottom:
                # Label is below - connect from bottom edge
                line_start = (element_center_x, y + height)
            elif min_dist == dist_left:
                # Label is left - connect from left edge
                line_start = (x, element_center_y)
            else:
                # Label is right - connect from right edge
                line_start = (x + width, element_center_y)

            # Draw connecting line from element edge to label (makes it clear the label belongs to the element)
            draw.line(
                [line_start, (label_center_x, label_center_y)],
                fill=neon_green,
                width=2,  # Slightly thicker for better visibility
            )

            # Draw label background (white with neon green border)
            label_bg_x1 = label_x - 4
            label_bg_y1 = label_y - 2
            label_bg_x2 = label_x + label_width + 4
            label_bg_y2 = label_y + label_height + 2

            # Draw white background with neon green border (makes label stand out as separate)
            draw.rectangle(
                [(label_bg_x1, label_bg_y1), (label_bg_x2, label_bg_y2)],
                fill="white",
                outline=neon_green,
                width=2,  # Thicker border to make it more distinct
            )

            # Draw label text (black for high contrast)
            draw.text(
                (label_x, label_y),
                label_text,
                fill="black",
                font=font,
            )

            # Record label position for collision detection
            existing_labels.append(
                {
                    "x": label_bg_x1,
                    "y": label_bg_y1,
                    "width": label_bg_x2 - label_bg_x1,
                    "height": label_bg_y2 - label_bg_y1,
                }
            )

        return img

    def _encode_image_to_base64(
        self, image: "PILImage.Image", format: str = "PNG", max_size_mb: float = 20.0
    ) -> str:
        """
        Encode PIL Image to base64 data URL with size optimization.

        Vision LLM APIs typically have size limits (e.g., 20MB for OpenAI).
        This function automatically compresses images if they're too large.

        Args:
            image: PIL Image object
            format: Image format (PNG or JPEG)
            max_size_mb: Maximum size in MB before compression (default: 20MB)

        Returns:
            Base64-encoded data URL
        """
        # Convert format for PIL
        pil_format = format.upper()

        # Try JPEG first for better compression (unless PNG is specifically requested)
        if format.upper() != "PNG":
            pil_format = "JPEG"
            # Convert RGBA to RGB for JPEG
            if image.mode in ("RGBA", "LA", "P"):
                # Create white background
                rgb_image = PILImage.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                rgb_image.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
                image = rgb_image

        buffer = io.BytesIO()
        quality = 95  # Start with high quality

        # Try to fit within size limit
        for attempt in range(3):
            buffer.seek(0)
            buffer.truncate(0)

            if pil_format == "JPEG":
                image.save(buffer, format=pil_format, quality=quality, optimize=True)
            else:
                image.save(buffer, format=pil_format, optimize=True)

            size_mb = len(buffer.getvalue()) / (1024 * 1024)

            if size_mb <= max_size_mb:
                break

            # Reduce quality for next attempt
            quality = max(70, quality - 15)
            if self.verbose and attempt == 0:
                print(f"   ⚠️  Image size {size_mb:.2f}MB exceeds limit, compressing...")

        image_bytes = buffer.getvalue()
        base64_data = base64.b64encode(image_bytes).decode("utf-8")

        final_size_mb = len(image_bytes) / (1024 * 1024)
        if self.verbose:
            print(f"   📸 Image encoded: {final_size_mb:.2f}MB ({len(base64_data)} chars base64)")

        mime_type = "image/png" if pil_format == "PNG" else "image/jpeg"
        return f"data:{mime_type};base64,{base64_data}"

    async def _query_llm_with_vision(
        self,
        image_data_url: str,
        goal: str,
    ) -> LLMResponse:
        """
        Query LLM with vision (labeled screenshot).

        Args:
            image_data_url: Base64-encoded image data URL
            goal: User's goal/task

        Returns:
            LLMResponse with element ID
        """
        system_prompt = """You are a web automation assistant. You will see a screenshot of a web page with labeled element IDs.
Each clickable element has:
- A bright neon green (#39FF14) bounding box around the element
- A white label box with a number (the element ID) connected by a green line
- The label is clearly separate from the element (not part of the UI)

CRITICAL INSTRUCTIONS:
1. Look at the screenshot carefully
2. Find the element that matches the user's goal (ignore the white label boxes - they are annotations, not UI elements)
3. Follow the green line from that element to find its label box with the ID number
4. Respond with ONLY that integer ID number (e.g., "42" or "1567")
5. Do NOT include any explanation, reasoning, or other text
6. Do NOT say "element 1" or "the first element" - just return the number
7. Do NOT confuse the white label box with an interactive element - labels are annotations connected by green lines

Example responses:
- Correct: "42"
- Correct: "1567"
- Wrong: "I see element 42"
- Wrong: "The element ID is 42"
- Wrong: "42 (the search box)" """

        user_prompt = f"""Goal: {goal}

Look at the screenshot. Each element has a neon green bounding box with a white label showing its ID number.
Find the element that should be clicked to accomplish this goal.
Return ONLY the integer ID number from the label, nothing else."""

        # Check if LLM provider supports vision (OpenAI GPT-4o, Claude, etc.)
        # Vision-capable providers use similar message format with image_url
        if hasattr(self.llm, "client") and hasattr(self.llm.client, "chat"):
            # Vision-capable provider - use vision API
            try:
                from openai import OpenAI

                # Check if it's OpenAI
                if isinstance(self.llm.client, OpenAI):
                    messages = [
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_data_url},
                                },
                            ],
                        },
                    ]

                    response = self.llm.client.chat.completions.create(
                        model=self.llm._model_name,
                        messages=messages,
                        temperature=0.0,
                        # Removed max_tokens to use API default (usually higher limit)
                    )

                    content = response.choices[0].message.content or ""
                    usage = response.usage

                    from .llm_response_builder import LLMResponseBuilder

                    return LLMResponseBuilder.from_openai_format(
                        content=content,
                        prompt_tokens=usage.prompt_tokens if usage else None,
                        completion_tokens=usage.completion_tokens if usage else None,
                        total_tokens=usage.total_tokens if usage else None,
                        model_name=response.model,
                        finish_reason=response.choices[0].finish_reason,
                    )

                # Check if provider supports vision API (uses OpenAI-compatible format)
                elif hasattr(self.llm, "client") and hasattr(self.llm.client, "chat"):
                    # Vision API uses similar format to OpenAI
                    if self.verbose:
                        print(f"   🔍 Using vision API with model: {self.llm._model_name}")
                        print(f"   📐 Image data URL length: {len(image_data_url)} chars")

                    messages = [
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_data_url},
                                },
                            ],
                        },
                    ]

                    try:
                        if self.verbose:
                            print(f"   📤 Sending request to vision API...")
                            print(f"   📋 Messages structure: {len(messages)} messages")
                            print(f"   🖼️  Image URL prefix: {image_data_url[:50]}...")

                        # Removed max_tokens to use API default (usually higher limit)
                        # This allows the model to generate complete responses without truncation
                        response = self.llm.client.chat.completions.create(
                            model=self.llm._model_name,
                            messages=messages,
                            temperature=0.0,
                            # No max_tokens - use API default
                        )

                        # Debug: Check response structure
                        if self.verbose:
                            print(f"   📥 Response received")
                            print(f"   📦 Response type: {type(response)}")
                            print(
                                f"   📦 Choices count: {len(response.choices) if hasattr(response, 'choices') else 0}"
                            )

                        if not hasattr(response, "choices") or len(response.choices) == 0:
                            raise ValueError("Vision API returned no choices in response")

                        choice = response.choices[0]
                        content = (
                            choice.message.content if hasattr(choice.message, "content") else None
                        )
                        finish_reason = (
                            choice.finish_reason if hasattr(choice, "finish_reason") else None
                        )

                        if self.verbose:
                            print(f"   📝 Content: {repr(content)}")
                            print(f"   🏁 Finish reason: {finish_reason}")
                            if finish_reason:
                                print(f"   ⚠️  Finish reason indicates: {finish_reason}")
                                if finish_reason == "length":
                                    print(
                                        f"      - Response was truncated (hit API default max_tokens limit)"
                                    )
                                    print(
                                        f"      - This might indicate the model needs more tokens or doesn't support vision properly"
                                    )
                                    # Even if truncated, there might be partial content
                                    if content:
                                        print(
                                            f"      - ⚠️  Partial content received: {repr(content)}"
                                        )
                                elif finish_reason == "content_filter":
                                    print(f"      - Content was filtered by safety filters")
                                elif finish_reason == "stop":
                                    print(f"      - Normal completion")

                        # If finish_reason is "length", we might still have partial content
                        # Try to use it if available (even if truncated, it might contain the element ID)
                        if finish_reason == "length" and content and content.strip():
                            if self.verbose:
                                print(f"   ⚠️  Using truncated response: {repr(content)}")
                            # Continue processing with partial content

                        if content is None or content == "":
                            error_msg = f"Vision API returned empty content (finish_reason: {finish_reason})"
                            if self.verbose:
                                print(f"   ❌ {error_msg}")
                                print(f"   💡 Possible causes:")
                                print(
                                    f"      - Model {self.llm._model_name} may not support vision"
                                )
                                print(f"      - Image format might not be supported")
                                print(f"      - API default max_tokens might be too restrictive")
                                print(f"      - API response structure might be different")
                                if finish_reason == "length":
                                    print(
                                        f"      - ⚠️  Response was truncated - content might have been cut off"
                                    )
                                    print(
                                        f"      - Try increasing max_tokens or check response.choices[0].message for partial content"
                                    )
                            raise ValueError(error_msg)

                        usage = response.usage if hasattr(response, "usage") else None

                        if self.verbose:
                            print(f"   ✅ Vision API response received")
                            print(
                                f"   📊 Tokens: {usage.total_tokens if usage else 'N/A'} (prompt: {usage.prompt_tokens if usage else 'N/A'}, completion: {usage.completion_tokens if usage else 'N/A'})"
                            )

                        from .llm_response_builder import LLMResponseBuilder

                        return LLMResponseBuilder.from_openai_format(
                            content=content,
                            prompt_tokens=usage.prompt_tokens if usage else None,
                            completion_tokens=usage.completion_tokens if usage else None,
                            total_tokens=usage.total_tokens if usage else None,
                            model_name=(
                                response.model
                                if hasattr(response, "model")
                                else self.llm._model_name
                            ),
                            finish_reason=finish_reason,
                        )
                    except Exception as vision_error:
                        if self.verbose:
                            print(f"   ❌ Vision API error: {vision_error}")
                            print(f"   💡 This might indicate:")
                            print(f"      - Model {self.llm._model_name} doesn't support vision")
                            print(f"      - Image format/size issue")
                            print(f"      - API key or permissions issue")
                            print(f"   🔄 Attempting fallback to regular generate method...")

                        # Fallback: Try using the regular generate method
                        # Some models might need images passed differently
                        try:
                            # Try embedding image in the prompt as base64
                            fallback_prompt = f"{user_prompt}\n\n[Image: {image_data_url[:200]}...]"
                            fallback_response = self.llm.generate(
                                system_prompt,
                                fallback_prompt,
                                temperature=0.0,
                                # No max_tokens - use API default
                            )
                            if self.verbose:
                                print(f"   ⚠️  Using fallback method (may not support vision)")
                            return fallback_response
                        except Exception as fallback_error:
                            if self.verbose:
                                print(f"   ❌ Fallback also failed: {fallback_error}")
                            raise vision_error  # Raise original error
            except ImportError:
                # openai or other vision SDK not available
                pass
            except Exception as e:
                if self.verbose:
                    print(f"⚠️  Vision API error: {e}, falling back to text-only")

        # Fallback: Try to pass image via kwargs or use text-only
        # Some providers might accept image in kwargs
        try:
            return self.llm.generate(
                system_prompt,
                f"{user_prompt}\n\n[Image data: {image_data_url[:100]}...]",
                temperature=0.0,
                # No max_tokens - use API default
            )
        except Exception as e:
            raise RuntimeError(
                f"LLM provider {type(self.llm).__name__} may not support vision. "
                f"Error: {e}. Use a vision-capable model like GPT-4o or Claude 3."
            ) from e

    def _extract_element_id(self, llm_response: str) -> int | None:
        """
        Extract element ID integer from LLM response.

        Args:
            llm_response: LLM response text

        Returns:
            Element ID as integer, or None if not found
        """
        if self.verbose:
            print(f"🔍 Raw LLM response: {repr(llm_response)}")

        # Clean the response - remove leading/trailing whitespace (handles '\n177', '177\n', etc.)
        cleaned = llm_response.strip()

        if self.verbose:
            print(f"   🧹 After strip: {repr(cleaned)}")

        # Remove common prefixes that LLMs might add
        prefixes_to_remove = [
            "element",
            "id",
            "the element",
            "element id",
            "the id",
            "click",
            "click on",
            "select",
            "choose",
        ]
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
                # Remove any remaining punctuation
                cleaned = cleaned.lstrip(":.,;!?()[]{}")
                cleaned = cleaned.strip()
                if self.verbose:
                    print(f"   🧹 After removing prefix '{prefix}': {repr(cleaned)}")

        # Try to find all integers in the cleaned response
        numbers = re.findall(r"\d+", cleaned)

        if self.verbose:
            print(f"   🔢 Numbers found: {numbers}")

        if numbers:
            # If multiple numbers found, prefer the largest one (likely the actual element ID)
            # Element IDs are typically larger numbers, not small ones like "1"
            try:
                # Convert all to int
                int_numbers = [int(n) for n in numbers]
                if self.verbose:
                    print(f"   🔢 As integers: {int_numbers}")

                # Prefer larger numbers (element IDs are usually > 10)
                # But if only small numbers exist, use the first one
                large_numbers = [n for n in int_numbers if n > 10]
                if large_numbers:
                    element_id = max(large_numbers)  # Take the largest
                    if self.verbose:
                        print(f"   ✅ Selected largest number > 10: {element_id}")
                else:
                    element_id = int_numbers[0]  # Fallback to first if all are small
                    if self.verbose:
                        print(f"   ⚠️  All numbers ≤ 10, using first: {element_id}")

                if self.verbose:
                    print(f"✅ Extracted element ID: {element_id} (from {numbers})")
                return element_id
            except ValueError:
                if self.verbose:
                    print(f"   ❌ Failed to convert numbers to integers")
                pass

        if self.verbose:
            print(f"⚠️  Could not extract element ID from response: {llm_response}")
        return None

    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def act(
        self,
        goal: str,
        max_retries: int = 2,
        snapshot_options: SnapshotOptions | None = None,
    ) -> AgentActionResult:
        """
        Override act() method to use visual prompting with full tracing support.

        Args:
            goal: User's goal/task
            max_retries: Maximum retry attempts
            snapshot_options: Optional snapshot options (screenshot will be enabled)

        Returns:
            AgentActionResult
        """
        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"🤖 Visual Agent Goal: {goal}")
            print(f"{'=' * 70}")

        # Generate step ID for tracing
        self._step_count += 1
        step_id = f"step-{self._step_count}"

        # Emit step_start trace event if tracer is enabled
        if self.tracer:
            pre_url = self.browser.page.url if self.browser.page else None
            _safe_tracer_call(
                self.tracer,
                "emit_step_start",
                self.verbose,
                step_id=step_id,
                step_index=self._step_count,
                goal=goal,
                attempt=0,
                pre_url=pre_url,
            )

        start_time = time.time()

        try:
            # Ensure screenshot is enabled
            if snapshot_options is None:
                snapshot_options = SnapshotOptions()

            # Enable screenshot if not already enabled
            if snapshot_options.screenshot is False or snapshot_options.screenshot is None:
                from .models import ScreenshotConfig

                snapshot_options.screenshot = ScreenshotConfig(format="png")

            # Set goal if not already provided
            if snapshot_options.goal is None:
                snapshot_options.goal = goal

            # Set limit if not provided
            if snapshot_options.limit is None:
                snapshot_options.limit = self.default_snapshot_limit

            if self.verbose:
                print(f"🎯 Goal: {goal}")
                print("📸 Taking snapshot with screenshot...")

            # 1. Take snapshot with screenshot
            from .snapshot import snapshot_async

            snap = await snapshot_async(self.browser, snapshot_options)

            if snap.status != "success":
                raise RuntimeError(f"Snapshot failed: {snap.error}")

            if not snap.screenshot:
                raise RuntimeError("Screenshot not available in snapshot")

            # Compute diff_status by comparing with previous snapshot
            elements_with_diff = SnapshotDiff.compute_diff_status(snap, self._previous_snapshot)

            # Create snapshot with diff_status populated
            snap_with_diff = Snapshot(
                status=snap.status,
                timestamp=snap.timestamp,
                url=snap.url,
                viewport=snap.viewport,
                elements=elements_with_diff,
                screenshot=snap.screenshot,
                screenshot_format=snap.screenshot_format,
                error=snap.error,
            )

            # Update previous snapshot for next comparison
            self._previous_snapshot = snap

            # Emit snapshot trace event if tracer is enabled
            if self.tracer:
                # Build snapshot event data (use snap_with_diff to include diff_status)
                snapshot_data = TraceEventBuilder.build_snapshot_event(snap_with_diff)

                # Always include screenshot in trace event for studio viewer compatibility
                if snap.screenshot:
                    # Extract base64 string from data URL if needed
                    if snap.screenshot.startswith("data:image"):
                        # Format: "data:image/jpeg;base64,{base64_string}"
                        screenshot_base64 = (
                            snap.screenshot.split(",", 1)[1]
                            if "," in snap.screenshot
                            else snap.screenshot
                        )
                    else:
                        screenshot_base64 = snap.screenshot

                    snapshot_data["screenshot_base64"] = screenshot_base64
                    if snap.screenshot_format:
                        snapshot_data["screenshot_format"] = snap.screenshot_format

                _safe_tracer_call(
                    self.tracer,
                    "emit",
                    self.verbose,
                    "snapshot",
                    snapshot_data,
                    step_id=step_id,
                )

            if self.verbose:
                print(f"✅ Snapshot taken: {len(snap.elements)} elements")

            # 2. Draw labeled screenshot
            if self.verbose:
                print("🎨 Drawing bounding boxes and labels...")
                print(f"   Elements to label: {len(snap.elements)}")
                if len(snap.elements) > 0:
                    element_ids = [el.id for el in snap.elements[:10]]  # Show first 10
                    print(f"   Sample element IDs: {element_ids}")

            labeled_image = self._draw_labeled_screenshot(snap, snap.elements)

            # Save labeled image to disk for debugging
            # Save to playground/images if running from playground, otherwise use current directory
            try:
                # Try to detect if we're in a playground context
                import sys

                cwd = Path.cwd()
                playground_path = None

                # Check if current working directory contains playground
                if (cwd / "playground").exists():
                    playground_path = cwd / "playground" / "images"
                else:
                    # Check sys.path for playground
                    for path_str in sys.path:
                        path_obj = Path(path_str)
                        if "playground" in str(path_obj) and path_obj.exists():
                            # Find the playground directory
                            if path_obj.name == "playground":
                                playground_path = path_obj / "images"
                                break
                            elif (path_obj / "playground").exists():
                                playground_path = path_obj / "playground" / "images"
                                break

                if playground_path is None:
                    # Fallback: use current working directory
                    playground_path = cwd / "playground" / "images"

                images_dir = playground_path
                images_dir.mkdir(parents=True, exist_ok=True)
                image_uuid = str(uuid.uuid4())
                image_filename = f"labeled_screenshot_{image_uuid}.png"
                image_path = images_dir / image_filename
                labeled_image.save(image_path, format="PNG")
                if self.verbose:
                    print(f"   💾 Saved labeled screenshot: {image_path.absolute()}")
            except Exception as save_error:
                # Don't fail if image save fails - it's just for debugging
                if self.verbose:
                    print(f"   ⚠️  Could not save labeled screenshot: {save_error}")

            # Use JPEG for better compression (smaller file size for vision APIs)
            labeled_image_data_url = self._encode_image_to_base64(
                labeled_image, format="JPEG", max_size_mb=20.0
            )

            # 3. Query LLM with vision
            if self.verbose:
                print("🧠 Querying LLM with labeled screenshot...")

            llm_response = await self._query_llm_with_vision(labeled_image_data_url, goal)

            # Emit LLM query trace event if tracer is enabled
            if self.tracer:
                _safe_tracer_call(
                    self.tracer,
                    "emit",
                    self.verbose,
                    "llm_query",
                    {
                        "prompt_tokens": llm_response.prompt_tokens,
                        "completion_tokens": llm_response.completion_tokens,
                        "model": llm_response.model_name,
                        "response": llm_response.content[:200],  # Truncate for brevity
                    },
                    step_id=step_id,
                )

            if self.verbose:
                print(f"💭 LLM Response: {llm_response.content}")

            # Track token usage
            self._track_tokens(goal, llm_response)

            # 4. Extract element ID
            element_id = self._extract_element_id(llm_response.content)

            if element_id is None:
                raise ValueError(
                    f"Could not extract element ID from LLM response: {llm_response.content}"
                )

            if self.verbose:
                print(f"🎯 Extracted Element ID: {element_id}")

            # 5. Click the element
            if self.verbose:
                print(f"🖱️  Clicking element {element_id}...")

            click_result = await click_async(self.browser, element_id)

            duration_ms = int((time.time() - start_time) * 1000)

            # Create AgentActionResult from click result
            result = AgentActionResult(
                success=click_result.success,
                action="click",
                goal=goal,
                duration_ms=duration_ms,
                attempt=0,
                element_id=element_id,
                outcome=click_result.outcome,
                url_changed=click_result.url_changed,
                error=click_result.error,
            )

            # Emit action execution trace event if tracer is enabled
            if self.tracer:
                post_url = self.browser.page.url if self.browser.page else None

                # Include element data for live overlay visualization
                elements_data = [
                    {
                        "id": el.id,
                        "bbox": {
                            "x": el.bbox.x,
                            "y": el.bbox.y,
                            "width": el.bbox.width,
                            "height": el.bbox.height,
                        },
                        "role": el.role,
                        "text": el.text[:50] if el.text else "",
                    }
                    for el in snap.elements[:50]
                ]

                _safe_tracer_call(
                    self.tracer,
                    "emit",
                    self.verbose,
                    "action",
                    {
                        "action": result.action,
                        "element_id": result.element_id,
                        "success": result.success,
                        "outcome": result.outcome,
                        "duration_ms": duration_ms,
                        "post_url": post_url,
                        "elements": elements_data,  # Add element data for overlay
                        "target_element_id": result.element_id,  # Highlight target in red
                    },
                    step_id=step_id,
                )

            # Record history
            self.history.append(
                {
                    "goal": goal,
                    "action": f"CLICK({element_id})",
                    "result": result.model_dump(),  # Store as dict
                    "success": result.success,
                    "attempt": 0,
                    "duration_ms": duration_ms,
                }
            )

            if self.verbose:
                status = "✅" if result.success else "❌"
                print(f"{status} Completed in {duration_ms}ms")

            # Emit step completion trace event if tracer is enabled
            if self.tracer:
                # Get pre_url from step_start (stored in tracer or use current)
                pre_url = snap.url
                post_url = self.browser.page.url if self.browser.page else None

                # Compute snapshot digest (simplified - use URL + timestamp)
                snapshot_digest = f"sha256:{self._compute_hash(f'{pre_url}{snap.timestamp}')}"

                # Build LLM data
                llm_response_text = llm_response.content

                # Build execution data
                exec_data = {
                    "success": result.success,
                    "outcome": result.outcome,
                    "action": result.action,
                    "element_id": result.element_id,
                    "url_changed": result.url_changed,
                    "duration_ms": duration_ms,
                }

                # Build verification data (simplified - always pass for now)
                verify_data = {
                    "passed": result.success,
                    "signals": {
                        "url_changed": result.url_changed or False,
                    },
                }

                post_snapshot_digest = (
                    self._best_effort_post_snapshot_digest(goal) if self.tracer else None
                )

                # Build complete step_end event
                step_end_data = TraceEventBuilder.build_step_end_event(
                    step_id=step_id,
                    step_index=self._step_count,
                    goal=goal,
                    attempt=0,
                    pre_url=pre_url,
                    post_url=post_url or pre_url,
                    snapshot_digest=snapshot_digest,
                    post_snapshot_digest=post_snapshot_digest,
                    llm_data={
                        "response_text": llm_response_text,
                        "response_hash": f"sha256:{self._compute_hash(llm_response_text)}",
                    },
                    exec_data=exec_data,
                    verify_data=verify_data,
                )

                _safe_tracer_call(
                    self.tracer,
                    "emit",
                    self.verbose,
                    "step_end",
                    step_end_data,
                    step_id=step_id,
                )

            return result

        except Exception as e:
            # Emit error trace event if tracer is enabled
            if self.tracer:
                _safe_tracer_call(
                    self.tracer,
                    "emit_error",
                    self.verbose,
                    step_id=step_id,
                    error=str(e),
                    attempt=0,
                )

            if self.verbose:
                print(f"❌ Error: {e}")

            # Re-raise the exception
            raise


class SentienceVisualAgent(SentienceAgent):
    """
    Sync visual agent that uses labeled screenshots with vision-capable LLMs.

    Extends SentienceAgent to override act() method with visual prompting.

    Requirements:
        - Pillow (PIL): Required for image processing and drawing bounding boxes
          Install with: pip install Pillow
        - Vision-capable LLM: Requires an LLM provider that supports vision (e.g., GPT-4o, Claude 3)
    """

    def __init__(
        self,
        browser: SentienceBrowser,
        llm: LLMProvider,
        default_snapshot_limit: int = 50,
        verbose: bool = True,
        tracer: Any | None = None,
        config: Any | None = None,
    ):
        """
        Initialize Visual Agent

        Args:
            browser: SentienceBrowser instance
            llm: LLM provider (must support vision, e.g., GPT-4o, Claude 3)
            default_snapshot_limit: Default maximum elements to include
            verbose: Print execution logs
            tracer: Optional Tracer instance
            config: Optional AgentConfig
        """
        super().__init__(browser, llm, default_snapshot_limit, verbose, tracer, config)

        if not PIL_AVAILABLE:
            raise ImportError(
                "PIL/Pillow is required for SentienceVisualAgent. Install with: pip install Pillow"
            )

        # Track previous snapshot for diff computation
        self._previous_snapshot: Snapshot | None = None

    def _decode_screenshot(self, screenshot_data_url: str) -> "PILImage.Image":
        """
        Decode base64 screenshot data URL to PIL Image

        Args:
            screenshot_data_url: Base64-encoded data URL (e.g., "data:image/png;base64,...")

        Returns:
            PIL Image object
        """
        # Extract base64 data from data URL
        if screenshot_data_url.startswith("data:image/"):
            # Format: "data:image/png;base64,<base64_data>"
            base64_data = screenshot_data_url.split(",", 1)[1]
        else:
            # Assume it's already base64
            base64_data = screenshot_data_url

        # Decode base64 to bytes
        image_bytes = base64.b64decode(base64_data)

        # Load image from bytes
        return PILImage.open(io.BytesIO(image_bytes))

    def _find_label_position(
        self,
        element_bbox: dict[str, float],
        existing_labels: list[dict[str, float]],
        image_width: int,
        image_height: int,
        label_width: int,
        label_height: int,
    ) -> tuple[int, int]:
        """
        Find best position for label using anti-collision algorithm.

        Tries 8 positions: 4 sides (top, bottom, left, right) + 4 corners.
        Returns the first position that doesn't collide with existing labels.

        Args:
            element_bbox: Element bounding box {x, y, width, height}
            existing_labels: List of existing label bounding boxes
            image_width: Image width in pixels
            image_height: Image height in pixels
            label_width: Label width in pixels
            label_height: Label height in pixels

        Returns:
            (x, y) position for label
        """
        x, y = element_bbox["x"], element_bbox["y"]
        width, height = element_bbox["width"], element_bbox["height"]

        # Offset from element edge
        label_offset = 15  # Increased from 5px for better separation

        # Try 8 positions: top, bottom, left, right, top-left, top-right, bottom-left, bottom-right
        positions = [
            (int(x + width / 2 - label_width / 2), int(y - label_height - label_offset)),  # Top
            (int(x + width / 2 - label_width / 2), int(y + height + label_offset)),  # Bottom
            (int(x - label_width - label_offset), int(y + height / 2 - label_height / 2)),  # Left
            (int(x + width + label_offset), int(y + height / 2 - label_height / 2)),  # Right
            (int(x - label_width - label_offset), int(y - label_height - label_offset)),  # Top-left
            (int(x + width + label_offset), int(y - label_height - label_offset)),  # Top-right
            (int(x - label_width - label_offset), int(y + height + label_offset)),  # Bottom-left
            (int(x + width + label_offset), int(y + height + label_offset)),  # Bottom-right
        ]

        # Check each position for collisions
        for pos_x, pos_y in positions:
            # Check bounds
            if (
                pos_x < 0
                or pos_y < 0
                or pos_x + label_width > image_width
                or pos_y + label_height > image_height
            ):
                continue

            # Check collision with existing labels
            label_bbox = {
                "x": pos_x,
                "y": pos_y,
                "width": label_width,
                "height": label_height,
            }

            collision = False
            for existing in existing_labels:
                # Simple AABB collision detection
                if not (
                    label_bbox["x"] + label_bbox["width"] < existing["x"]
                    or label_bbox["x"] > existing["x"] + existing["width"]
                    or label_bbox["y"] + label_bbox["height"] < existing["y"]
                    or label_bbox["y"] > existing["y"] + existing["height"]
                ):
                    collision = True
                    break

            if not collision:
                return (pos_x, pos_y)

        # If all positions collide, use top position with increased offset
        return (int(x + width / 2 - label_width / 2), int(y - label_height - label_offset * 2))

    def _draw_labeled_screenshot(
        self,
        snapshot: Snapshot,
        elements: list[Element],
    ) -> "PILImage.Image":
        """
        Draw labeled screenshot with bounding boxes and element IDs.

        Args:
            snapshot: Snapshot with screenshot data
            elements: List of elements to label

        Returns:
            PIL Image with labels drawn
        """
        # Decode screenshot
        img = self._decode_screenshot(snapshot.screenshot)
        draw = PILImageDraw.Draw(img)

        # Load font (fallback to default if not available)
        try:
            font = PILImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        except OSError:
            try:
                font = PILImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16
                )
            except OSError:
                font = PILImageFont.load_default()

        image_width, image_height = img.size
        existing_labels: list[dict[str, float]] = []

        # Neon green color: #39FF14 (bright, vibrant green)
        neon_green = "#39FF14"

        for element in elements:
            bbox = element.bbox
            x, y, width, height = bbox.x, bbox.y, bbox.width, bbox.height

            # Draw bounding box rectangle (neon green with 2px width)
            draw.rectangle(
                [(x, y), (x + width, y + height)],
                outline=neon_green,
                width=2,
            )

            # Prepare label text (just the number - keep it simple and compact)
            label_text = str(element.id)

            # Measure label text size
            bbox_text = draw.textbbox((0, 0), label_text, font=font)
            label_width = bbox_text[2] - bbox_text[0]
            label_height = bbox_text[3] - bbox_text[1]

            # Find best position for label (anti-collision)
            label_x, label_y = self._find_label_position(
                {"x": x, "y": y, "width": width, "height": height},
                existing_labels,
                image_width,
                image_height,
                label_width + 8,  # Add padding
                label_height + 4,  # Add padding
            )

            # Calculate connection points for a clearer visual link
            element_center_x = x + width / 2
            element_center_y = y + height / 2
            label_center_x = label_x + label_width / 2
            label_center_y = label_y + label_height / 2

            # Determine which edge of the element is closest to the label
            dist_top = abs(label_center_y - y)
            dist_bottom = abs(label_center_y - (y + height))
            dist_left = abs(label_center_x - x)
            dist_right = abs(label_center_x - (x + width))

            min_dist = min(dist_top, dist_bottom, dist_left, dist_right)

            if min_dist == dist_top:
                line_start = (element_center_x, y)
            elif min_dist == dist_bottom:
                line_start = (element_center_x, y + height)
            elif min_dist == dist_left:
                line_start = (x, element_center_y)
            else:
                line_start = (x + width, element_center_y)

            # Draw connecting line from element edge to label
            draw.line(
                [line_start, (label_center_x, label_center_y)],
                fill=neon_green,
                width=2,
            )

            # Draw label background (white with neon green border)
            label_bg_x1 = label_x - 4
            label_bg_y1 = label_y - 2
            label_bg_x2 = label_x + label_width + 4
            label_bg_y2 = label_y + label_height + 2

            draw.rectangle(
                [(label_bg_x1, label_bg_y1), (label_bg_x2, label_bg_y2)],
                fill="white",
                outline=neon_green,
                width=2,
            )

            # Draw label text
            draw.text(
                (label_x, label_y),
                label_text,
                fill="black",
                font=font,
            )

            # Record label position for collision detection
            existing_labels.append(
                {
                    "x": label_bg_x1,
                    "y": label_bg_y1,
                    "width": label_bg_x2 - label_bg_x1,
                    "height": label_bg_y2 - label_bg_y1,
                }
            )

        return img

    def _encode_image_to_base64(
        self,
        image: "PILImage.Image",
        format: str = "PNG",
        max_size_mb: float = 20.0,
    ) -> str:
        """
        Encode PIL Image to base64 data URL with size optimization.

        Args:
            image: PIL Image object
            format: Output format ("PNG" or "JPEG")
            max_size_mb: Maximum size in MB (will compress if exceeded)

        Returns:
            Base64-encoded data URL
        """
        buffer = io.BytesIO()
        pil_format = format.upper()
        quality = 95  # Start with high quality

        # Convert RGBA to RGB for JPEG
        if pil_format == "JPEG" and image.mode == "RGBA":
            # Create white background
            rgb_image = Image.new("RGB", image.size, (255, 255, 255))
            rgb_image.paste(image, mask=image.split()[3])  # Use alpha channel as mask
            image = rgb_image

        # Try to fit within size limit
        for attempt in range(3):
            buffer.seek(0)
            buffer.truncate(0)

            if pil_format == "JPEG":
                image.save(buffer, format=pil_format, quality=quality, optimize=True)
            else:
                image.save(buffer, format=pil_format, optimize=True)

            size_mb = len(buffer.getvalue()) / (1024 * 1024)

            if size_mb <= max_size_mb:
                break

            # Reduce quality for next attempt
            quality = max(70, quality - 15)
            if self.verbose and attempt == 0:
                print(f"   ⚠️  Image size {size_mb:.2f}MB exceeds limit, compressing...")

        image_bytes = buffer.getvalue()
        base64_data = base64.b64encode(image_bytes).decode("utf-8")

        final_size_mb = len(image_bytes) / (1024 * 1024)
        if self.verbose:
            print(f"   📸 Image encoded: {final_size_mb:.2f}MB ({len(base64_data)} chars base64)")

        mime_type = "image/png" if pil_format == "PNG" else "image/jpeg"
        return f"data:{mime_type};base64,{base64_data}"

    def _query_llm_with_vision(
        self,
        image_data_url: str,
        goal: str,
    ) -> LLMResponse:
        """
        Query LLM with vision (labeled screenshot) - sync version.

        Args:
            image_data_url: Base64-encoded image data URL
            goal: User's goal/task

        Returns:
            LLMResponse with element ID
        """
        # Use the same prompt as async version
        system_prompt = """You are a web automation assistant. You will see a screenshot of a web page with labeled element IDs.
Each clickable element has:
- A bright neon green (#39FF14) bounding box around the element
- A white label box with a number (the element ID) connected by a green line
- The label is clearly separate from the element (not part of the UI)

CRITICAL INSTRUCTIONS:
1. Look at the screenshot carefully
2. Find the element that matches the user's goal (ignore the white label boxes - they are annotations, not UI elements)
3. Follow the green line from that element to find its label box with the ID number
4. Respond with ONLY that integer ID number (e.g., "42" or "1567")
5. Do NOT include any explanation, reasoning, or other text
6. Do NOT say "element 1" or "the first element" - just return the number
7. Do NOT confuse the white label box with an interactive element - labels are annotations connected by green lines

Example responses:
- Correct: "42"
- Correct: "1567"
- Wrong: "I see element 42"
- Wrong: "The element ID is 42"
- Wrong: "42 (the search box)" """

        user_prompt = f"""Goal: {goal}

Look at the screenshot. Each element has a neon green bounding box with a white label showing its ID number.
Find the element that should be clicked to accomplish this goal.
Return ONLY the integer ID number from the label, nothing else."""

        # Check if LLM provider supports vision (OpenAI GPT-4o, Claude, etc.)
        if hasattr(self.llm, "client") and hasattr(self.llm.client, "chat"):
            # Vision-capable provider - use vision API
            try:
                from openai import OpenAI

                # Check if it's OpenAI
                if isinstance(self.llm.client, OpenAI):
                    messages = [
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_data_url},
                                },
                            ],
                        },
                    ]

                    response = self.llm.client.chat.completions.create(
                        model=self.llm._model_name,
                        messages=messages,
                        temperature=0.0,
                    )

                    content = response.choices[0].message.content or ""
                    usage = response.usage

                    from .llm_response_builder import LLMResponseBuilder

                    return LLMResponseBuilder.from_openai_format(
                        content=content,
                        prompt_tokens=usage.prompt_tokens if usage else None,
                        completion_tokens=usage.completion_tokens if usage else None,
                        total_tokens=usage.total_tokens if usage else None,
                        model_name=response.model,
                        finish_reason=response.choices[0].finish_reason,
                    )

                # Check if provider supports vision API (uses OpenAI-compatible format)
                elif hasattr(self.llm, "client") and hasattr(self.llm.client, "chat"):
                    if self.verbose:
                        print(f"   🔍 Using vision API with model: {self.llm._model_name}")
                        print(f"   📐 Image data URL length: {len(image_data_url)} chars")

                    messages = [
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_data_url},
                                },
                            ],
                        },
                    ]

                    try:
                        if self.verbose:
                            print(f"   📤 Sending request to vision API...")

                        response = self.llm.client.chat.completions.create(
                            model=self.llm._model_name,
                            messages=messages,
                            temperature=0.0,
                        )

                        if not hasattr(response, "choices") or len(response.choices) == 0:
                            raise ValueError("Vision API returned no choices in response")

                        choice = response.choices[0]
                        content = (
                            choice.message.content if hasattr(choice.message, "content") else None
                        )
                        finish_reason = (
                            choice.finish_reason if hasattr(choice, "finish_reason") else None
                        )

                        if content is None or content == "":
                            error_msg = f"Vision API returned empty content (finish_reason: {finish_reason})"
                            if self.verbose:
                                print(f"   ❌ {error_msg}")
                            raise ValueError(error_msg)

                        usage = response.usage if hasattr(response, "usage") else None

                        from .llm_response_builder import LLMResponseBuilder

                        return LLMResponseBuilder.from_openai_format(
                            content=content,
                            prompt_tokens=usage.prompt_tokens if usage else None,
                            completion_tokens=usage.completion_tokens if usage else None,
                            total_tokens=usage.total_tokens if usage else None,
                            model_name=(
                                response.model
                                if hasattr(response, "model")
                                else self.llm._model_name
                            ),
                            finish_reason=finish_reason,
                        )
                    except Exception as vision_error:
                        if self.verbose:
                            print(f"   ❌ Vision API error: {vision_error}")
                            print(f"   🔄 Attempting fallback to regular generate method...")

                        # Fallback: Try using the regular generate method
                        try:
                            fallback_prompt = f"{user_prompt}\n\n[Image: {image_data_url[:200]}...]"
                            fallback_response = self.llm.generate(
                                system_prompt,
                                fallback_prompt,
                                temperature=0.0,
                            )
                            if self.verbose:
                                print(f"   ⚠️  Using fallback method (may not support vision)")
                            return fallback_response
                        except Exception as fallback_error:
                            if self.verbose:
                                print(f"   ❌ Fallback also failed: {fallback_error}")
                            raise vision_error  # Raise original error
            except ImportError:
                # openai or other vision SDK not available
                pass
            except Exception as e:
                if self.verbose:
                    print(f"⚠️  Vision API error: {e}, falling back to text-only")

        # Fallback: Try to pass image via kwargs or use text-only
        try:
            return self.llm.generate(
                system_prompt,
                f"{user_prompt}\n\n[Image data: {image_data_url[:100]}...]",
                temperature=0.0,
            )
        except Exception as e:
            raise RuntimeError(
                f"LLM provider {type(self.llm).__name__} may not support vision. "
                f"Error: {e}. Use a vision-capable model like GPT-4o or Claude 3."
            ) from e

    def _extract_element_id(self, llm_response: str) -> int | None:
        """Extract element ID integer from LLM response (shared with async version)."""
        return SentienceVisualAgentAsync._extract_element_id(self, llm_response)

    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def act(
        self,
        goal: str,
        max_retries: int = 2,
        snapshot_options: SnapshotOptions | None = None,
    ) -> AgentActionResult:
        """
        Override act() method to use visual prompting with full tracing support.

        Args:
            goal: User's goal/task
            max_retries: Maximum retry attempts
            snapshot_options: Optional snapshot options (screenshot will be enabled)

        Returns:
            AgentActionResult
        """
        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"🤖 Visual Agent Goal: {goal}")
            print(f"{'=' * 70}")

        # Generate step ID for tracing
        self._step_count += 1
        step_id = f"step-{self._step_count}"

        # Emit step_start trace event if tracer is enabled
        if self.tracer:
            pre_url = self.browser.page.url if self.browser.page else None
            _safe_tracer_call(
                self.tracer,
                "emit_step_start",
                self.verbose,
                step_id=step_id,
                step_index=self._step_count,
                goal=goal,
                attempt=0,
                pre_url=pre_url,
            )

        start_time = time.time()

        try:
            # Ensure screenshot is enabled
            if snapshot_options is None:
                snapshot_options = SnapshotOptions()

            # Enable screenshot if not already enabled
            if snapshot_options.screenshot is False or snapshot_options.screenshot is None:
                from .models import ScreenshotConfig

                snapshot_options.screenshot = ScreenshotConfig(format="png")

            # Set goal if not already provided
            if snapshot_options.goal is None:
                snapshot_options.goal = goal

            # Set limit if not provided
            if snapshot_options.limit is None:
                snapshot_options.limit = self.default_snapshot_limit

            if self.verbose:
                print(f"🎯 Goal: {goal}")
                print("📸 Taking snapshot with screenshot...")

            # 1. Take snapshot with screenshot (sync version)
            snap = snapshot(self.browser, snapshot_options)

            if snap.status != "success":
                raise RuntimeError(f"Snapshot failed: {snap.error}")

            if not snap.screenshot:
                raise RuntimeError("Screenshot not available in snapshot")

            # Compute diff_status by comparing with previous snapshot
            elements_with_diff = SnapshotDiff.compute_diff_status(snap, self._previous_snapshot)

            # Create snapshot with diff_status populated
            snap_with_diff = Snapshot(
                status=snap.status,
                timestamp=snap.timestamp,
                url=snap.url,
                viewport=snap.viewport,
                elements=elements_with_diff,
                screenshot=snap.screenshot,
                screenshot_format=snap.screenshot_format,
                error=snap.error,
            )

            # Update previous snapshot for next comparison
            self._previous_snapshot = snap

            # Emit snapshot trace event if tracer is enabled
            if self.tracer:
                # Build snapshot event data (use snap_with_diff to include diff_status)
                snapshot_data = TraceEventBuilder.build_snapshot_event(snap_with_diff)

                # Always include screenshot in trace event for studio viewer compatibility
                if snap.screenshot:
                    # Extract base64 string from data URL if needed
                    if snap.screenshot.startswith("data:image"):
                        # Format: "data:image/jpeg;base64,{base64_string}"
                        screenshot_base64 = (
                            snap.screenshot.split(",", 1)[1]
                            if "," in snap.screenshot
                            else snap.screenshot
                        )
                    else:
                        screenshot_base64 = snap.screenshot

                    snapshot_data["screenshot_base64"] = screenshot_base64
                    if snap.screenshot_format:
                        snapshot_data["screenshot_format"] = snap.screenshot_format

                _safe_tracer_call(
                    self.tracer,
                    "emit",
                    self.verbose,
                    "snapshot",
                    snapshot_data,
                    step_id=step_id,
                )

            if self.verbose:
                print(f"✅ Snapshot taken: {len(snap.elements)} elements")

            # 2. Draw labeled screenshot
            if self.verbose:
                print("🎨 Drawing bounding boxes and labels...")
                print(f"   Elements to label: {len(snap.elements)}")
                if len(snap.elements) > 0:
                    element_ids = [el.id for el in snap.elements[:10]]  # Show first 10
                    print(f"   Sample element IDs: {element_ids}")

            labeled_image = self._draw_labeled_screenshot(snap, snap.elements)

            # Save labeled image to disk for debugging
            # Save to playground/images if running from playground, otherwise use current directory
            try:
                # Try to detect if we're in a playground context
                import sys

                cwd = Path.cwd()
                playground_path = None

                # Check if current working directory contains playground
                if (cwd / "playground").exists():
                    playground_path = cwd / "playground" / "images"
                else:
                    # Check sys.path for playground
                    for path_str in sys.path:
                        path_obj = Path(path_str)
                        if "playground" in str(path_obj) and path_obj.exists():
                            # Find the playground directory
                            if path_obj.name == "playground":
                                playground_path = path_obj / "images"
                                break
                            elif (path_obj / "playground").exists():
                                playground_path = path_obj / "playground" / "images"
                                break

                if playground_path is None:
                    # Fallback: use current working directory
                    playground_path = cwd / "playground" / "images"

                images_dir = playground_path
                images_dir.mkdir(parents=True, exist_ok=True)
                image_uuid = str(uuid.uuid4())
                image_filename = f"labeled_screenshot_{image_uuid}.png"
                image_path = images_dir / image_filename
                labeled_image.save(image_path, format="PNG")
                if self.verbose:
                    print(f"   💾 Saved labeled screenshot: {image_path.absolute()}")
            except Exception as save_error:
                # Don't fail if image save fails - it's just for debugging
                if self.verbose:
                    print(f"   ⚠️  Could not save labeled screenshot: {save_error}")

            # Use JPEG for better compression (smaller file size for vision APIs)
            labeled_image_data_url = self._encode_image_to_base64(
                labeled_image, format="JPEG", max_size_mb=20.0
            )

            # 3. Query LLM with vision (sync version)
            if self.verbose:
                print("🧠 Querying LLM with labeled screenshot...")

            llm_response = self._query_llm_with_vision(labeled_image_data_url, goal)

            # Emit LLM query trace event if tracer is enabled
            if self.tracer:
                _safe_tracer_call(
                    self.tracer,
                    "emit",
                    self.verbose,
                    "llm_query",
                    {
                        "prompt_tokens": llm_response.prompt_tokens,
                        "completion_tokens": llm_response.completion_tokens,
                        "model": llm_response.model_name,
                        "response": llm_response.content[:200],  # Truncate for brevity
                    },
                    step_id=step_id,
                )

            if self.verbose:
                print(f"💭 LLM Response: {llm_response.content}")

            # Track token usage
            self._track_tokens(goal, llm_response)

            # 4. Extract element ID
            element_id = self._extract_element_id(llm_response.content)

            if element_id is None:
                raise ValueError(
                    f"Could not extract element ID from LLM response: {llm_response.content}"
                )

            if self.verbose:
                print(f"🎯 Extracted Element ID: {element_id}")

            # 5. Click the element (sync version)
            if self.verbose:
                print(f"🖱️  Clicking element {element_id}...")

            click_result = click(self.browser, element_id)

            duration_ms = int((time.time() - start_time) * 1000)

            # Create AgentActionResult from click result
            result = AgentActionResult(
                success=click_result.success,
                action="click",
                goal=goal,
                duration_ms=duration_ms,
                attempt=0,
                element_id=element_id,
                outcome=click_result.outcome,
                url_changed=click_result.url_changed,
                error=click_result.error,
            )

            # Emit action execution trace event if tracer is enabled
            if self.tracer:
                post_url = self.browser.page.url if self.browser.page else None

                # Include element data for live overlay visualization
                elements_data = [
                    {
                        "id": el.id,
                        "bbox": {
                            "x": el.bbox.x,
                            "y": el.bbox.y,
                            "width": el.bbox.width,
                            "height": el.bbox.height,
                        },
                        "role": el.role,
                        "text": el.text[:50] if el.text else "",
                    }
                    for el in snap.elements[:50]
                ]

                _safe_tracer_call(
                    self.tracer,
                    "emit",
                    self.verbose,
                    "action",
                    {
                        "action": result.action,
                        "element_id": result.element_id,
                        "success": result.success,
                        "outcome": result.outcome,
                        "duration_ms": duration_ms,
                        "post_url": post_url,
                        "elements": elements_data,  # Add element data for overlay
                        "target_element_id": result.element_id,  # Highlight target in red
                    },
                    step_id=step_id,
                )

            # Record history
            self.history.append(
                {
                    "goal": goal,
                    "action": f"CLICK({element_id})",
                    "result": result.model_dump(),  # Store as dict
                    "success": result.success,
                    "attempt": 0,
                    "duration_ms": duration_ms,
                }
            )

            if self.verbose:
                status = "✅" if result.success else "❌"
                print(f"{status} Completed in {duration_ms}ms")

            # Emit step completion trace event if tracer is enabled
            if self.tracer:
                # Get pre_url from step_start (stored in tracer or use current)
                pre_url = snap.url
                post_url = self.browser.page.url if self.browser.page else None

                # Compute snapshot digest (simplified - use URL + timestamp)
                snapshot_digest = f"sha256:{self._compute_hash(f'{pre_url}{snap.timestamp}')}"

                # Build LLM data
                llm_response_text = llm_response.content

                # Build execution data
                exec_data = {
                    "success": result.success,
                    "outcome": result.outcome,
                    "action": result.action,
                    "element_id": result.element_id,
                    "url_changed": result.url_changed,
                    "duration_ms": duration_ms,
                }

                # Build verification data (simplified - always pass for now)
                verify_data = {
                    "passed": result.success,
                    "signals": {
                        "url_changed": result.url_changed or False,
                    },
                }

                post_snapshot_digest = (
                    self._best_effort_post_snapshot_digest(goal) if self.tracer else None
                )

                # Build complete step_end event
                step_end_data = TraceEventBuilder.build_step_end_event(
                    step_id=step_id,
                    step_index=self._step_count,
                    goal=goal,
                    attempt=0,
                    pre_url=pre_url,
                    post_url=post_url or pre_url,
                    snapshot_digest=snapshot_digest,
                    post_snapshot_digest=post_snapshot_digest,
                    llm_data={
                        "response_text": llm_response_text,
                        "response_hash": f"sha256:{self._compute_hash(llm_response_text)}",
                    },
                    exec_data=exec_data,
                    verify_data=verify_data,
                )

                _safe_tracer_call(
                    self.tracer,
                    "emit",
                    self.verbose,
                    "step_end",
                    step_end_data,
                    step_id=step_id,
                )

            return result

        except Exception as e:
            # Emit error trace event if tracer is enabled
            if self.tracer:
                _safe_tracer_call(
                    self.tracer,
                    "emit_error",
                    self.verbose,
                    step_id=step_id,
                    error=str(e),
                    attempt=0,
                )

            if self.verbose:
                print(f"❌ Error: {e}")

            # Re-raise the exception
            raise
