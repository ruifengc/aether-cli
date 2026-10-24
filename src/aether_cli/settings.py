"""CLI settings from explicit options and the process environment."""

from __future__ import annotations

import os

from aether.chat import Settings


def load_settings(*, provider: str | None = None,
                  model: str | None = None, reasoning: str | None = None) -> Settings:
    """Read the host-provided environment; never discover or read configuration files."""
    allowed = {"TOKENHUB_API_KEY", "TENCENT_API_KEY", "TOKENHUB_BASE_URL", "DEEPSEEK_API_KEY",
               "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "LLM_PROVIDER", "LLM_PRO_MODEL",
               "LLM_PRO_REASONING_EFFORT", "QUERY_AGENT_MODEL"}
    values = {key: value for key, value in os.environ.items() if key in allowed}
    provider = provider or values.get("LLM_PROVIDER", "tencent")
    if provider == "tencent":
        key = values.get("TOKENHUB_API_KEY") or values.get("TENCENT_API_KEY", "")
        url = values.get("TOKENHUB_BASE_URL", "https://tokenhub.tencentmaas.com/v1")
        selected = model or values.get("QUERY_AGENT_MODEL") or values.get("LLM_PRO_MODEL")
        selected = selected or "deepseek/deepseek-flash"
    elif provider == "deepseek":
        key = values.get("DEEPSEEK_API_KEY", "")
        url = values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        selected = model or values.get("DEEPSEEK_MODEL") or "deepseek-v4-pro"
    else:
        raise ValueError("supported providers: tencent, deepseek")
    if not key:
        raise ValueError(f"no credential configured for {provider}")
    return Settings(key, url.rstrip("/"), selected, provider,
                    reasoning if reasoning is not None else
                    (values.get("LLM_PRO_REASONING_EFFORT") or "high"))
