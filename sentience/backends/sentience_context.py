"""
SentienceContext: Token-Slasher Context Middleware for browser-use.

This module provides a compact, ranked DOM context block for browser-use agents,
reducing tokens and improving reliability by using Sentience snapshots.

Example usage:
    from browser_use import Agent
    from sentience.backends import SentienceContext

    ctx = SentienceContext(show_overlay=True)
    state = await ctx.build(agent.browser_session, goal="Click the first Show HN post")
    if state:
        agent.add_context(state.prompt_block)  # or however browser-use injects state
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ..models import Element, Snapshot

logger = logging.getLogger(__name__)


@dataclass
class SentienceContextState:
    """Sentience context state with snapshot and formatted prompt block."""

    url: str
    snapshot: "Snapshot"
    prompt_block: str


class SentienceContext:
    """
    Token-Slasher Context Middleware for browser-use.

    Creates a compact, ranked DOM context block using Sentience snapshots,
    reducing tokens and improving reliability for LLM-based browser agents.

    Example:
        from browser_use import Agent
        from sentience.backends import SentienceContext

        ctx = SentienceContext(show_overlay=True)
        state = await ctx.build(agent.browser_session, goal="Click the first Show HN post")
        if state:
            agent.add_context(state.prompt_block)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        use_api: bool | None = None,
        limit: int = 60,
        show_overlay: bool = False,
        top_by_importance: int = 60,
        top_from_dominant_group: int = 15,
        top_by_position: int = 10,
        role_link_when_href: bool = True,
        include_rank_in_group: bool = True,
        env_api_key: str = "SENTIENCE_API_KEY",
    ) -> None:
        """
        Initialize SentienceContext.

        Args:
            api_key: Sentience API key (defaults from env var if not passed)
            api_url: Sentience API URL (defaults to production)
            use_api: Force API vs extension mode (auto-detected if None)
            limit: Maximum elements to fetch from snapshot
            show_overlay: Show visual overlay highlighting elements in browser
            top_by_importance: Number of top elements by importance to include
            top_from_dominant_group: Number of top elements from dominant group
            top_by_position: Number of top elements by position (lowest doc_y)
            role_link_when_href: If True, output role="link" for elements with href
            include_rank_in_group: If True, compute local rank_in_group for ord_val
            env_api_key: Environment variable name for API key
        """
        self._api_key = api_key or os.getenv(env_api_key)
        self._api_url = api_url
        self._use_api = use_api
        self._limit = limit
        self._show_overlay = show_overlay
        self._top_by_importance = top_by_importance
        self._top_from_dominant_group = top_from_dominant_group
        self._top_by_position = top_by_position
        self._role_link_when_href = role_link_when_href
        self._include_rank_in_group = include_rank_in_group

    async def build(
        self,
        browser_session: Any,
        *,
        goal: str | None = None,
        wait_for_extension_ms: int = 5000,
        retries: int = 2,
        retry_delay_s: float = 1.0,
    ) -> SentienceContextState | None:
        """
        Build context state from browser session.

        Takes a snapshot using the Sentience extension and formats it for LLM consumption.
        Returns None if snapshot fails (extension not loaded, timeout, etc.).

        Args:
            browser_session: Browser-use BrowserSession instance
            goal: Optional goal/task description (passed to gateway for reranking)
            wait_for_extension_ms: Maximum time to wait for extension injection
            retries: Number of retry attempts on snapshot failure
            retry_delay_s: Delay between retries in seconds

        Returns:
            SentienceContextState with snapshot and formatted prompt, or None if failed
        """
        try:
            # Import here to avoid requiring sentience as a hard dependency
            from .browser_use_adapter import BrowserUseAdapter
            from .snapshot import snapshot
            from ..models import SnapshotOptions

            # Create adapter and backend
            adapter = BrowserUseAdapter(browser_session)
            backend = await adapter.create_backend()

            # Give extension a moment to inject (especially after navigation)
            await asyncio.sleep(0.5)

            # Build snapshot options
            options = SnapshotOptions(
                limit=self._limit,
                show_overlay=self._show_overlay,
                goal=goal,
            )

            # Set API options
            if self._api_key:
                options.sentience_api_key = self._api_key
            if self._use_api is not None:
                options.use_api = self._use_api
            elif self._api_key:
                options.use_api = True

            # Take snapshot with retry logic
            snap = None
            last_error: Exception | None = None

            for attempt in range(retries):
                try:
                    snap = await snapshot(backend, options=options)
                    break  # Success
                except Exception as e:
                    last_error = e
                    if attempt < retries - 1:
                        logger.debug(
                            "Sentience snapshot attempt %d failed: %s, retrying...",
                            attempt + 1,
                            e,
                        )
                        await asyncio.sleep(retry_delay_s)
                    else:
                        logger.warning(
                            "Sentience snapshot failed after %d attempts: %s",
                            retries,
                            last_error,
                        )
                        return None

            if snap is None:
                logger.warning("Sentience snapshot returned None")
                return None

            # Get URL from snapshot
            url = snap.url or ""

            # Format for LLM
            formatted = self._format_snapshot_for_llm(snap)

            # Build prompt block
            prompt = (
                "Elements: ID|role|text|imp|docYq|ord|DG|href\n"
                "Rules: ordinal→DG=1 then ord asc; otherwise imp desc. "
                "Use click(ID)/input_text(ID,...).\n"
                f"{formatted}"
            )

            logger.info(
                "SentienceContext snapshot: %d elements URL=%s",
                len(snap.elements),
                url,
            )

            return SentienceContextState(url=url, snapshot=snap, prompt_block=prompt)

        except ImportError as e:
            logger.warning("Sentience SDK not available: %s", e)
            return None
        except Exception as e:
            logger.warning("Sentience snapshot skipped: %s", e)
            return None

    def _format_snapshot_for_llm(self, snapshot: "Snapshot") -> str:
        """
        Format Sentience snapshot for LLM consumption.

        Creates an ultra-compact inventory of interactive elements optimized
        for minimal token usage. Uses 3-way selection: by importance,
        from dominant group, and by position.

        Args:
            snapshot: Sentience Snapshot object

        Returns:
            Formatted string with format: ID|role|text|imp|docYq|ord|DG|href
        """
        # Filter to interactive elements only
        interactive_roles = {
            "button",
            "link",
            "textbox",
            "searchbox",
            "combobox",
            "checkbox",
            "radio",
            "slider",
            "tab",
            "menuitem",
            "option",
            "switch",
            "cell",
            "a",
            "input",
            "select",
            "textarea",
        }

        interactive_elements: list[Element] = []
        for el in snapshot.elements:
            role = (el.role or "").lower()
            if role in interactive_roles:
                interactive_elements.append(el)

        # Sort by importance (descending) for importance-based selection
        interactive_elements.sort(key=lambda el: el.importance or 0, reverse=True)

        # Get top N by importance (track by ID for deduplication)
        selected_ids: set[int] = set()
        selected_elements: list[Element] = []

        for el in interactive_elements[: self._top_by_importance]:
            if el.id not in selected_ids:
                selected_ids.add(el.id)
                selected_elements.append(el)

        # Get top elements from dominant group (for ordinal tasks)
        # Prefer in_dominant_group field (uses fuzzy matching from gateway)
        dominant_group_elements = [
            el for el in interactive_elements if el.in_dominant_group is True
        ]

        # Fallback to exact group_key match if in_dominant_group not populated
        if not dominant_group_elements and snapshot.dominant_group_key:
            dominant_group_elements = [
                el for el in interactive_elements if el.group_key == snapshot.dominant_group_key
            ]

        # Sort by group_index for ordinal ordering
        dominant_group_elements.sort(key=lambda el: el.group_index or 999)

        for el in dominant_group_elements[: self._top_from_dominant_group]:
            if el.id not in selected_ids:
                selected_ids.add(el.id)
                selected_elements.append(el)

        # Get top elements by position (lowest doc_y = top of page)
        def get_y_position(el: "Element") -> float:
            if el.doc_y is not None:
                return el.doc_y
            if el.bbox is not None:
                return el.bbox.y
            return float("inf")

        elements_by_position = sorted(
            interactive_elements, key=lambda el: (get_y_position(el), -(el.importance or 0))
        )

        for el in elements_by_position[: self._top_by_position]:
            if el.id not in selected_ids:
                selected_ids.add(el.id)
                selected_elements.append(el)

        # Compute local rank_in_group if enabled
        rank_in_group_map: dict[int, int] = {}
        if self._include_rank_in_group:
            # Sort dominant group elements by position for rank computation
            dg_elements_for_rank = [
                el for el in interactive_elements if el.in_dominant_group is True
            ]
            if not dg_elements_for_rank and snapshot.dominant_group_key:
                dg_elements_for_rank = [
                    el for el in interactive_elements if el.group_key == snapshot.dominant_group_key
                ]

            # Sort by (doc_y, bbox.y, bbox.x, -importance)
            def rank_sort_key(el: "Element") -> tuple[float, float, float, float]:
                doc_y = el.doc_y if el.doc_y is not None else float("inf")
                bbox_y = el.bbox.y if el.bbox else float("inf")
                bbox_x = el.bbox.x if el.bbox else float("inf")
                neg_importance = -(el.importance or 0)
                return (doc_y, bbox_y, bbox_x, neg_importance)

            dg_elements_for_rank.sort(key=rank_sort_key)
            for rank, el in enumerate(dg_elements_for_rank):
                rank_in_group_map[el.id] = rank

        # Format lines
        lines: list[str] = []
        for el in selected_elements:
            # Get role (with link-when-href optimization)
            role = el.role or ""
            if self._role_link_when_href and el.href:
                role = "link"

            # Get name/text (truncate aggressively)
            name = (el.text or "").strip()
            if len(name) > 30:
                name = name[:27] + "..."

            # Extract fields
            importance = el.importance or 0
            doc_y = el.doc_y or 0

            # Pre-encode fields for compactness
            # docYq: bucketed doc_y (round to nearest 200 for smaller numbers)
            doc_yq = int(round(doc_y / 200)) if doc_y else 0

            # Determine if in dominant group
            in_dg = el.in_dominant_group
            if in_dg is None and snapshot.dominant_group_key:
                # Fallback for older gateway versions
                in_dg = el.group_key == snapshot.dominant_group_key

            # ord_val: rank_in_group if in dominant group (and include_rank_in_group enabled)
            if in_dg and self._include_rank_in_group and el.id in rank_in_group_map:
                ord_val: str | int = rank_in_group_map[el.id]
            else:
                ord_val = "-"

            # DG: 1 if dominant group, else 0
            dg_flag = "1" if in_dg else "0"

            # href: short token (domain or last path segment, or blank)
            href = self._compress_href(el.href)

            # Ultra-compact format: ID|role|text|imp|docYq|ord|DG|href
            line = f"{el.id}|{role}|{name}|{importance}|{doc_yq}|{ord_val}|{dg_flag}|{href}"
            lines.append(line)

        logger.debug(
            "Formatted %d elements (top %d by importance + top %d from dominant group + top %d by position)",
            len(lines),
            self._top_by_importance,
            self._top_from_dominant_group,
            self._top_by_position,
        )

        return "\n".join(lines)

    def _compress_href(self, href: str | None) -> str:
        """
        Compress href into a short token for minimal tokens.

        Args:
            href: Full URL or None

        Returns:
            Short token (domain second-level or last path segment)
        """
        if not href:
            return ""

        try:
            parsed = urlparse(href)
            if parsed.netloc:
                # Extract second-level domain (e.g., "github" from "github.com")
                parts = parsed.netloc.split(".")
                if len(parts) >= 2:
                    return parts[-2][:10]
                return parsed.netloc[:10]
            elif parsed.path:
                # Use last path segment
                segments = [s for s in parsed.path.split("/") if s]
                if segments:
                    return segments[-1][:10]
                return "item"
        except Exception:
            pass

        return "item"
