import asyncio
import importlib
import sys

snapshot_module = importlib.import_module("predicate.snapshot")
from predicate.snapshot import _post_snapshot_to_gateway_async, _post_snapshot_to_gateway_sync


class _DummyResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"status": "success", "elements": [], "url": "https://example.com"}


def test_post_snapshot_async_uses_default_timeout(monkeypatch):
    class DummyClient:
        last_timeout = None

        def __init__(self, timeout):
            DummyClient.last_timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *args, **kwargs):
            return _DummyResponse()

    dummy_httpx = type("DummyHttpx", (), {"AsyncClient": DummyClient})
    monkeypatch.setitem(sys.modules, "httpx", dummy_httpx)
    asyncio.run(
        _post_snapshot_to_gateway_async(
            {"raw_elements": [], "url": "https://example.com", "viewport": None, "goal": None, "options": {}},
            "sk_test",
            "https://api.sentienceapi.com",
        )
    )
    assert DummyClient.last_timeout == 30.0


def test_post_snapshot_async_uses_custom_timeout(monkeypatch):
    class DummyClient:
        last_timeout = None

        def __init__(self, timeout):
            DummyClient.last_timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *args, **kwargs):
            return _DummyResponse()

    dummy_httpx = type("DummyHttpx", (), {"AsyncClient": DummyClient})
    monkeypatch.setitem(sys.modules, "httpx", dummy_httpx)
    asyncio.run(
        _post_snapshot_to_gateway_async(
            {"raw_elements": [], "url": "https://example.com", "viewport": None, "goal": None, "options": {}},
            "sk_test",
            "https://api.sentienceapi.com",
            timeout_s=12.5,
        )
    )
    assert DummyClient.last_timeout == 12.5


def test_post_snapshot_sync_uses_default_timeout(monkeypatch):
    class DummyRequests:
        last_timeout = None

        @staticmethod
        def post(*args, **kwargs):
            DummyRequests.last_timeout = kwargs.get("timeout")
            return _DummyResponse()

    monkeypatch.setattr(snapshot_module, "requests", DummyRequests)
    _post_snapshot_to_gateway_sync(
        {"raw_elements": [], "url": "https://example.com", "viewport": None, "goal": None, "options": {}},
        "sk_test",
        "https://api.sentienceapi.com",
    )
    assert DummyRequests.last_timeout == 30


def test_post_snapshot_sync_uses_custom_timeout(monkeypatch):
    class DummyRequests:
        last_timeout = None

        @staticmethod
        def post(*args, **kwargs):
            DummyRequests.last_timeout = kwargs.get("timeout")
            return _DummyResponse()

    monkeypatch.setattr(snapshot_module, "requests", DummyRequests)
    _post_snapshot_to_gateway_sync(
        {"raw_elements": [], "url": "https://example.com", "viewport": None, "goal": None, "options": {}},
        "sk_test",
        "https://api.sentienceapi.com",
        timeout_s=9.0,
    )
    assert DummyRequests.last_timeout == 9.0
