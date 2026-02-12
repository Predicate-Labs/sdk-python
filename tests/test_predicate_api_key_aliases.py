# pylint: disable=protected-access
from unittest.mock import MagicMock

from predicate.agent_runtime import AgentRuntime
from predicate.models import SnapshotOptions


def test_snapshot_options_accepts_predicate_api_key() -> None:
    opts = SnapshotOptions(predicate_api_key="pk_test")
    assert opts.predicate_api_key == "pk_test"
    assert opts.sentience_api_key == "pk_test"


def test_snapshot_options_keeps_backward_compatible_sentience_api_key() -> None:
    opts = SnapshotOptions(sentience_api_key="sk_test")
    assert opts.sentience_api_key == "sk_test"
    assert opts.predicate_api_key == "sk_test"


def test_agent_runtime_accepts_predicate_api_key() -> None:
    runtime = AgentRuntime(
        backend=MagicMock(),
        tracer=MagicMock(),
        predicate_api_key="pk_runtime",
    )
    assert runtime._snapshot_options.predicate_api_key == "pk_runtime"
    assert runtime._snapshot_options.sentience_api_key == "pk_runtime"


def test_agent_runtime_prefers_predicate_api_key_when_both_provided() -> None:
    runtime = AgentRuntime(
        backend=MagicMock(),
        tracer=MagicMock(),
        predicate_api_key="pk_new",
        sentience_api_key="sk_old",
    )
    assert runtime._snapshot_options.predicate_api_key == "pk_new"
    assert runtime._snapshot_options.sentience_api_key == "pk_new"
