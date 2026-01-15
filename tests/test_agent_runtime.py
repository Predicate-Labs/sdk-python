"""
Tests for AgentRuntime.

These tests verify the AgentRuntime works correctly with the new
BrowserBackend-based architecture.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sentience.agent_runtime import AgentRuntime
from sentience.models import SnapshotOptions
from sentience.verification import AssertContext, AssertOutcome


class MockBackend:
    """Mock BrowserBackend implementation for testing."""

    def __init__(self) -> None:
        self._url = "https://example.com"
        self.eval_results: dict[str, any] = {}

    async def get_url(self) -> str:
        return self._url

    async def eval(self, expression: str) -> any:
        return self.eval_results.get(expression)

    async def refresh_page_info(self):
        pass

    async def call(self, function_declaration: str, args=None):
        pass

    async def get_layout_metrics(self):
        pass

    async def screenshot_png(self) -> bytes:
        return b""

    async def mouse_move(self, x: float, y: float) -> None:
        pass

    async def mouse_click(self, x: float, y: float, button="left", click_count=1) -> None:
        pass

    async def wheel(self, delta_y: float, x=None, y=None) -> None:
        pass

    async def type_text(self, text: str) -> None:
        pass

    async def wait_ready_state(self, state="interactive", timeout_ms=15000) -> None:
        pass


class MockTracer:
    """Mock Tracer for testing."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
        self.events.append(
            {
                "type": event_type,
                "data": data,
                "step_id": step_id,
            }
        )


class TestAgentRuntimeInit:
    """Tests for AgentRuntime initialization."""

    def test_init_with_backend(self) -> None:
        """Test basic initialization with backend."""
        backend = MockBackend()
        tracer = MockTracer()

        runtime = AgentRuntime(backend=backend, tracer=tracer)

        assert runtime.backend is backend
        assert runtime.tracer is tracer
        assert runtime.step_id is None
        assert runtime.step_index == 0
        assert runtime.last_snapshot is None
        assert runtime.is_task_done is False

    def test_init_with_snapshot_options(self) -> None:
        """Test initialization with custom snapshot options."""
        backend = MockBackend()
        tracer = MockTracer()
        options = SnapshotOptions(limit=100, goal="test goal")

        runtime = AgentRuntime(backend=backend, tracer=tracer, snapshot_options=options)

        assert runtime._snapshot_options.limit == 100
        assert runtime._snapshot_options.goal == "test goal"

    def test_init_with_api_key(self) -> None:
        """Test initialization with API key enables use_api."""
        backend = MockBackend()
        tracer = MockTracer()

        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            sentience_api_key="sk_test_key",
        )

        assert runtime._snapshot_options.sentience_api_key == "sk_test_key"
        assert runtime._snapshot_options.use_api is True

    def test_init_with_api_key_and_options(self) -> None:
        """Test API key merges with provided options."""
        backend = MockBackend()
        tracer = MockTracer()
        options = SnapshotOptions(limit=50)

        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            snapshot_options=options,
            sentience_api_key="sk_pro_key",
        )

        assert runtime._snapshot_options.limit == 50
        assert runtime._snapshot_options.sentience_api_key == "sk_pro_key"
        assert runtime._snapshot_options.use_api is True


class TestAgentRuntimeGetUrl:
    """Tests for get_url method."""

    @pytest.mark.asyncio
    async def test_get_url(self) -> None:
        """Test get_url returns URL from backend."""
        backend = MockBackend()
        backend._url = "https://test.example.com/page"
        tracer = MockTracer()

        runtime = AgentRuntime(backend=backend, tracer=tracer)
        url = await runtime.get_url()

        assert url == "https://test.example.com/page"
        assert runtime._cached_url == "https://test.example.com/page"


class TestAgentRuntimeBeginStep:
    """Tests for begin_step method."""

    def test_begin_step_generates_step_id(self) -> None:
        """Test begin_step generates a UUID step_id."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        step_id = runtime.begin_step(goal="Test step")

        assert step_id is not None
        assert len(step_id) == 36  # UUID length with dashes

    def test_begin_step_increments_index(self) -> None:
        """Test begin_step auto-increments step_index."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        runtime.begin_step(goal="Step 1")
        assert runtime.step_index == 1

        runtime.begin_step(goal="Step 2")
        assert runtime.step_index == 2

    def test_begin_step_explicit_index(self) -> None:
        """Test begin_step with explicit step_index."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        runtime.begin_step(goal="Custom step", step_index=10)
        assert runtime.step_index == 10

    def test_begin_step_clears_assertions(self) -> None:
        """Test begin_step clears previous assertions."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        # Add some assertions
        runtime._assertions_this_step = [{"label": "old", "passed": True}]

        runtime.begin_step(goal="New step")

        assert runtime._assertions_this_step == []


