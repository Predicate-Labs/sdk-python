import pytest

from sentience import AsyncSentienceBrowser, SentienceBrowser
from sentience.permissions import PermissionPolicy


class SyncContextStub:
    def __init__(self) -> None:
        self.calls: list[tuple | str] = []

    def clear_permissions(self) -> None:
        self.calls.append("clear")

    def set_geolocation(self, geolocation: dict) -> None:
        self.calls.append(("geolocation", geolocation))

    def grant_permissions(self, permissions: list[str], origin: str | None = None) -> None:
        self.calls.append(("grant", permissions, origin))


class AsyncContextStub:
    def __init__(self) -> None:
        self.calls: list[tuple | str] = []

    async def clear_permissions(self) -> None:
        self.calls.append("clear")

    async def set_geolocation(self, geolocation: dict) -> None:
        self.calls.append(("geolocation", geolocation))

    async def grant_permissions(self, permissions: list[str], origin: str | None = None) -> None:
        self.calls.append(("grant", permissions, origin))


def test_apply_permission_policy_sync() -> None:
    policy = PermissionPolicy(
        default="clear",
        auto_grant=["geolocation"],
        geolocation={"latitude": 37.77, "longitude": -122.41},
        origin="https://example.com",
    )
    browser = SentienceBrowser(permission_policy=policy)
    context = SyncContextStub()
    browser.apply_permission_policy(context)
    assert context.calls == [
        "clear",
        ("geolocation", {"latitude": 37.77, "longitude": -122.41}),
        ("grant", ["geolocation"], "https://example.com"),
    ]


@pytest.mark.asyncio
async def test_apply_permission_policy_async() -> None:
    policy = PermissionPolicy(
        default="clear",
        auto_grant=["notifications"],
        geolocation={"latitude": 40.71, "longitude": -74.0, "accuracy": 10},
    )
    browser = AsyncSentienceBrowser(permission_policy=policy)
    context = AsyncContextStub()
    await browser.apply_permission_policy(context)
    assert context.calls == [
        "clear",
        ("geolocation", {"latitude": 40.71, "longitude": -74.0, "accuracy": 10}),
        ("grant", ["notifications"], None),
    ]
