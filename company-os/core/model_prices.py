"""Model price table (USD per million tokens) and the cost of one call."""

# name: (input, output). Cache read is 0.1x input, cache write is 1.25x input.
PRICES = {
    "opus-5-5": (4.0, 20.0),
    "sonnet-5-5": (2.0, 10.0),
    "haiku-5-5": (0.10, 0.50),
}
ALIASES = {"fake": "sonnet-5-5", "claude-cli": "sonnet-5-5"}
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25


def price_name(model: str) -> str:
    name = ALIASES.get(model, model)
    if name not in PRICES:
        raise KeyError(f"no price for model {model!r}")
    return name


def cost_usd(model: str, usage) -> float:
    """input_tokens counts only the uncached part; cache tokens are priced on their own."""
    inp, out = PRICES[price_name(model)]
    total = (
        usage.input_tokens * inp
        + usage.output_tokens * out
        + usage.cache_read_tokens * inp * CACHE_READ_FACTOR
        + usage.cache_write_tokens * inp * CACHE_WRITE_FACTOR
    )
    return total / 1_000_000
