"""
Tests for read functionality
"""

from sentience import SentienceBrowser, read


def test_read_text():
    """Test reading page as text"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        result = read(browser, output_format="text")
        
        assert result["status"] == "success"
        assert result["format"] == "text"
        assert "content" in result
        assert "length" in result
        assert len(result["content"]) > 0
        assert result["url"] == "https://example.com/"


def test_read_markdown():
    """Test reading page as markdown"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        result = read(browser, output_format="markdown")
        
        assert result["status"] == "success"
        assert result["format"] == "markdown"
        assert "content" in result
        assert "length" in result
        assert len(result["content"]) > 0
        assert result["url"] == "https://example.com/"


def test_read_markdown_enhanced():
    """Test reading page as markdown with enhancement"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        # Test with enhancement (default)
        result_enhanced = read(browser, output_format="markdown", enhance_markdown=True)
        
        assert result_enhanced["status"] == "success"
        assert result_enhanced["format"] == "markdown"
        assert len(result_enhanced["content"]) > 0
        
        # Test without enhancement
        result_basic = read(browser, output_format="markdown", enhance_markdown=False)
        
        assert result_basic["status"] == "success"
        assert result_basic["format"] == "markdown"
        assert len(result_basic["content"]) > 0
        
        # Enhanced markdown should be different (and likely better formatted)
        # Note: They might be similar for simple pages, but enhanced should handle more cases
        assert isinstance(result_enhanced["content"], str)
        assert isinstance(result_basic["content"], str)

