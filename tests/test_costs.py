"""Unit tests for cost calculation, including the prefix + litellm fallbacks."""

from __future__ import annotations

import sys
import types

from peekai.core.costs import calculate_cost


def test_exact_match():
    # gpt-4o: 0.005 in / 0.015 out per 1k tokens
    assert calculate_cost("gpt-4o", 1000, 1000) == round(0.005 + 0.015, 8)


def test_provider_prefix_is_stripped():
    assert calculate_cost("openai/gpt-4o", 1000, 0) == round(0.005, 8)


def test_versioned_openai_name_resolves_via_prefix():
    # Dated id should resolve to the gpt-4o family price, not 0.
    assert calculate_cost("gpt-4o-2024-08-06", 1000, 0) == round(0.005, 8)


def test_claude_latest_resolves_to_family_base():
    # "-latest" should resolve to the claude-3-5-sonnet base price.
    assert calculate_cost("claude-3-5-sonnet-latest", 1000, 1000) == round(
        0.003 + 0.015, 8
    )


def test_longest_prefix_wins():
    # gpt-4o-mini must match the mini price, not gpt-4o.
    assert calculate_cost("gpt-4o-mini-2024-07-18", 1000, 0) == round(0.00015, 8)


def test_unknown_model_returns_zero():
    assert calculate_cost("totally-unknown-model-xyz", 1000, 1000) == 0.0


def test_litellm_fallback_used_when_imported(monkeypatch):
    stub = types.SimpleNamespace(
        model_cost={
            "weird-model": {
                "input_cost_per_token": 0.001,
                "output_cost_per_token": 0.002,
            }
        }
    )
    monkeypatch.setitem(sys.modules, "litellm", stub)
    # 0.001/token -> 1.0 per 1k; 0.002/token -> 2.0 per 1k
    assert calculate_cost("weird-model", 1000, 1000) == round(1.0 + 2.0, 8)
