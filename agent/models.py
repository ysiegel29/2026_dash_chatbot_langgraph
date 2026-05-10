import os
from typing import Any

from langchain_core.language_models import BaseChatModel

DEFAULT_MODEL_CONFIG = {
    "provider": "openai",
    "model": "gpt-4o",
    "temperature": 0.7,
}

PROVIDER_MODELS = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o1",
        "o3-mini",
    ],
    "anthropic": [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "oss": [
        "gpt-oss-120",
        "llama3.3:70b",
        "qwen2.5:72b",
    ],
}


def get_model(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    **kwargs: Any,
) -> BaseChatModel:
    provider = provider or os.environ.get("LLM_PROVIDER", DEFAULT_MODEL_CONFIG["provider"])
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL_CONFIG["model"])

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, **kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=temperature, **kwargs)

    if provider == "oss":
        from langchain_openai import ChatOpenAI
        base_url = os.environ.get("OSS_BASE_URL", "http://localhost:11434/v1")
        api_key = os.environ.get("OSS_API_KEY", "none")
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=base_url,
            api_key=api_key,
            **kwargs,
        )

    raise ValueError(f"Unknown provider '{provider}'. Choose: openai | anthropic | oss")
