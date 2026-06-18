"""
Token cost calculation per model.

Prices are in USD per 1,000 tokens (input, output).

Lookup order for a model name:
  1. Exact match against the table below.
  2. Longest table key that is a prefix of the model name — this catches
     version/date-suffixed and "-latest" names (e.g. "gpt-4o-2024-08-06",
     "claude-3-5-sonnet-latest").
  3. LiteLLM's pricing map, if litellm is already imported — covers everything
     else with up-to-date numbers without forcing a heavy import.
  4. 0.0 if the model is still unknown.
"""

from __future__ import annotations

import sys

# (input_cost_per_1k, output_cost_per_1k)
_PRICES: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-4": (0.03, 0.06),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "o1": (0.015, 0.06),
    "o1-mini": (0.003, 0.012),
    "o3-mini": (0.0011, 0.0044),
    # Anthropic — full dated ids
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-3-5-haiku-20241022": (0.0008, 0.004),
    "claude-3-opus-20240229": (0.015, 0.075),
    "claude-3-sonnet-20240229": (0.003, 0.015),
    "claude-3-haiku-20240307": (0.00025, 0.00125),
    # Anthropic — family base names, so "-latest" / other dates resolve via the
    # prefix fallback to the right family price.
    "claude-3-5-sonnet": (0.003, 0.015),
    "claude-3-5-haiku": (0.0008, 0.004),
    "claude-3-opus": (0.015, 0.075),
    "claude-3-sonnet": (0.003, 0.015),
    "claude-3-haiku": (0.00025, 0.00125),
}


def _normalise(model: str) -> str:
    """Strip provider prefixes like 'openai/gpt-4o' and lowercase."""
    return model.split("/")[-1].lower().strip()


def _prefix_match(normalised: str) -> tuple[float, float] | None:
    """Return the price for the longest table key that prefixes the model."""
    candidates = [key for key in _PRICES if normalised.startswith(key)]
    if not candidates:
        return None
    return _PRICES[max(candidates, key=len)]


def _litellm_price(normalised: str) -> tuple[float, float] | None:
    """Fall back to LiteLLM's cost map, but only if it is already imported.

    Avoids triggering a slow `import litellm` just to price a token; users who
    actually use litellm will already have it loaded.
    """
    litellm = sys.modules.get("litellm")
    if litellm is None:
        return None
    try:
        cost_map = getattr(litellm, "model_cost", {})
        info = cost_map.get(normalised) or cost_map.get(normalised.split("/")[-1])
        if not info:
            return None
        in_per_token = info.get("input_cost_per_token")
        out_per_token = info.get("output_cost_per_token")
        if in_per_token is None or out_per_token is None:
            return None
        return (in_per_token * 1000, out_per_token * 1000)
    except Exception:
        return None


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Return the estimated cost in USD for a given model and token counts.
    Returns 0.0 if the model cannot be priced.
    """
    normalised = _normalise(model)
    prices = (
        _PRICES.get(normalised)
        or _prefix_match(normalised)
        or _litellm_price(normalised)
    )
    if prices is None:
        return 0.0
    input_cost = (input_tokens / 1000) * prices[0]
    output_cost = (output_tokens / 1000) * prices[1]
    return round(input_cost + output_cost, 8)


def get_known_models() -> list[str]:
    """Return all models with known pricing."""
    return list(_PRICES.keys())
