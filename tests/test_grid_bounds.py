"""
Tests for get_grid_bounds functionality
"""

import pytest

from sentience.models import (
    BBox,
    Element,
    GridInfo,
    GridPosition,
    LayoutHints,
    Snapshot,
    Viewport,
    VisualCues,
)


def create_test_element(
    element_id: int,
    x: float,
    y: float,
    width: float,
    height: float,
    grid_id: int | None = None,
    row_index: int | None = None,
    col_index: int | None = None,
    text: str | None = None,
    href: str | None = None,
) -> Element:
    """Helper to create test elements with layout data"""
    layout = None
    if grid_id is not None:
        grid_pos = None
        if row_index is not None and col_index is not None:
            grid_pos = GridPosition(
                row_index=row_index,
                col_index=col_index,
                cluster_id=grid_id,
            )
        layout = LayoutHints(
            grid_id=grid_id,
            grid_pos=grid_pos,
            grid_confidence=1.0,
            parent_confidence=1.0,
            region_confidence=1.0,
        )

    return Element(
        id=element_id,
        role="link",
        text=text or f"Element {element_id}",
        importance=100,
        bbox=BBox(x=x, y=y, width=width, height=height),
        visual_cues=VisualCues(
            is_primary=False,
            background_color_name=None,
            is_clickable=True,
        ),
        in_viewport=True,
        is_occluded=False,
        z_index=0,
        layout=layout,
        href=href,
    )


