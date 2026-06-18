"""Unit tests for the replay engine's tool-override rewriting."""

from __future__ import annotations

import pytest

from peekai.core.storage import Storage
from peekai.replay.engine import ReplayEngine


@pytest.fixture
def engine(tmp_path):
    return ReplayEngine(
        storage=Storage(tmp_path / "replay.db"),
        tool_overrides={"search": "FAKE RESULT"},
    )


def test_tool_override_rewrites_matching_message(engine):
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "name": "search", "content": "real result"},
        {"role": "tool", "name": "calculator", "content": "42"},
    ]
    out = engine._apply_tool_overrides(messages)

    assert out[1]["content"] == "FAKE RESULT"   # overridden
    assert out[2]["content"] == "42"            # untouched
    assert out[0]["content"] == "hi"            # untouched
    # Original messages must not be mutated in place.
    assert messages[1]["content"] == "real result"


def test_function_role_is_also_matched(engine):
    messages = [{"role": "function", "name": "search", "content": "x"}]
    assert engine._apply_tool_overrides(messages)[0]["content"] == "FAKE RESULT"


def test_no_overrides_returns_input_unchanged(tmp_path):
    engine = ReplayEngine(storage=Storage(tmp_path / "r.db"))
    messages = [{"role": "tool", "name": "search", "content": "x"}]
    assert engine._apply_tool_overrides(messages) is messages