class TestAgentRuntimeAssertions:
    """Tests for assertion methods."""

    def test_assert_passing(self) -> None:
        """Test assert_ with passing predicate."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        # Create a passing predicate
        def passing_predicate(ctx: AssertContext) -> AssertOutcome:
            return AssertOutcome(passed=True, reason="Matched", details={})

        result = runtime.assert_(passing_predicate, label="test_label")

        assert result is True
        assert len(runtime._assertions_this_step) == 1
        assert runtime._assertions_this_step[0]["label"] == "test_label"
        assert runtime._assertions_this_step[0]["passed"] is True

    def test_assert_failing(self) -> None:
        """Test assert_ with failing predicate."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        def failing_predicate(ctx: AssertContext) -> AssertOutcome:
            return AssertOutcome(passed=False, reason="Not matched", details={})

        result = runtime.assert_(failing_predicate, label="fail_label")

        assert result is False
        assert runtime._assertions_this_step[0]["passed"] is False

    def test_assert_emits_event(self) -> None:
        """Test assert_ emits verification event."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        def predicate(ctx: AssertContext) -> AssertOutcome:
            return AssertOutcome(passed=True, reason="OK", details={"key": "value"})

        runtime.assert_(predicate, label="test_emit")

        assert len(tracer.events) == 1
        event = tracer.events[0]
        assert event["type"] == "verification"
        assert event["data"]["kind"] == "assert"
        assert event["data"]["passed"] is True
        assert event["data"]["label"] == "test_emit"

    def test_assert_done_marks_task_complete(self) -> None:
        """Test assert_done marks task as done on success."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        def passing_predicate(ctx: AssertContext) -> AssertOutcome:
            return AssertOutcome(passed=True, reason="Done", details={})

        result = runtime.assert_done(passing_predicate, label="task_complete")

        assert result is True
        assert runtime.is_task_done is True
        assert runtime._task_done_label == "task_complete"

    def test_assert_done_does_not_mark_on_failure(self) -> None:
        """Test assert_done doesn't mark task done on failure."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        def failing_predicate(ctx: AssertContext) -> AssertOutcome:
            return AssertOutcome(passed=False, reason="Not done", details={})

        result = runtime.assert_done(failing_predicate, label="task_incomplete")

        assert result is False
        assert runtime.is_task_done is False

    @pytest.mark.asyncio
    async def test_check_eventually_records_final_only(self) -> None:
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        # Two failing snapshots, then success
        snaps = [
            MagicMock(url="https://example.com", elements=[]),
            MagicMock(url="https://example.com", elements=[]),
            MagicMock(url="https://example.com/done", elements=[]),
        ]

        async def fake_snapshot(**_kwargs):
            runtime.last_snapshot = snaps.pop(0)
            return runtime.last_snapshot

        runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

        def pred(ctx: AssertContext) -> AssertOutcome:
            ok = (ctx.url or "").endswith("/done")
            return AssertOutcome(
                passed=ok,
                reason="" if ok else "not done",
                details={"selector": "text~'Done'", "reason_code": "ok" if ok else "no_match"},
            )

        handle = runtime.check(pred, label="eventually_done")
        ok = await handle.eventually(timeout_s=2.0, poll_s=0.0)
        assert ok is True

        # Only the final record is accumulated for step_end
        assert len(runtime._assertions_this_step) == 1
        assert runtime._assertions_this_step[0]["label"] == "eventually_done"
        assert runtime._assertions_this_step[0]["passed"] is True
        assert runtime._assertions_this_step[0].get("final") is True

        # But attempts emitted multiple verification events
        assert len(tracer.events) >= 3
        assert all(e["type"] == "verification" for e in tracer.events)

    @pytest.mark.asyncio
    async def test_check_eventually_snapshot_exhausted_min_confidence(self) -> None:
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        low_diag = MagicMock()
        low_diag.confidence = 0.1
        low_diag.model_dump = lambda: {"confidence": 0.1}

        snaps = [
            MagicMock(url="https://example.com", elements=[], diagnostics=low_diag),
            MagicMock(url="https://example.com", elements=[], diagnostics=low_diag),
        ]

        async def fake_snapshot(**_kwargs):
            runtime.last_snapshot = snaps.pop(0)
            return runtime.last_snapshot

        runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

        def pred(_ctx: AssertContext) -> AssertOutcome:
            return AssertOutcome(passed=True, reason="would pass", details={})

        handle = runtime.check(pred, label="min_confidence_gate")
        ok = await handle.eventually(
            timeout_s=5.0,
            poll_s=0.0,
            min_confidence=0.7,
            max_snapshot_attempts=2,
        )
        assert ok is False

        # Only the final record is accumulated for step_end
        assert len(runtime._assertions_this_step) == 1
        details = runtime._assertions_this_step[0]["details"]
        assert details["reason_code"] == "snapshot_exhausted"

    @pytest.mark.asyncio
    async def test_check_eventually_vision_fallback_on_exhaustion(self) -> None:
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        low_diag = MagicMock()
        low_diag.confidence = 0.1
        low_diag.model_dump = lambda: {"confidence": 0.1}

        async def fake_snapshot(**_kwargs):
            runtime.last_snapshot = MagicMock(
                url="https://example.com", elements=[], diagnostics=low_diag
            )
            return runtime.last_snapshot

        runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

        class VisionProviderStub:
            def supports_vision(self) -> bool:
                return True

            def generate_with_image(self, *_args, **_kwargs):
                return MagicMock(content="YES")

        def pred(_ctx: AssertContext) -> AssertOutcome:
            return AssertOutcome(passed=False, reason="should not run", details={})

        handle = runtime.check(pred, label="vision_fallback_check")
        ok = await handle.eventually(
            timeout_s=5.0,
            poll_s=0.0,
            min_confidence=0.7,
            max_snapshot_attempts=1,
            vision_provider=VisionProviderStub(),
        )
        assert ok is True
        assert len(runtime._assertions_this_step) == 1
        rec = runtime._assertions_this_step[0]
        assert rec.get("vision_fallback") is True
        assert rec["details"]["reason_code"] == "vision_fallback_pass"


class TestAgentRuntimeAssertionHelpers:
    """Tests for assertion helper methods."""

    def test_all_assertions_passed_empty(self) -> None:
        """Test all_assertions_passed with no assertions."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        assert runtime.all_assertions_passed() is True

    def test_all_assertions_passed_true(self) -> None:
        """Test all_assertions_passed when all pass."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._assertions_this_step = [
            {"passed": True},
            {"passed": True},
        ]

        assert runtime.all_assertions_passed() is True

    def test_all_assertions_passed_false(self) -> None:
        """Test all_assertions_passed when one fails."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._assertions_this_step = [
            {"passed": True},
            {"passed": False},
        ]

        assert runtime.all_assertions_passed() is False

    def test_required_assertions_passed(self) -> None:
        """Test required_assertions_passed ignores optional failures."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._assertions_this_step = [
            {"passed": True, "required": True},
            {"passed": False, "required": False},  # Optional failure
        ]

        assert runtime.required_assertions_passed() is True

    def test_required_assertions_failed(self) -> None:
        """Test required_assertions_passed fails on required failure."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._assertions_this_step = [
            {"passed": True, "required": True},
            {"passed": False, "required": True},  # Required failure
        ]

        assert runtime.required_assertions_passed() is False