class TestGetGridBounds:
    """Test suite for Snapshot.get_grid_bounds()"""

    def test_empty_snapshot(self):
        """Test with no elements"""
        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=[],
        )
        result = snapshot.get_grid_bounds()
        assert result == []

    def test_no_layout_data(self):
        """Test with elements but no layout data"""
        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=[
                create_test_element(1, 10, 20, 100, 50, grid_id=None),
                create_test_element(2, 120, 20, 100, 50, grid_id=None),
            ],
        )
        result = snapshot.get_grid_bounds()
        assert result == []

    def test_single_grid(self):
        """Test with a single 2x2 grid"""
        # Create a 2x2 grid
        elements = [
            create_test_element(1, 10, 20, 100, 50, grid_id=0, row_index=0, col_index=0),
            create_test_element(2, 120, 20, 100, 50, grid_id=0, row_index=0, col_index=1),
            create_test_element(3, 10, 80, 100, 50, grid_id=0, row_index=1, col_index=0),
            create_test_element(4, 120, 80, 100, 50, grid_id=0, row_index=1, col_index=1),
        ]
        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=elements,
        )

        result = snapshot.get_grid_bounds()
        assert len(result) == 1

        grid = result[0]
        assert grid.grid_id == 0
        assert grid.bbox.x == 10
        assert grid.bbox.y == 20
        assert grid.bbox.width == 210  # max_x (120+100) - min_x (10)
        assert grid.bbox.height == 110  # max_y (80+50) - min_y (20)
        assert grid.row_count == 2
        assert grid.col_count == 2
        assert grid.item_count == 4
        assert grid.confidence == 1.0

    def test_multiple_grids(self):
        """Test with multiple distinct grids"""
        # Grid 0: 2x1 at top
        grid0_elements = [
            create_test_element(1, 10, 20, 100, 50, grid_id=0, row_index=0, col_index=0),
            create_test_element(2, 120, 20, 100, 50, grid_id=0, row_index=0, col_index=1),
        ]
        # Grid 1: 1x3 at bottom
        grid1_elements = [
            create_test_element(3, 10, 200, 100, 50, grid_id=1, row_index=0, col_index=0),
            create_test_element(4, 10, 260, 100, 50, grid_id=1, row_index=1, col_index=0),
            create_test_element(5, 10, 320, 100, 50, grid_id=1, row_index=2, col_index=0),
        ]

        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=grid0_elements + grid1_elements,
        )

        result = snapshot.get_grid_bounds()
        assert len(result) == 2

        # Check grid 0
        grid0 = result[0]
        assert grid0.grid_id == 0
        assert grid0.bbox.x == 10
        assert grid0.bbox.y == 20
        assert grid0.bbox.width == 210
        assert grid0.bbox.height == 50
        assert grid0.row_count == 1
        assert grid0.col_count == 2
        assert grid0.item_count == 2

        # Check grid 1
        grid1 = result[1]
        assert grid1.grid_id == 1
        assert grid1.bbox.x == 10
        assert grid1.bbox.y == 200
        assert grid1.bbox.width == 100
        assert grid1.bbox.height == 170  # max_y (320+50) - min_y (200)
        assert grid1.row_count == 3
        assert grid1.col_count == 1
        assert grid1.item_count == 3

    def test_filter_by_grid_id(self):
        """Test filtering by specific grid_id"""
        elements = [
            create_test_element(1, 10, 20, 100, 50, grid_id=0, row_index=0, col_index=0),
            create_test_element(2, 120, 20, 100, 50, grid_id=0, row_index=0, col_index=1),
            create_test_element(3, 10, 200, 100, 50, grid_id=1, row_index=0, col_index=0),
        ]

        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=elements,
        )

        # Get only grid 0
        result = snapshot.get_grid_bounds(grid_id=0)
        assert len(result) == 1
        assert result[0].grid_id == 0
        assert result[0].item_count == 2

        # Get only grid 1
        result = snapshot.get_grid_bounds(grid_id=1)
        assert len(result) == 1
        assert result[0].grid_id == 1
        assert result[0].item_count == 1

        # Get non-existent grid
        result = snapshot.get_grid_bounds(grid_id=99)
        assert result == []

    def test_grid_without_grid_pos(self):
        """Test grid elements that have grid_id but no grid_pos"""
        # Elements with grid_id but no grid_pos (should still be counted)
        elements = [
            create_test_element(1, 10, 20, 100, 50, grid_id=0, row_index=None, col_index=None),
            create_test_element(2, 120, 20, 100, 50, grid_id=0, row_index=None, col_index=None),
        ]

        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=elements,
        )

        result = snapshot.get_grid_bounds()
        assert len(result) == 1
        grid = result[0]
        assert grid.grid_id == 0
        assert grid.item_count == 2
        assert grid.row_count == 0  # No grid_pos means no rows/cols counted
        assert grid.col_count == 0

    def test_label_inference_product_grid(self):
        """Test that product grids get labeled correctly"""
        elements = [
            create_test_element(
                1,
                10,
                20,
                100,
                50,
                grid_id=0,
                row_index=0,
                col_index=0,
                text="Wireless Headphones $50",
                href="https://example.com/product/headphones",
            ),
            create_test_element(
                2,
                120,
                20,
                100,
                50,
                grid_id=0,
                row_index=0,
                col_index=1,
                text="Bluetooth Speaker $30",
                href="https://example.com/product/speaker",
            ),
            create_test_element(
                3,
                10,
                80,
                100,
                50,
                grid_id=0,
                row_index=1,
                col_index=0,
                text="USB-C Cable $10",
                href="https://example.com/product/cable",
            ),
        ]

        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=elements,
        )

        result = snapshot.get_grid_bounds()
        assert len(result) == 1
        assert result[0].label == "product_grid"

    def test_label_inference_article_feed(self):
        """Test that article feeds get labeled correctly"""
        elements = [
            create_test_element(
                1,
                10,
                20,
                100,
                50,
                grid_id=0,
                row_index=0,
                col_index=0,
                text="Breaking News 2 hours ago",
            ),
            create_test_element(
                2,
                10,
                80,
                100,
                50,
                grid_id=0,
                row_index=1,
                col_index=0,
                text="Tech Update 3 days ago",
            ),
        ]

        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=elements,
        )

        result = snapshot.get_grid_bounds()
        assert len(result) == 1
        assert result[0].label == "article_feed"

    def test_label_inference_navigation(self):
        """Test that navigation grids get labeled correctly"""
        elements = [
            create_test_element(
                1, 10, 20, 80, 30, grid_id=0, row_index=0, col_index=0, text="Home"
            ),
            create_test_element(
                2, 100, 20, 80, 30, grid_id=0, row_index=0, col_index=1, text="About"
            ),
            create_test_element(
                3, 190, 20, 80, 30, grid_id=0, row_index=0, col_index=2, text="Contact"
            ),
        ]

        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=elements,
        )

        result = snapshot.get_grid_bounds()
        assert len(result) == 1
        assert result[0].label == "navigation"

    def test_sorted_by_grid_id(self):
        """Test that results are sorted by grid_id"""
        elements = [
            create_test_element(1, 10, 20, 100, 50, grid_id=2, row_index=0, col_index=0),
            create_test_element(2, 10, 200, 100, 50, grid_id=0, row_index=0, col_index=0),
            create_test_element(3, 10, 380, 100, 50, grid_id=1, row_index=0, col_index=0),
        ]

        snapshot = Snapshot(
            status="success",
            url="https://example.com",
            elements=elements,
        )

        result = snapshot.get_grid_bounds()
        assert len(result) == 3
        assert result[0].grid_id == 0
        assert result[1].grid_id == 1
        assert result[2].grid_id == 2
