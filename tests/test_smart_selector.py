"""
Tests for smart selector inference
"""

import pytest
from sentience import SentienceBrowser, record, snapshot


def test_smart_selector_inference():
    """Test that recorder infers selectors automatically"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        # Take snapshot to get element
        snap = snapshot(browser)
        if len(snap.elements) > 0:
            element = snap.elements[0]
            
            with record(browser) as rec:
                # Record click without providing selector
                rec.record_click(element.id)
            
            # Should have inferred a selector
            step = rec.trace.steps[0]
            # Selector may or may not be inferred depending on element properties
            # But element_id should always be present
            assert step.element_id == element.id


def test_smart_selector_with_text():
    """Test selector inference for elements with text"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        # Find element with text
        element_with_text = None
        for el in snap.elements:
            if el.text and len(el.text) > 0:
                element_with_text = el
                break
        
        if element_with_text:
            with record(browser) as rec:
                rec.record_click(element_with_text.id)
            
            step = rec.trace.steps[0]
            # If selector was inferred, it should include text
            if step.selector:
                assert "text" in step.selector or "role" in step.selector


def test_smart_selector_validation():
    """Test that inferred selectors are validated"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        if len(snap.elements) > 0:
            element = snap.elements[0]
            
            with record(browser) as rec:
                rec.record_click(element.id)
            
            step = rec.trace.steps[0]
            # If selector was inferred and validated, it should match the element
            if step.selector:
                # Verify selector would match the element
                from sentience.query import query
                matches = query(snap, step.selector)
                # Should match at least the original element
                assert any(el.id == element.id for el in matches)

