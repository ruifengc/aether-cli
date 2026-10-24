"""CLI-owned environment and local configuration discovery."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from aether.chat import Settings


def load_settings(*, env_file: Path | None = None, provider: str | None = None,
                  model: str | None = None, reasoning: str | None = None) -> Settings:
    """Read an allowlist as data; never source/execute an environment file."""
    allowed = {"TOKENHUB_API_KEY", "TENCENT_API_KEY", "TOKENHUB_BASE_URL", "DEEPSEEK_API_KEY",
               "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "LLM_PROVIDER", "LLM_PRO_MODEL",
               "LLM_PRO_REASONING_EFFORT", "QUERY_AGENT_MODEL"}
    values = {key: value for key, value in os.environ.items() if key in allowed}
    path = env_file or Path.home() / ".hermes" / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)", line)
            if match and match[1] in allowed:
                parts = shlex.split(match[2], comments=True)
                if parts:
                    values.setdefault(match[1], " ".join(parts))
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
