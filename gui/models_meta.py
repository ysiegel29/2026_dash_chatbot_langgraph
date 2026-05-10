# Provider → model list shown in the UI.
# Mirrors agent/models.py PROVIDER_MODELS but kept separate so the GUI
# doesn't import the agent package (avoids pulling in LangChain at GUI startup).

PROVIDER_MODELS: dict[str, list[str]] = {
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
