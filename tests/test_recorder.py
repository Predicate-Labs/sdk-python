"""
Tests for recorder functionality
"""

import pytest
import tempfile
import os
from sentience import SentienceBrowser, record, Trace, TraceStep
from sentience.recorder import Recorder


def test_recorder_start_stop():
    """Test recorder can start and stop"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        rec = record(browser)
        rec.start()
        assert rec._active is True
        assert rec.trace is not None
        
        rec.stop()
        assert rec._active is False


def test_recorder_context_manager():
    """Test recorder as context manager"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            assert rec._active is True
            assert rec.trace is not None
        
        assert rec._active is False


def test_recorder_navigation():
    """Test recording navigation events"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_navigation("https://example.com/page2")
        
        assert len(rec.trace.steps) == 1
        assert rec.trace.steps[0].type == "navigation"
        assert rec.trace.steps[0].url == "https://example.com/page2"


def test_recorder_click():
    """Test recording click events"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_click(42, "role=button text~'Click'")
        
        assert len(rec.trace.steps) == 1
        assert rec.trace.steps[0].type == "click"
        assert rec.trace.steps[0].element_id == 42
        assert rec.trace.steps[0].selector == "role=button text~'Click'"


def test_recorder_type():
    """Test recording type events"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_type(10, "hello world", "role=textbox")
        
        assert len(rec.trace.steps) == 1
        assert rec.trace.steps[0].type == "type"
        assert rec.trace.steps[0].element_id == 10
        assert rec.trace.steps[0].text == "hello world"
        assert rec.trace.steps[0].selector == "role=textbox"


def test_recorder_type_masking():
    """Test text masking in type events"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.add_mask_pattern("password")
            rec.record_type(10, "mypassword123", "role=textbox")
        
        assert len(rec.trace.steps) == 1
        assert rec.trace.steps[0].text == "***"  # Should be masked


def test_recorder_press():
    """Test recording key press events"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_press("Enter")
        
        assert len(rec.trace.steps) == 1
        assert rec.trace.steps[0].type == "press"
        assert rec.trace.steps[0].key == "Enter"


def test_trace_save_load():
    """Test trace save and load"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_navigation("https://example.com")
            rec.record_click(1, "role=button")
            rec.record_type(2, "text", "role=textbox")
        
        # Save trace
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            rec.save(temp_path)
            assert os.path.exists(temp_path)
            
            # Load trace
            loaded_trace = Trace.load(temp_path)
            assert loaded_trace.version == "1.0.0"
            assert len(loaded_trace.steps) == 3
            assert loaded_trace.steps[0].type == "navigation"
            assert loaded_trace.steps[1].type == "click"
            assert loaded_trace.steps[2].type == "type"
        finally:
            os.unlink(temp_path)


def test_trace_format():
    """Test trace format matches spec"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_click(1)
        
        trace_dict = rec.trace.steps[0].to_dict()
        
        # Verify required fields
        assert "ts" in trace_dict
        assert "type" in trace_dict
        assert trace_dict["type"] == "click"
        assert "element_id" in trace_dict
        assert trace_dict["element_id"] == 1