class TestAgentRuntimeFlushAssertions:
    """Tests for flush_assertions method."""

    def test_flush_assertions(self) -> None:
        """Test flush_assertions returns and clears assertions."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._assertions_this_step = [
            {"label": "a", "passed": True},
            {"label": "b", "passed": False},
        ]

        assertions = runtime.flush_assertions()

        assert len(assertions) == 2
        assert assertions[0]["label"] == "a"
        assert runtime._assertions_this_step == []


class TestAgentRuntimeGetAssertionsForStepEnd:
    """Tests for get_assertions_for_step_end method."""

    def test_get_assertions_basic(self) -> None:
        """Test get_assertions_for_step_end returns assertions."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._assertions_this_step = [{"label": "test", "passed": True}]

        result = runtime.get_assertions_for_step_end()

        assert "assertions" in result
        assert len(result["assertions"]) == 1
        assert "task_done" not in result

    def test_get_assertions_with_task_done(self) -> None:
        """Test get_assertions_for_step_end includes task_done."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._task_done = True
        runtime._task_done_label = "completed"

        result = runtime.get_assertions_for_step_end()

        assert result["task_done"] is True
        assert result["task_done_label"] == "completed"


class TestAgentRuntimeResetTaskDone:
    """Tests for reset_task_done method."""

    def test_reset_task_done(self) -> None:
        """Test reset_task_done clears task state."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._task_done = True
        runtime._task_done_label = "was_done"

        runtime.reset_task_done()

        assert runtime.is_task_done is False
        assert runtime._task_done_label is None


