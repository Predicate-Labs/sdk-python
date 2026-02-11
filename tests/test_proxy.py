"""Tests for proxy support in SentienceBrowser"""

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from predicate.browser import SentienceBrowser
from predicate.models import ProxyConfig


class TestProxyConfig:
    """Test ProxyConfig Pydantic model"""

    def test_proxy_config_basic(self):
        """Test basic proxy config creation"""
        config = ProxyConfig(
            server="http://proxy.example.com:8080",
        )
        assert config.server == "http://proxy.example.com:8080"
        assert config.username is None
        assert config.password is None

    def test_proxy_config_with_auth(self):
        """Test proxy config with authentication"""
        config = ProxyConfig(
            server="http://proxy.example.com:8080",
            username="testuser",
            password="testpass",
        )
        assert config.server == "http://proxy.example.com:8080"
        assert config.username == "testuser"
        assert config.password == "testpass"

    def test_proxy_config_to_playwright_dict_without_auth(self):
        """Test conversion to Playwright dict without authentication"""
        config = ProxyConfig(server="http://proxy.example.com:8080")
        playwright_dict = config.to_playwright_dict()

        assert playwright_dict == {"server": "http://proxy.example.com:8080"}

    def test_proxy_config_to_playwright_dict_with_auth(self):
        """Test conversion to Playwright dict with authentication"""
        config = ProxyConfig(
            server="http://proxy.example.com:8080",
            username="testuser",
            password="testpass",
        )
        playwright_dict = config.to_playwright_dict()

        assert playwright_dict == {
            "server": "http://proxy.example.com:8080",
            "username": "testuser",
            "password": "testpass",
        }


class TestBrowserProxyParsing:
    """Test SentienceBrowser proxy parsing functionality"""

    def test_parse_proxy_http_no_auth(self):
        """Test parsing HTTP proxy without authentication"""
        browser = SentienceBrowser()
        config = browser._parse_proxy("http://proxy.example.com:8080")

        assert config is not None
        assert config.server == "http://proxy.example.com:8080"
        assert config.username is None
        assert config.password is None

    def test_parse_proxy_http_with_auth(self):
        """Test parsing HTTP proxy with authentication"""
        browser = SentienceBrowser()
        config = browser._parse_proxy("http://user:pass@proxy.example.com:8080")

        assert config is not None
        assert config.server == "http://proxy.example.com:8080"
        assert config.username == "user"
        assert config.password == "pass"

    def test_parse_proxy_https(self):
        """Test parsing HTTPS proxy"""
        browser = SentienceBrowser()
        config = browser._parse_proxy("https://user:pass@secure-proxy.example.com:8443")

        assert config is not None
        assert config.server == "https://secure-proxy.example.com:8443"
        assert config.username == "user"
        assert config.password == "pass"

    def test_parse_proxy_socks5(self):
        """Test parsing SOCKS5 proxy"""
        browser = SentienceBrowser()
        config = browser._parse_proxy("socks5://user:pass@socks-proxy.example.com:1080")

        assert config is not None
        assert config.server == "socks5://socks-proxy.example.com:1080"
        assert config.username == "user"
        assert config.password == "pass"

    def test_parse_proxy_invalid_scheme(self, caplog):
        """Test parsing proxy with invalid scheme"""
        with caplog.at_level(logging.WARNING):
            browser = SentienceBrowser()
            config = browser._parse_proxy("ftp://proxy.example.com:8080")

            assert config is None
            assert "Unsupported proxy scheme: ftp" in caplog.text
            assert "Supported: http, https, socks5" in caplog.text

    def test_parse_proxy_missing_port(self, caplog):
        """Test parsing proxy without port"""
        with caplog.at_level(logging.WARNING):
            browser = SentienceBrowser()
            config = browser._parse_proxy("http://proxy.example.com")

            assert config is None
            assert "Proxy URL must include hostname and port" in caplog.text

    def test_parse_proxy_missing_host(self, caplog):
        """Test parsing proxy without hostname"""
        with caplog.at_level(logging.WARNING):
            browser = SentienceBrowser()
            config = browser._parse_proxy("http://:8080")

            assert config is None
            assert "Proxy URL must include hostname and port" in caplog.text

    def test_parse_proxy_empty_string(self):
        """Test parsing empty proxy string"""
        browser = SentienceBrowser()
        config = browser._parse_proxy("")

        assert config is None

    def test_parse_proxy_none(self):
        """Test parsing None proxy"""
        browser = SentienceBrowser()
        config = browser._parse_proxy(None)

        assert config is None


class TestBrowserProxyInitialization:
    """Test SentienceBrowser initialization with proxy"""

    def test_browser_init_with_proxy_arg(self):
        """Test browser initialization with proxy argument"""
        browser = SentienceBrowser(proxy="http://proxy.example.com:8080")
        assert browser.proxy == "http://proxy.example.com:8080"

    def test_browser_init_with_env_var(self, monkeypatch):
        """Test browser initialization with SENTIENCE_PROXY env var"""
        monkeypatch.setenv("SENTIENCE_PROXY", "http://env-proxy.example.com:8080")
        browser = SentienceBrowser()
        assert browser.proxy == "http://env-proxy.example.com:8080"

    def test_browser_init_arg_overrides_env(self, monkeypatch):
        """Test that proxy argument overrides environment variable"""
        monkeypatch.setenv("SENTIENCE_PROXY", "http://env-proxy.example.com:8080")
        browser = SentienceBrowser(proxy="http://arg-proxy.example.com:8080")
        assert browser.proxy == "http://arg-proxy.example.com:8080"

    def test_browser_init_without_proxy(self):
        """Test browser initialization without proxy"""
        # Ensure env var is not set
        if "SENTIENCE_PROXY" in os.environ:
            del os.environ["SENTIENCE_PROXY"]

        browser = SentienceBrowser()
        assert browser.proxy is None


