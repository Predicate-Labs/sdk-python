"""
Playwright browser harness with extension loading
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright


class SentienceBrowser:
    """Main browser session with Sentience extension loaded"""
    
    def __init__(self, license_key: Optional[str] = None, headless: bool = False):
        """
        Initialize Sentience browser
        
        Args:
            license_key: Optional license key for headless mode
            headless: Whether to run in headless mode
        """
        self.license_key = license_key
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._extension_path: Optional[str] = None
    
    def start(self) -> None:
        """Launch browser with extension loaded"""
        # Get extension path (sentience-chrome directory)
        repo_root = Path(__file__).parent.parent.parent
        extension_source = repo_root / "sentience-chrome"
        
        if not extension_source.exists():
            raise FileNotFoundError(
                f"Extension not found at {extension_source}. "
                "Make sure sentience-chrome directory exists."
            )
        
        # Create temporary extension bundle
        temp_dir = tempfile.mkdtemp(prefix="sentience-ext-")
        self._extension_path = temp_dir
        
        # Copy extension files
        files_to_copy = [
            "manifest.json",
            "content.js",
            "background.js",
            "injected_api.js",
        ]
        
        for file in files_to_copy:
            src = extension_source / file
            if src.exists():
                shutil.copy2(src, os.path.join(temp_dir, file))
        
        # Copy pkg directory (WASM)
        pkg_source = extension_source / "pkg"
        if pkg_source.exists():
            pkg_dest = os.path.join(temp_dir, "pkg")
            shutil.copytree(pkg_source, pkg_dest, dirs_exist_ok=True)
        
        # Launch Playwright
        self.playwright = sync_playwright().start()
        
        # Create persistent context with extension
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=tempfile.mkdtemp(prefix="sentience-profile-"),
            headless=self.headless,
            args=[
                f"--load-extension={temp_dir}",
                f"--disable-extensions-except={temp_dir}",
            ],
        )
        
        # Get first page or create new one
        pages = self.context.pages
        if pages:
            self.page = pages[0]
        else:
            self.page = self.context.new_page()
        
        # Wait for extension to load
        self._wait_for_extension()
    
    def _wait_for_extension(self, timeout: int = 10000) -> bool:
        """Wait for window.sentience API to be available"""
        import time
        start = time.time()
        
        while time.time() - start < timeout / 1000:
            try:
                result = self.page.evaluate("""
                    () => {
                        return typeof window.sentience !== 'undefined' && 
                               typeof window.sentience.snapshot === 'function';
                    }
                """)
                if result:
                    return True
            except Exception:
                pass
            
            time.sleep(0.1)
        
        return False
    
    def close(self) -> None:
        """Close browser and cleanup"""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
        if self._extension_path and os.path.exists(self._extension_path):
            shutil.rmtree(self._extension_path)
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

