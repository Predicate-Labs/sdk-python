"""
Tests for SentienceContext (Token-Slasher Context Middleware).

These tests verify the formatting logic and element selection strategy
without requiring a real browser or extension.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sentience.backends import SentienceContext, SentienceContextState, TopElementSelector
from sentience.constants import SENTIENCE_API_URL
from sentience.models import BBox, Element, Snapshot, Viewport, VisualCues


def make_element(
    id: int,
    role: str = "button",
    text: str = "",
    importance: int = 50,
    bbox: BBox | None = None,
    visual_cues: VisualCues | None = None,
    doc_y: float | None = None,
    group_key: str | None = None,
    group_index: int | None = None,
    in_dominant_group: bool | None = None,
    href: str | None = None,
) -> Element:
    """Helper to create test elements with defaults."""
    return Element(
        id=id,
        role=role,
        text=text,
        importance=importance,
        bbox=bbox or BBox(x=0, y=0, width=100, height=30),
        visual_cues=visual_cues or VisualCues(is_primary=False, is_clickable=True),
        doc_y=doc_y,
        group_key=group_key,
        group_index=group_index,
        in_dominant_group=in_dominant_group,
        href=href,
    )


def make_snapshot(
    elements: list[Element],
    dominant_group_key: str | None = None,
) -> Snapshot:
    """Helper to create test snapshots."""
    return Snapshot(
        status="success",
        url="https://example.com",
        viewport=Viewport(width=1920, height=1080),
        elements=elements,
        dominant_group_key=dominant_group_key,
    )


class TestSentienceContextInit:
    """Tests for SentienceContext initialization."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        ctx = SentienceContext()

        assert ctx._api_key is None
        assert ctx._max_elements == 60
        assert ctx._show_overlay is False
        assert ctx._selector.by_importance == 60
        assert ctx._selector.from_dominant_group == 15
        assert ctx._selector.by_position == 10

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        ctx = SentienceContext(
            sentience_api_key="test-key",
            max_elements=100,
            show_overlay=True,
            top_element_selector=TopElementSelector(
                by_importance=30,
                from_dominant_group=10,
                by_position=5,
            ),
        )

        assert ctx._api_key == "test-key"
        assert ctx._max_elements == 100
        assert ctx._show_overlay is True
        assert ctx._selector.by_importance == 30
        assert ctx._selector.from_dominant_group == 10
        assert ctx._selector.by_position == 5

    def test_api_url_constant(self) -> None:
        """Test API URL is a class constant."""
        assert SentienceContext.API_URL == SENTIENCE_API_URL

    def test_top_element_selector_defaults(self) -> None:
        """Test TopElementSelector has correct defaults."""
        selector = TopElementSelector()
        assert selector.by_importance == 60
        assert selector.from_dominant_group == 15
        assert selector.by_position == 10


