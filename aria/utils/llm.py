"""
Unified LLM client — supports Anthropic (Claude) and OpenAI (GPT).
Set LLM_PROVIDER=openai or LLM_PROVIDER=anthropic in your .env.
Auto-detects based on which API key is set if LLM_PROVIDER is not specified.
"""
from aria.config import Config
from aria.utils.rate_limiter import anthropic_limiter

# Model tiers:
#   "fast"    → cheap/fast  (Haiku / gpt-4o-mini)
#   "quality" → best        (Sonnet / gpt-4o)

_ANTHROPIC_MODELS = {
    "fast": "claude-haiku-4-5-20251001",
    "quality": "claude-sonnet-4-6",
}

_OPENAI_MODELS = {
    "fast": "gpt-4o-mini",
    "quality": "gpt-4o",
}

_anthropic_client = None
_openai_client = None


def _provider() -> str:
    p = Config.LLM_PROVIDER.lower() if Config.LLM_PROVIDER else ""
    if p in ("anthropic", "openai"):
        return p
    # Auto-detect
    if Config.ANTHROPIC_API_KEY:
        return "anthropic"
    if Config.OPENAI_API_KEY:
        return "openai"
    raise RuntimeError(
        "No LLM API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your .env"
    )


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return _openai_client


def call_llm(prompt: str, tier: str = "fast", max_tokens: int = 512) -> str:
    """
    Call the configured LLM. Returns the response text.

    Args:
        prompt: The user prompt string.
        tier: "fast" (cheap) or "quality" (best).
        max_tokens: Max tokens to generate.
    """
    provider = _provider()

    if provider == "anthropic":
        anthropic_limiter.wait()
        client = _get_anthropic()
        model = _ANTHROPIC_MODELS[tier]
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    else:  # openai
        client = _get_openai()
        model = _OPENAI_MODELS[tier]
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
