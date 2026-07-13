# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared dataclasses for the correction loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ProviderName(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    MOCK = "mock"


class Mode(StrEnum):
    RUN = "run"
    HEAL = "heal"


class ExitReason(StrEnum):
    SUCCESS = "success"
    MAX_ITERATIONS = "max_iterations"
    CONFIG_ERROR = "config_error"
    INTERRUPTED = "interrupted"
    PARSE_ERROR = "parse_error"


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of an isolated subprocess run."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: float
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of a success-gate check."""

    success: bool
    summary: str
    details: str = ""
    execution: ExecutionResult | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "success": self.success,
            "summary": self.summary,
            "details": self.details,
            "execution": self.execution.to_dict() if self.execution else None,
        }
        return payload


@dataclass
class IterationRecord:
    """One generate → execute → verify cycle."""

    iteration: int
    code: str
    verification: VerificationResult
    prompt_tokens_estimate: int = 0
    raw_model_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "code": self.code,
            "verification": self.verification.to_dict(),
            "prompt_tokens_estimate": self.prompt_tokens_estimate,
            "raw_model_response": self.raw_model_response,
        }


@dataclass
class RunReport:
    """Persisted end-of-run artifact."""

    mode: Mode
    prompt: str
    max_iterations: int
    timeout_seconds: float
    provider: ProviderName
    model: str
    exit_reason: ExitReason
    iterations: list[IterationRecord] = field(default_factory=list)
    final_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "prompt": self.prompt,
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
            "provider": self.provider.value,
            "model": self.model,
            "exit_reason": self.exit_reason.value,
            "iterations": [item.to_dict() for item in self.iterations],
            "final_code": self.final_code,
        }


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}
