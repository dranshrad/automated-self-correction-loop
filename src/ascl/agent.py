# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM orchestration layer (Anthropic, OpenAI, Mock)."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Sequence

from ascl.models import ChatMessage, ProviderName

DEFAULT_MODELS: dict[ProviderName, str] = {
    ProviderName.ANTHROPIC: "claude-sonnet-4-20250514",
    ProviderName.OPENAI: "gpt-4o",
    ProviderName.MOCK: "mock-v1",
}


class AgentError(RuntimeError):
    """Raised when the LLM provider cannot complete a request."""


class Agent(ABC):
    """Thin provider interface used by the correction loop."""

    provider: ProviderName
    model: str

    @abstractmethod
    def complete(self, messages: Sequence[ChatMessage]) -> str:
        """Return the assistant text for the given messages."""


class AnthropicAgent(Agent):
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.provider = ProviderName.ANTHROPIC
        self.model = model or DEFAULT_MODELS[ProviderName.ANTHROPIC]
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise AgentError("ANTHROPIC_API_KEY is not set")
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover
            raise AgentError("anthropic package is not installed") from exc
        self._client = Anthropic(api_key=key)

    def complete(self, messages: Sequence[ChatMessage]) -> str:
        system = ""
        chat: list[dict[str, str]] = []
        for message in messages:
            if message.role == "system":
                system = message.content
            else:
                chat.append({"role": message.role, "content": message.content})
        if not chat:
            raise AgentError("No user/assistant messages provided")
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system or "You are a helpful coding assistant.",
                messages=chat,  # type: ignore[arg-type]
            )
        except Exception as exc:
            raise AgentError(f"Anthropic request failed: {exc}") from exc
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        if not parts:
            raise AgentError("Anthropic returned an empty response")
        return "\n".join(parts)


class OpenAIAgent(Agent):
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.provider = ProviderName.OPENAI
        self.model = model or DEFAULT_MODELS[ProviderName.OPENAI]
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise AgentError("OPENAI_API_KEY is not set")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise AgentError("openai package is not installed") from exc
        self._client = OpenAI(api_key=key)

    def complete(self, messages: Sequence[ChatMessage]) -> str:
        payload = [message.to_dict() for message in messages]
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=payload,  # type: ignore[arg-type]
                temperature=0.2,
            )
        except Exception as exc:
            raise AgentError(f"OpenAI request failed: {exc}") from exc
        choice = response.choices[0].message.content
        if not choice:
            raise AgentError("OpenAI returned an empty response")
        return choice


class MockAgent(Agent):
    """
    Deterministic provider for CI and demos.

    Response sequence can be injected; otherwise a minimal successful script
    or a heal-oriented fibonacci fix sequence is used.
    """

    def __init__(
        self,
        model: str | None = None,
        responses: Sequence[str] | None = None,
    ) -> None:
        self.provider = ProviderName.MOCK
        self.model = model or DEFAULT_MODELS[ProviderName.MOCK]
        self._responses = list(responses) if responses is not None else []
        self._index = 0
        self.call_count = 0

    def complete(self, messages: Sequence[ChatMessage]) -> str:
        self.call_count += 1
        if self._responses:
            if self._index >= len(self._responses):
                return self._responses[-1]
            response = self._responses[self._index]
            self._index += 1
            return response

        joined = "\n".join(message.content for message in messages).lower()
        if "fibonacci" in joined or "fib" in joined:
            return self._fibonacci_response(joined)
        if "pytest" in joined or "heal" in joined or "from solution import" in joined:
            return "```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```"
        return "```python\nprint('hello from ascl mock')\n```"

    def _fibonacci_response(self, joined: str) -> str:
        # First attempt intentionally wrong; subsequent attempts correct.
        if self.call_count == 1 and "latest failure" not in joined:
            return (
                "```python\n"
                "def fib(n: int) -> int:\n"
                "    if n < 0:\n"
                "        raise ValueError('n must be non-negative')\n"
                "    if n < 2:\n"
                "        return n\n"
                "    return fib(n - 1) + fib(n - 2) + 1  # intentional bug\n"
                "```"
            )
        return (
            "```python\n"
            "def fib(n: int) -> int:\n"
            "    if n < 0:\n"
            "        raise ValueError('n must be non-negative')\n"
            "    if n < 2:\n"
            "        return n\n"
            "    a, b = 0, 1\n"
            "    for _ in range(2, n + 1):\n"
            "        a, b = b, a + b\n"
            "    return b\n"
            "```"
        )


def create_agent(
    provider: ProviderName | str,
    *,
    model: str | None = None,
    mock_responses: Sequence[str] | None = None,
) -> Agent:
    """Factory for provider agents."""
    name = ProviderName(provider) if isinstance(provider, str) else provider
    if name is ProviderName.ANTHROPIC:
        return AnthropicAgent(model=model)
    if name is ProviderName.OPENAI:
        return OpenAIAgent(model=model)
    if name is ProviderName.MOCK:
        return MockAgent(model=model, responses=mock_responses)
    raise AgentError(f"Unsupported provider: {provider}")
