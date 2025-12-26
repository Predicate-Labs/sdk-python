"""
Unit tests for sentience.utils module.

Tests canonicalization and hashing functions for snapshot digests.
"""

from sentience.utils import (
    BBox,
    canonical_snapshot_loose,
    canonical_snapshot_strict,
    compute_snapshot_digests,
    extract_element_fingerprint,
    normalize_bbox,
    normalize_text_strict,
    sha256_digest,
)


class TestNormalizeText:
    """Tests for text normalization."""

    def test_normalize_text_basic(self):
        """Test basic text normalization."""
        text = "  Hello   World  "
        result = normalize_text_strict(text)
        assert result == "hello world"

    def test_normalize_text_digits(self):
        """Test digit replacement."""
        text = "Price: $79.99"
        result = normalize_text_strict(text)
        assert result == "price: $#.#"

    def test_normalize_text_time(self):
        """Test time pattern normalization."""
        text = "12:34 PM"
        result = normalize_text_strict(text)
        assert result == "#:# pm"

    def test_normalize_text_length_cap(self):
        """Test length capping."""
        text = "a" * 100
        result = normalize_text_strict(text, max_length=80)
        assert len(result) == 80

    def test_normalize_text_empty(self):
        """Test empty text."""
        assert normalize_text_strict(None) == ""
        assert normalize_text_strict("") == ""
        assert normalize_text_strict("   ") == ""

    def test_normalize_text_stability(self):
        """Test that same text produces same result."""
        text1 = "Add to Cart"
        text2 = "  add   TO  cart  "
        assert normalize_text_strict(text1) == normalize_text_strict(text2)


class TestNormalizeBBox:
    """Tests for bbox normalization."""

    def test_normalize_bbox_dict(self):
        """Test bbox normalization from dict."""
        bbox = {"x": 123, "y": 456, "width": 78, "height": 90}
        result = normalize_bbox(bbox)
        # Should round to 2px buckets (123 rounds to 124)
        assert result == [124, 456, 78, 90]

    def test_normalize_bbox_object(self):
        """Test bbox normalization from BBox object."""
        bbox = BBox(x=123, y=456, width=78, height=90)
        result = normalize_bbox(bbox)
        assert result == [124, 456, 78, 90]

    def test_normalize_bbox_rounding(self):
        """Test 2px bucket rounding."""
        bbox = {"x": 121, "y": 122, "width": 123, "height": 124}
        result = normalize_bbox(bbox, bucket_size=2)
        # 121 -> 120, 122 -> 122, 123 -> 124, 124 -> 124
        assert result == [120, 122, 124, 124]

    def test_normalize_bbox_stability(self):
        """Test that similar bboxes produce same result."""
        bbox1 = {"x": 100, "y": 200, "width": 50, "height": 30}
        bbox2 = {"x": 101, "y": 199, "width": 51, "height": 29}
        # Both should round to same buckets (with 2px rounding)
        result1 = normalize_bbox(bbox1)
        result2 = normalize_bbox(bbox2)
        # 100->100, 200->200, 50->50, 30->30
        # 101->100, 199->200, 51->52, 29->28
        assert result1 == [100, 200, 50, 30]
        assert result2 == [100, 200, 52, 28]


class TestExtractElementFingerprint:
    """Tests for element fingerprint extraction."""

    def test_extract_with_text(self):
        """Test extraction with text included."""
        element = {
            "id": 42,
            "role": "button",
            "text": "Add to Cart",
            "bbox": {"x": 100, "y": 200, "width": 80, "height": 30},
            "visual_cues": {
                "is_clickable": True,
                "is_primary": False,
            },
        }

        fingerprint = extract_element_fingerprint(element, include_text=True)

        assert fingerprint.id == 42
        assert fingerprint.role == "button"
        assert fingerprint.text == "add to cart"
        assert fingerprint.clickable == 1
        assert fingerprint.primary == 0
        assert len(fingerprint.bbox) == 4

    def test_extract_without_text(self):
        """Test extraction without text (loose digest)."""
        element = {
            "id": 42,
            "role": "button",
            "text": "Add to Cart",
            "bbox": {"x": 100, "y": 200, "width": 80, "height": 30},
            "visual_cues": {
                "is_clickable": True,
                "is_primary": True,
            },
        }

        fingerprint = extract_element_fingerprint(element, include_text=False)

        assert fingerprint.id == 42
        assert fingerprint.text == ""  # No text in loose digest

    def test_extract_missing_fields(self):
        """Test extraction with missing fields."""
        element = {"id": 1}

        fingerprint = extract_element_fingerprint(element)

        assert fingerprint.id == 1
        assert fingerprint.role == "unknown"
        assert fingerprint.clickable == 0
        assert fingerprint.primary == 0