class TestAgentRuntimeContext:
    """Tests for _ctx method."""

    def test_ctx_with_snapshot(self) -> None:
        """Test _ctx uses snapshot URL."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime.begin_step(goal="Test")

        # Mock snapshot with URL
        mock_snapshot = MagicMock()
        mock_snapshot.url = "https://snapshot-url.com"
        runtime.last_snapshot = mock_snapshot

        ctx = runtime._ctx()

        assert ctx.url == "https://snapshot-url.com"
        assert ctx.snapshot is mock_snapshot
        assert ctx.step_id == runtime.step_id

    def test_ctx_fallback_to_cached_url(self) -> None:
        """Test _ctx falls back to cached URL."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)
        runtime._cached_url = "https://cached-url.com"
        runtime.begin_step(goal="Test")

        ctx = runtime._ctx()

        assert ctx.url == "https://cached-url.com"
        assert ctx.snapshot is None


class TestAgentRuntimeFromSentienceBrowser:
    """Tests for from_sentience_browser factory method."""

    @pytest.mark.asyncio
    async def test_from_sentience_browser_creates_runtime(self) -> None:
        """Test from_sentience_browser creates runtime with legacy support."""
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        tracer = MockTracer()

        with patch("sentience.backends.playwright_backend.PlaywrightBackend") as MockPWBackend:
            mock_backend_instance = MagicMock()
            MockPWBackend.return_value = mock_backend_instance

            runtime = await AgentRuntime.from_sentience_browser(
                browser=mock_browser,
                page=mock_page,
                tracer=tracer,
            )

            assert runtime.backend is mock_backend_instance
            assert runtime._legacy_browser is mock_browser
            assert runtime._legacy_page is mock_page
            MockPWBackend.assert_called_once_with(mock_page)

    @pytest.mark.asyncio
    async def test_from_sentience_browser_with_api_key(self) -> None:
        """Test from_sentience_browser passes API key."""
        mock_browser = MagicMock()
        mock_page = MagicMock()
        tracer = MockTracer()

        with patch("sentience.backends.playwright_backend.PlaywrightBackend"):
            runtime = await AgentRuntime.from_sentience_browser(
                browser=mock_browser,
                page=mock_page,
                tracer=tracer,
                sentience_api_key="sk_test",
            )

            assert runtime._snapshot_options.sentience_api_key == "sk_test"
            assert runtime._snapshot_options.use_api is True


class TestAgentRuntimeSnapshot:
    """Tests for snapshot method."""

    @pytest.mark.asyncio
    async def test_snapshot_with_legacy_browser(self) -> None:
        """Test snapshot uses legacy browser when available."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        # Set up legacy browser
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_snapshot = MagicMock()
        mock_browser.snapshot = AsyncMock(return_value=mock_snapshot)

        runtime._legacy_browser = mock_browser
        runtime._legacy_page = mock_page

        result = await runtime.snapshot(limit=30)

        mock_browser.snapshot.assert_called_once_with(mock_page, limit=30)
        assert result is mock_snapshot
        assert runtime.last_snapshot is mock_snapshot

    @pytest.mark.asyncio
    async def test_snapshot_with_backend(self) -> None:
        """Test snapshot uses backend-agnostic snapshot."""
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        mock_snapshot = MagicMock()

        with patch("sentience.backends.snapshot.snapshot", new_callable=AsyncMock) as mock_snap_fn:
            mock_snap_fn.return_value = mock_snapshot

            result = await runtime.snapshot(goal="test goal")

            mock_snap_fn.assert_called_once()
            call_args = mock_snap_fn.call_args
            assert call_args[0][0] is backend
            assert call_args[1]["options"].goal == "test goal"
            assert result is mock_snapshot
            assert runtime.last_snapshot is mock_snapshot

    @pytest.mark.asyncio
    async def test_snapshot_merges_options(self) -> None:
        """Test snapshot merges default and call-specific options."""
        backend = MockBackend()
        tracer = MockTracer()
        default_options = SnapshotOptions(limit=100, screenshot=True)
        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            snapshot_options=default_options,
        )

        with patch("sentience.backends.snapshot.snapshot", new_callable=AsyncMock) as mock_snap_fn:
            mock_snap_fn.return_value = MagicMock()

            await runtime.snapshot(goal="override goal")

            call_args = mock_snap_fn.call_args
            options = call_args[1]["options"]
            assert options.limit == 100  # From default
            assert options.screenshot is True  # From default
            assert options.goal == "override goal"  # From call
