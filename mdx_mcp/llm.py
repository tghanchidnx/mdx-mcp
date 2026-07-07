"""LLM provider seam — the ``LLMClient`` Protocol + a Claude reference client.

Provider-agnostic: the engine only needs ``complete(prompt) -> str``. ``ClaudeClient`` is the
recommended default (Anthropic). OSS users can supply any implementation (OpenAI, local, …).
``anthropic`` is imported lazily so the package installs and unit-tests without it.
"""
from __future__ import annotations

import os
from typing import Optional, Protocol


class LLMClient(Protocol):
    """Complete a prompt into text (the model returns bare MDX, per the producer prompt)."""

    def complete(self, prompt: str) -> str:  # pragma: no cover - protocol
        ...


class ClaudeClient:
    """Reference ``LLMClient`` backed by Anthropic Claude.

    Defaults to a current Claude model; override via ``model`` or ``MDX_MCP_MODEL``.
    Reads the API key from ``ANTHROPIC_API_KEY`` unless passed explicitly.
    """

    def __init__(self, model: Optional[str] = None, *, api_key: Optional[str] = None,
                 max_tokens: int = 1024, temperature: float = 0.7) -> None:
        self.model = model or os.environ.get("MDX_MCP_MODEL", "claude-opus-4-8")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    def _ensure(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("ClaudeClient needs the 'anthropic' package "
                                   "(`pip install mdx-mcp[claude]`)") from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, prompt: str) -> str:
        client = self._ensure()
        msg = client.messages.create(
            model=self.model, max_tokens=self.max_tokens, temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(b, "text", "") for b in msg.content)