class TestCanonicalSnapshots:
    """Tests for canonical snapshot string generation."""

    def test_canonical_strict_ordering(self):
        """Test that elements are sorted by ID."""
        elements = [
            {
                "id": 3,
                "role": "button",
                "text": "C",
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
                "visual_cues": {},
            },
            {
                "id": 1,
                "role": "button",
                "text": "A",
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
                "visual_cues": {},
            },
            {
                "id": 2,
                "role": "button",
                "text": "B",
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
                "visual_cues": {},
            },
        ]

        canonical = canonical_snapshot_strict(elements)

        # Should be sorted by ID (JSON has space after colon)
        assert '"id": 1' in canonical
        assert canonical.index('"id": 1') < canonical.index('"id": 2')
        assert canonical.index('"id": 2') < canonical.index('"id": 3')

    def test_canonical_loose_no_text(self):
        """Test that loose digest has no text."""
        elements = [
            {
                "id": 1,
                "role": "button",
                "text": "Click me",
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
                "visual_cues": {},
            },
        ]

        canonical = canonical_snapshot_loose(elements)

        # Should not contain the text
        assert "click me" not in canonical.lower()

    def test_canonical_stability(self):
        """Test that same elements produce same canonical string."""
        elements = [
            {
                "id": 1,
                "role": "button",
                "text": "Test",
                "bbox": {"x": 100, "y": 200, "width": 50, "height": 30},
                "visual_cues": {},
            },
        ]

        canonical1 = canonical_snapshot_strict(elements)
        canonical2 = canonical_snapshot_strict(elements)

        assert canonical1 == canonical2


class TestSHA256Digest:
    """Tests for SHA256 hashing."""

    def test_sha256_format(self):
        """Test hash format."""
        digest = sha256_digest("test")
        assert digest.startswith("sha256:")
        assert len(digest) == 71  # "sha256:" + 64 hex chars

    def test_sha256_stability(self):
        """Test that same input produces same hash."""
        digest1 = sha256_digest("test")
        digest2 = sha256_digest("test")
        assert digest1 == digest2

    def test_sha256_uniqueness(self):
        """Test that different inputs produce different hashes."""
        digest1 = sha256_digest("test1")
        digest2 = sha256_digest("test2")
        assert digest1 != digest2


class TestComputeSnapshotDigests:
    """Tests for combined digest computation."""

    def test_compute_both_digests(self):
        """Test that both digests are computed."""
        elements = [
            {
                "id": 1,
                "role": "button",
                "text": "Click",
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
                "visual_cues": {},
            },
        ]

        result = compute_snapshot_digests(elements)

        assert "strict" in result
        assert "loose" in result
        assert result["strict"].startswith("sha256:")
        assert result["loose"].startswith("sha256:")

    def test_digests_differ(self):
        """Test that strict and loose digests differ when text present."""
        elements = [
            {
                "id": 1,
                "role": "button",
                "text": "Important Text",
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
                "visual_cues": {},
            },
        ]

        result = compute_snapshot_digests(elements)

        # Digests should differ because strict includes text
        assert result["strict"] != result["loose"]

    def test_loose_digest_stable_across_text_changes(self):
        """Test that loose digest stays same when only text changes."""
        elements1 = [
            {
                "id": 1,
                "role": "button",
                "text": "Text A",
                "bbox": {"x": 100, "y": 200, "width": 50, "height": 30},
                "visual_cues": {"is_clickable": True},
            },
        ]

        elements2 = [
            {
                "id": 1,
                "role": "button",
                "text": "Text B",
                "bbox": {"x": 100, "y": 200, "width": 50, "height": 30},
                "visual_cues": {"is_clickable": True},
            },
        ]

        digest1 = compute_snapshot_digests(elements1)
        digest2 = compute_snapshot_digests(elements2)

        # Loose digests should be same (no text)
        assert digest1["loose"] == digest2["loose"]

        # Strict digests should differ (different text)
        assert digest1["strict"] != digest2["strict"]