class TestBrowserProxyIntegration:
    """Test proxy integration in browser start() method"""

    @patch("predicate.browser.shutil.copytree")
    @patch("predicate.browser.sync_playwright")
    def test_start_without_proxy(self, mock_playwright, mock_copytree):
        """Test browser start without proxy"""
        # Mock Playwright
        mock_pw_instance = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = []
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context
        mock_playwright.return_value.start.return_value = mock_pw_instance

        # Mock extension path check
        with patch("predicate.browser.Path") as mock_path:
            mock_ext_path = MagicMock()
            mock_ext_path.exists.return_value = True
            (mock_ext_path / "manifest.json").exists.return_value = True
            mock_path.return_value.parent.parent.parent = MagicMock()
            mock_path.return_value.parent.parent.parent.__truediv__.return_value = mock_ext_path

            browser = SentienceBrowser()
            browser.start()

            # Verify proxy was not passed to launch_persistent_context
            call_kwargs = mock_pw_instance.chromium.launch_persistent_context.call_args[1]
            assert "proxy" not in call_kwargs

    @patch("predicate.browser.shutil.copytree")
    @patch("predicate.browser.sync_playwright")
    def test_start_with_proxy(self, mock_playwright, mock_copytree, caplog):
        """Test browser start with proxy"""
        # Mock Playwright
        mock_pw_instance = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = []
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context
        mock_playwright.return_value.start.return_value = mock_pw_instance

        # Mock extension path check
        with patch("predicate.browser.Path") as mock_path:
            mock_ext_path = MagicMock()
            mock_ext_path.exists.return_value = True
            (mock_ext_path / "manifest.json").exists.return_value = True
            mock_path.return_value.parent.parent.parent = MagicMock()
            mock_path.return_value.parent.parent.parent.__truediv__.return_value = mock_ext_path

            with caplog.at_level(logging.INFO):
                browser = SentienceBrowser(proxy="http://user:pass@proxy.example.com:8080")
                browser.start()

                # Verify proxy was passed to launch_persistent_context
                call_kwargs = mock_pw_instance.chromium.launch_persistent_context.call_args[1]
                assert "proxy" in call_kwargs
                assert call_kwargs["proxy"] == {
                    "server": "http://proxy.example.com:8080",
                    "username": "user",
                    "password": "pass",
                }

                # Verify log message
                assert "Using proxy: http://proxy.example.com:8080" in caplog.text

    @patch("predicate.browser.shutil.copytree")
    @patch("predicate.browser.sync_playwright")
    def test_start_with_webrtc_flags(self, mock_playwright, mock_copytree):
        """Test that WebRTC leak protection flags are always included"""
        # Mock Playwright
        mock_pw_instance = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = []
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context
        mock_playwright.return_value.start.return_value = mock_pw_instance

        # Mock extension path check
        with patch("predicate.browser.Path") as mock_path:
            mock_ext_path = MagicMock()
            mock_ext_path.exists.return_value = True
            (mock_ext_path / "manifest.json").exists.return_value = True
            mock_path.return_value.parent.parent.parent = MagicMock()
            mock_path.return_value.parent.parent.parent.__truediv__.return_value = mock_ext_path

            browser = SentienceBrowser()
            browser.start()

            # Verify WebRTC flags are included in args
            call_kwargs = mock_pw_instance.chromium.launch_persistent_context.call_args[1]
            args = call_kwargs["args"]
            assert "--disable-features=WebRtcHideLocalIpsWithMdns" in args
            assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args

    @patch("predicate.browser.shutil.copytree")
    @patch("predicate.browser.sync_playwright")
    def test_start_with_proxy_ignores_https_errors(self, mock_playwright, mock_copytree):
        """Test that ignore_https_errors is set when using proxy (for self-signed certs)"""
        # Mock Playwright
        mock_pw_instance = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = []
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context
        mock_playwright.return_value.start.return_value = mock_pw_instance

        # Mock extension path check
        with patch("predicate.browser.Path") as mock_path:
            mock_ext_path = MagicMock()
            mock_ext_path.exists.return_value = True
            (mock_ext_path / "manifest.json").exists.return_value = True
            mock_path.return_value.parent.parent.parent = MagicMock()
            mock_path.return_value.parent.parent.parent.__truediv__.return_value = mock_ext_path

            browser = SentienceBrowser(proxy="http://user:pass@proxy.example.com:8080")
            browser.start()

            # Verify ignore_https_errors is set when using proxy
            call_kwargs = mock_pw_instance.chromium.launch_persistent_context.call_args[1]
            assert call_kwargs["ignore_https_errors"] is True

    @patch("predicate.browser.shutil.copytree")
    @patch("predicate.browser.sync_playwright")
    def test_start_without_proxy_does_not_ignore_https_errors(self, mock_playwright, mock_copytree):
        """Test that ignore_https_errors is NOT set when not using proxy"""
        # Mock Playwright
        mock_pw_instance = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = []
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context
        mock_playwright.return_value.start.return_value = mock_pw_instance

        # Mock extension path check
        with patch("predicate.browser.Path") as mock_path:
            mock_ext_path = MagicMock()
            mock_ext_path.exists.return_value = True
            (mock_ext_path / "manifest.json").exists.return_value = True
            mock_path.return_value.parent.parent.parent = MagicMock()
            mock_path.return_value.parent.parent.parent.__truediv__.return_value = mock_ext_path

            browser = SentienceBrowser()  # No proxy
            browser.start()

            # Verify ignore_https_errors is NOT set (maintains default security)
            call_kwargs = mock_pw_instance.chromium.launch_persistent_context.call_args[1]
            assert "ignore_https_errors" not in call_kwargs