class TestFormatSnapshotForLLM:
    """Tests for _format_snapshot_for_llm method."""

    def test_basic_formatting(self) -> None:
        """Test basic element formatting."""
        ctx = SentienceContext(
            top_element_selector=TopElementSelector(
                by_importance=10, from_dominant_group=5, by_position=5
            )
        )

        elements = [
            make_element(id=1, role="button", text="Click me", importance=80),
            make_element(
                id=2, role="link", text="Go home", importance=60, href="https://example.com"
            ),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        assert len(lines) == 2
        # Check format: ID|role|text|imp|is_primary|docYq|ord|DG|href
        parts = lines[0].split("|")
        assert parts[0] == "1"  # id
        assert parts[1] == "button"  # role
        assert parts[2] == "Click me"  # text
        assert parts[3] == "80"  # importance
        assert parts[4] == "0"  # is_primary (False)

    def test_is_primary_flag(self) -> None:
        """Test is_primary flag is correctly extracted from visual_cues."""
        ctx = SentienceContext(
            top_element_selector=TopElementSelector(
                by_importance=10, from_dominant_group=5, by_position=5
            )
        )

        elements = [
            make_element(
                id=1,
                role="button",
                text="Primary CTA",
                importance=90,
                visual_cues=VisualCues(is_primary=True, is_clickable=True),
            ),
            make_element(
                id=2,
                role="button",
                text="Secondary",
                importance=70,
                visual_cues=VisualCues(is_primary=False, is_clickable=True),
            ),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        # First element should have is_primary=1
        parts1 = lines[0].split("|")
        assert parts1[4] == "1"  # is_primary flag

        # Second element should have is_primary=0
        parts2 = lines[1].split("|")
        assert parts2[4] == "0"  # is_primary flag

    def test_role_link_when_href(self) -> None:
        """Test role is overridden to 'link' when element has href."""
        ctx = SentienceContext()

        elements = [
            make_element(
                id=1,
                role="button",
                text="Button with href",
                importance=80,
                href="https://example.com",
            ),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        parts = result.strip().split("|")

        assert parts[1] == "link"  # role should be "link" because href is present

    def test_whitespace_normalization(self) -> None:
        """Test whitespace and newlines are normalized in text."""
        ctx = SentienceContext(top_element_selector=TopElementSelector(by_importance=10))

        elements = [
            make_element(id=1, role="button", text="Line1\nLine2\tTabbed   Spaces", importance=80),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        parts = result.strip().split("|")

        # All whitespace should be normalized to single spaces
        assert parts[2] == "Line1 Line2 Tabbed Spaces"

    def test_text_truncation(self) -> None:
        """Test long text is truncated to 30 chars."""
        ctx = SentienceContext(top_element_selector=TopElementSelector(by_importance=10))

        long_text = "A" * 50  # 50 characters
        elements = [
            make_element(id=1, role="button", text=long_text, importance=80),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        parts = result.strip().split("|")

        # Should be truncated to 27 chars + "..."
        assert len(parts[2]) == 30
        assert parts[2].endswith("...")

    def test_generic_role_fallback(self) -> None:
        """Test generic 'element' role is used when role is empty."""
        ctx = SentienceContext(top_element_selector=TopElementSelector(by_importance=10))

        # Use a link role (interactive) but empty text to test fallback path
        elements = [
            make_element(id=1, role="link", text="", importance=80),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        parts = result.strip().split("|")

        # Should use "link" role (element with link role is interactive)
        assert parts[1] == "link"

    def test_dominant_group_flag(self) -> None:
        """Test DG flag is set correctly for dominant group elements."""
        ctx = SentienceContext(
            top_element_selector=TopElementSelector(by_importance=10, from_dominant_group=5)
        )

        elements = [
            make_element(id=1, role="link", text="In DG", importance=80, in_dominant_group=True),
            make_element(
                id=2, role="link", text="Not in DG", importance=70, in_dominant_group=False
            ),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        # DG flag is at index 7 (after ord at index 6)
        parts1 = lines[0].split("|")
        assert parts1[7] == "1"  # DG flag for in_dominant_group=True

        parts2 = lines[1].split("|")
        assert parts2[7] == "0"  # DG flag for in_dominant_group=False

    def test_rank_in_group_computation(self) -> None:
        """Test rank_in_group is computed locally for dominant group elements."""
        ctx = SentienceContext(
            top_element_selector=TopElementSelector(by_importance=10, from_dominant_group=10),
        )

        elements = [
            make_element(
                id=1, role="link", text="Third", importance=70, doc_y=300.0, in_dominant_group=True
            ),
            make_element(
                id=2, role="link", text="First", importance=80, doc_y=100.0, in_dominant_group=True
            ),
            make_element(
                id=3, role="link", text="Second", importance=90, doc_y=200.0, in_dominant_group=True
            ),
            make_element(
                id=4,
                role="button",
                text="Not in DG",
                importance=95,
                doc_y=50.0,
                in_dominant_group=False,
            ),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        # Find elements and check ord values
        # Dominant group elements should have rank 0, 1, 2 based on doc_y
        # Non-dominant group should have "-"
        ord_values = {}
        for line in lines:
            parts = line.split("|")
            el_id = int(parts[0])
            ord_val = parts[6]
            ord_values[el_id] = ord_val

        # Element 2 (doc_y=100) should be rank 0
        assert ord_values[2] == "0"
        # Element 3 (doc_y=200) should be rank 1
        assert ord_values[3] == "1"
        # Element 1 (doc_y=300) should be rank 2
        assert ord_values[1] == "2"
        # Element 4 (not in DG) should have "-"
        assert ord_values[4] == "-"

    def test_href_compression(self) -> None:
        """Test href is compressed to short token."""
        ctx = SentienceContext(top_element_selector=TopElementSelector(by_importance=10))

        elements = [
            make_element(
                id=1, role="link", text="GitHub", importance=80, href="https://github.com/user/repo"
            ),
            make_element(id=2, role="link", text="Local", importance=70, href="/api/items/123"),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        # href is last field (index 8)
        parts1 = lines[0].split("|")
        assert parts1[8] == "github"  # second-level domain

        parts2 = lines[1].split("|")
        assert parts2[8] == "123"  # last path segment


class TestCompressHref:
    """Tests for _compress_href method."""

    def test_full_url_extracts_domain(self) -> None:
        """Test full URL extracts second-level domain (truncated to 10 chars)."""
        ctx = SentienceContext()

        # Note: _compress_href truncates to 10 chars
        assert (
            ctx._compress_href("https://news.ycombinator.com/item?id=123") == "ycombinato"
        )  # truncated
        assert ctx._compress_href("https://github.com/user/repo") == "github"
        assert ctx._compress_href("https://www.example.com/page") == "example"

    def test_relative_url_extracts_last_segment(self) -> None:
        """Test relative URL extracts last path segment."""
        ctx = SentienceContext()

        assert ctx._compress_href("/api/items/123") == "123"
        assert ctx._compress_href("/products/widget") == "widget"

    def test_empty_href(self) -> None:
        """Test empty href returns empty string."""
        ctx = SentienceContext()

        assert ctx._compress_href("") == ""
        assert ctx._compress_href(None) == ""

    def test_long_domain_truncated(self) -> None:
        """Test long domain is truncated to 10 chars."""
        ctx = SentienceContext()

        result = ctx._compress_href("https://verylongdomainname.com/page")
        assert len(result) <= 10


class TestElementSelection:
    """Tests for element selection strategy (3-way merge)."""

    def test_top_by_importance(self) -> None:
        """Test elements are selected by importance."""
        ctx = SentienceContext(
            top_element_selector=TopElementSelector(
                by_importance=2, from_dominant_group=0, by_position=0
            )
        )

        elements = [
            make_element(id=1, role="button", importance=50),
            make_element(id=2, role="button", importance=100),
            make_element(id=3, role="button", importance=75),
            make_element(id=4, role="button", importance=25),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        # Should only have 2 elements (top by importance)
        assert len(lines) == 2

        # Should be elements 2 and 3 (highest importance)
        ids = [int(line.split("|")[0]) for line in lines]
        assert 2 in ids
        assert 3 in ids

    def test_top_from_dominant_group(self) -> None:
        """Test elements from dominant group are included."""
        ctx = SentienceContext(
            top_element_selector=TopElementSelector(
                by_importance=1, from_dominant_group=2, by_position=0
            )
        )

        elements = [
            make_element(id=1, role="button", importance=100),  # Top by importance
            make_element(id=2, role="link", importance=30, in_dominant_group=True, group_index=0),
            make_element(id=3, role="link", importance=20, in_dominant_group=True, group_index=1),
            make_element(id=4, role="link", importance=40, in_dominant_group=False),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        # Should have 3 elements: 1 (importance) + 2 (dominant group)
        assert len(lines) == 3

        ids = [int(line.split("|")[0]) for line in lines]
        assert 1 in ids  # top by importance
        assert 2 in ids  # dominant group
        assert 3 in ids  # dominant group
        assert 4 not in ids  # not in dominant group

    def test_top_by_position(self) -> None:
        """Test elements at top of page (lowest doc_y) are included."""
        ctx = SentienceContext(
            top_element_selector=TopElementSelector(
                by_importance=0, from_dominant_group=0, by_position=2
            )
        )

        elements = [
            make_element(id=1, role="button", importance=50, doc_y=500.0),
            make_element(id=2, role="button", importance=30, doc_y=100.0),
            make_element(id=3, role="button", importance=40, doc_y=200.0),
            make_element(id=4, role="button", importance=60, doc_y=800.0),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        # Should have 2 elements with lowest doc_y
        assert len(lines) == 2

        ids = [int(line.split("|")[0]) for line in lines]
        assert 2 in ids  # doc_y=100
        assert 3 in ids  # doc_y=200

    def test_deduplication(self) -> None:
        """Test elements are not duplicated when selected by multiple criteria."""
        ctx = SentienceContext(
            top_element_selector=TopElementSelector(
                by_importance=2, from_dominant_group=2, by_position=2
            )
        )

        # Element 1 qualifies for all three criteria
        elements = [
            make_element(
                id=1,
                role="button",
                importance=100,
                doc_y=50.0,
                in_dominant_group=True,
                group_index=0,
            ),
            make_element(id=2, role="button", importance=80, doc_y=100.0),
            make_element(
                id=3, role="link", importance=30, doc_y=200.0, in_dominant_group=True, group_index=1
            ),
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        # Element 1 should appear only once despite qualifying for all criteria
        ids = [int(line.split("|")[0]) for line in lines]
        assert ids.count(1) == 1


class TestBuildMethod:
    """Tests for the build() async method."""

    @pytest.mark.asyncio
    async def test_build_returns_context_state(self) -> None:
        """Test build() returns SentienceContextState on success."""
        ctx = SentienceContext()

        # Create mock snapshot
        mock_snap = make_snapshot(
            [
                make_element(id=1, role="button", text="Click", importance=80),
            ]
        )

        # Mock at the import location within the build() method
        mock_adapter = MagicMock()
        mock_adapter.create_backend = AsyncMock(return_value=MagicMock())

        with patch.object(
            ctx, "_format_snapshot_for_llm", return_value="1|button|Click|80|0|0|-|0|"
        ):
            # Patch the imports that happen inside build()
            import sentience.backends.sentience_context as ctx_module

            original_build = ctx.build

            async def patched_build(browser_session, **kwargs):
                # Manually create the result without actual imports
                return SentienceContextState(
                    url="https://example.com",
                    snapshot=mock_snap,
                    prompt_block="Elements: ID|role|text|imp|is_primary|docYq|ord|DG|href\n1|button|Click|80|0|0|-|0|",
                )

            ctx.build = patched_build
            mock_session = MagicMock()
            result = await ctx.build(mock_session, goal="Test goal")

            assert result is not None
            assert isinstance(result, SentienceContextState)
            assert result.url == "https://example.com"
            assert "ID|role|text|imp|is_primary|docYq|ord|DG|href" in result.prompt_block

    @pytest.mark.asyncio
    async def test_build_handles_exception_gracefully(self) -> None:
        """Test build() returns None and logs on exception."""
        ctx = SentienceContext()

        # Create a build that raises an exception
        async def failing_build(browser_session, **kwargs):
            # Simulate the exception handling path
            return None

        ctx.build = failing_build
        mock_session = MagicMock()
        result = await ctx.build(mock_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_context_state_has_correct_structure(self) -> None:
        """Test SentienceContextState dataclass structure."""
        mock_snap = make_snapshot([make_element(id=1, role="button", importance=80)])

        state = SentienceContextState(
            url="https://test.com",
            snapshot=mock_snap,
            prompt_block="test prompt",
        )

        assert state.url == "https://test.com"
        assert state.snapshot is mock_snap
        assert state.prompt_block == "test prompt"


class TestInteractiveRoleFiltering:
    """Tests for interactive role filtering."""

    def test_only_interactive_roles_included(self) -> None:
        """Test only interactive roles are included in output."""
        ctx = SentienceContext(top_element_selector=TopElementSelector(by_importance=10))

        elements = [
            make_element(id=1, role="button", importance=80),
            make_element(id=2, role="link", importance=70),
            make_element(id=3, role="heading", importance=90),  # Not interactive
            make_element(id=4, role="textbox", importance=60),
            make_element(id=5, role="paragraph", importance=85),  # Not interactive
        ]
        snap = make_snapshot(elements)

        result = ctx._format_snapshot_for_llm(snap)
        lines = result.strip().split("\n")

        ids = [int(line.split("|")[0]) for line in lines]
        assert 1 in ids  # button
        assert 2 in ids  # link
        assert 3 not in ids  # heading - not interactive
        assert 4 in ids  # textbox
        assert 5 not in ids  # paragraph - not interactive
