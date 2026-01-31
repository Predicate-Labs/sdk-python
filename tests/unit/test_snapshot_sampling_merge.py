import pytest

from sentience.backends.snapshot import merge_snapshots
from sentience.models import BBox, Element, Snapshot, VisualCues


def _el(
    *,
    el_id: int,
    role: str = "link",
    text: str | None = None,
    href: str | None = None,
    name: str | None = None,
    importance: int = 100,
    doc_y: float | None = None,
) -> Element:
    return Element(
        id=el_id,
        role=role,
        text=text,
        href=href,
        name=name,
        importance=importance,
        bbox=BBox(x=10, y=20, width=100, height=30),
        visual_cues=VisualCues(is_primary=False, background_color_name=None, is_clickable=True),
        in_viewport=True,
        doc_y=doc_y,
    )


def test_merge_snapshots_dedupes_by_href_and_prefers_higher_importance():
    s1 = Snapshot(
        status="success",
        url="https://example.com",
        elements=[
            _el(el_id=1, href="https://example.com/a", text="A", importance=120, doc_y=10),
            _el(el_id=2, href="https://example.com/b", text="B", importance=110, doc_y=20),
        ],
    )
    # Same href "a" appears again with higher importance; should replace.
    s2 = Snapshot(
        status="success",
        url="https://example.com",
        elements=[
            _el(el_id=9, href="https://example.com/a", text="A", importance=220, doc_y=10),
            _el(el_id=3, href="https://example.com/c", text="C", importance=105, doc_y=30),
        ],
    )

    merged = merge_snapshots([s1, s2])
    hrefs = [e.href for e in merged.elements if e.href]

    assert hrefs == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]

    a = next(e for e in merged.elements if e.href == "https://example.com/a")
    assert a.importance == 220


def test_merge_snapshots_orders_by_doc_y_then_importance():
    s1 = Snapshot(
        status="success",
        url="https://example.com",
        elements=[
            _el(el_id=1, href="https://example.com/b", text="B", importance=150, doc_y=20),
            _el(el_id=2, href="https://example.com/a", text="A", importance=100, doc_y=10),
        ],
    )
    s2 = Snapshot(
        status="success",
        url="https://example.com",
        elements=[
            _el(el_id=3, href="https://example.com/c", text="C", importance=90, doc_y=30),
        ],
    )

    merged = merge_snapshots([s1, s2])
    assert [e.href for e in merged.elements if e.href] == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]


def test_merge_snapshots_respects_union_limit_and_drops_screenshot():
    s = Snapshot(
        status="success",
        url="https://example.com",
        screenshot="data:fake",
        elements=[
            _el(el_id=1, href="https://example.com/a", text="A", importance=100, doc_y=10),
            _el(el_id=2, href="https://example.com/b", text="B", importance=100, doc_y=20),
            _el(el_id=3, href="https://example.com/c", text="C", importance=100, doc_y=30),
        ],
    )

    merged = merge_snapshots([s], union_limit=2)
    assert len(merged.elements) == 2
    assert merged.screenshot is None


def test_merge_snapshots_requires_nonempty_list():
    with pytest.raises(ValueError):
        merge_snapshots([])

