"""
Token cost calculation per model.

Prices are in USD per 1,000 tokens (input, output).
Update this table as providers change pricing.
"""

from __future__ import annotations

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
    # Anthropic
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-3-5-haiku-20241022": (0.0008, 0.004),
    "claude-3-opus-20240229": (0.015, 0.075),
    "claude-3-sonnet-20240229": (0.003, 0.015),
    "claude-3-haiku-20240307": (0.00025, 0.00125),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Return the estimated cost in USD for a given model and token counts.
    Returns 0.0 if the model is not in the price table.
    """
    # Normalise model name — strip provider prefixes like "openai/gpt-4o"
    normalised = model.split("/")[-1].lower().strip()
    prices = _PRICES.get(normalised)
    if prices is None:
        return 0.0
    input_cost = (input_tokens / 1000) * prices[0]
    output_cost = (output_tokens / 1000) * prices[1]
    return round(input_cost + output_cost, 8)


def get_known_models() -> list[str]:
    """Return all models with known pricing."""
    return list(_PRICES.keys())
