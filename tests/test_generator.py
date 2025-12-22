"""
Tests for script generator functionality
"""

import pytest
import tempfile
import os
from sentience import SentienceBrowser, record
from sentience.recorder import Trace
from sentience.generator import ScriptGenerator, generate


def test_generator_python():
    """Test Python script generation"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_navigation("https://example.com")
            rec.record_click(1, "role=button text~'Click'")
            rec.record_type(2, "hello", "role=textbox")
            rec.record_press("Enter")
        
        generator = ScriptGenerator(rec.trace)
        code = generator.generate_python()
        
        # Verify code contains expected elements
        assert "from sentience import" in code
        assert "def main():" in code
        assert "SentienceBrowser" in code
        assert "role=button text~'Click'" in code
        assert "click(browser" in code
        assert "type_text(browser" in code
        assert "press(browser" in code


def test_generator_typescript():
    """Test TypeScript script generation"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_navigation("https://example.com")
            rec.record_click(1, "role=button")
        
        generator = ScriptGenerator(rec.trace)
        code = generator.generate_typescript()
        
        # Verify code contains expected elements
        assert "import" in code
        assert "async function main()" in code
        assert "SentienceBrowser" in code
        assert "await click" in code


def test_generator_save_python():
    """Test saving generated Python script"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_click(1)
        
        generator = ScriptGenerator(rec.trace)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            temp_path = f.name
        
        try:
            generator.save_python(temp_path)
            assert os.path.exists(temp_path)
            
            with open(temp_path) as f:
                code = f.read()
                assert "from sentience import" in code
        finally:
            os.unlink(temp_path)


def test_generator_save_typescript():
    """Test saving generated TypeScript script"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_click(1)
        
        generator = ScriptGenerator(rec.trace)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False) as f:
            temp_path = f.name
        
        try:
            generator.save_typescript(temp_path)
            assert os.path.exists(temp_path)
            
            with open(temp_path) as f:
                code = f.read()
                assert "import" in code
        finally:
            os.unlink(temp_path)


def test_generator_without_selector():
    """Test generator handles steps without selectors"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_click(1)  # No selector
        
        generator = ScriptGenerator(rec.trace)
        code = generator.generate_python()
        
        # Should include TODO comment for missing selector
        assert "TODO: replace with semantic selector" in code
        assert "click(browser, 1)" in code


def test_generate_helper():
    """Test generate() helper function"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with record(browser) as rec:
            rec.record_click(1)
        
        # Test Python generation
        py_code = generate(rec.trace, 'py')
        assert "from sentience import" in py_code
        
        # Test TypeScript generation
        ts_code = generate(rec.trace, 'ts')
        assert "import" in ts_code

