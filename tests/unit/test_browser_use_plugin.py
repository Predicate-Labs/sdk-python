import importlib

import pytest


def test_plugin_imports():
    mod = importlib.import_module("predicate.integrations.browser_use.plugin")
    assert hasattr(mod, "PredicateBrowserUsePlugin")


def test_effective_snapshot_options_sets_api_key_and_use_api():
    from predicate.integrations.browser_use.plugin import (
        PredicateBrowserUsePlugin,
        PredicateBrowserUsePluginConfig,
    )
    from predicate.models import SnapshotOptions

    plugin = PredicateBrowserUsePlugin(
        config=PredicateBrowserUsePluginConfig(
            predicate_api_key="sk_test_123",
            use_api=None,
            snapshot_options=SnapshotOptions(use_api=None),
        )
    )

    # v1: internal helper is the only way to validate merged SnapshotOptions behavior.
    # pylint: disable=protected-access
    opts = plugin._effective_snapshot_options()
    assert opts.predicate_api_key == "sk_test_123"
    assert opts.sentience_api_key == "sk_test_123"
    assert opts.use_api is True


def test_effective_snapshot_options_use_api_override():
    from predicate.integrations.browser_use.plugin import (
        PredicateBrowserUsePlugin,
        PredicateBrowserUsePluginConfig,
    )
    from predicate.models import SnapshotOptions

    plugin = PredicateBrowserUsePlugin(
        config=PredicateBrowserUsePluginConfig(
            predicate_api_key="sk_test_123",
            use_api=False,
            snapshot_options=SnapshotOptions(use_api=True),
        )
    )

    # pylint: disable=protected-access
    opts = plugin._effective_snapshot_options()
    assert opts.use_api is False


def test_register_tools_requires_browser_use(monkeypatch):
    from predicate.integrations.browser_use.plugin import PredicateBrowserUsePlugin

    plugin = PredicateBrowserUsePlugin()

    def _fake_import_module(name: str, *args, **kwargs):
        if name == "browser_use":
            raise ImportError("browser_use not installed")
        return importlib.import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _fake_import_module)

    with pytest.raises(ImportError):
        plugin.register_tools(tools=None)


@pytest.mark.asyncio
async def test_wrap_step_calls_hooks_in_order():
    from predicate.integrations.browser_use.plugin import PredicateBrowserUsePlugin

    plugin = PredicateBrowserUsePlugin()
    calls: list[str] = []

    async def _on_start(_agent):
        calls.append("start")

    async def _on_end(_agent):
        calls.append("end")

    async def _step():
        calls.append("step")
        return 123

    # Monkeypatch instance methods (lightweight behavioral test).
    plugin.on_step_start = _on_start  # type: ignore[assignment]
    plugin.on_step_end = _on_end  # type: ignore[assignment]

    out = await plugin.wrap_step(agent=object(), step_coro=_step)
    assert out == 123
    assert calls == ["start", "step", "end"]


@pytest.mark.asyncio
async def test_on_step_end_raises_on_required_auto_check_false():
    from predicate.integrations.browser_use.plugin import (
        PredicateBrowserUsePlugin,
        PredicateBrowserUsePluginConfig,
        PredicateBrowserUseVerificationError,
        StepCheckSpec,
    )

    class _FakeHandle:
        def once(self) -> bool:
            return False

    class _FakeDbg:
        def check(self, _pred, label: str, required: bool = False):
            assert label == "req"
            assert required is True
            return _FakeHandle()

        async def snapshot(self):
            return None

    class _FakeRuntime:
        async def emit_step_end(self, **_kw):
            return {}

    plugin = PredicateBrowserUsePlugin(
        config=PredicateBrowserUsePluginConfig(
            auto_snapshot_each_step=False,
            auto_checks_each_step=True,
            auto_checks=[StepCheckSpec(predicate=lambda _ctx: None, label="req", required=True, eventually=False)],
            on_failure="raise",
        )
    )
    plugin.runtime = _FakeRuntime()  # type: ignore[assignment]
    plugin.dbg = _FakeDbg()  # type: ignore[assignment]

    with pytest.raises(PredicateBrowserUseVerificationError):
        await plugin.on_step_end(agent=object())

