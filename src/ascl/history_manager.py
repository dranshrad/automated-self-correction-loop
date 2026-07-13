# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Token-aware rolling window for recursive error history."""

from __future__ import annotations

from dataclasses import dataclass, field

from ascl.models import ChatMessage, IterationRecord

DEFAULT_MAX_CONTEXT_TOKENS = 8000
_COMPRESS_AFTER_ITERATION = 3


def estimate_tokens(text: str) -> int:
    """Heuristic token estimate without tiktoken (chars / 4)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class HistoryManager:
    """
    Builds LLM message lists under a hard token budget.

    Always preserves:
    - system rules
    - original user prompt
    - latest failing code + crash/pytest log

    After iteration > 3, older failures collapse to one-line summaries.
    """

    system_prompt: str
    user_prompt: str
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    _summaries: list[str] = field(default_factory=list)

    def ingest_failure(self, record: IterationRecord) -> None:
        """Record a failed iteration for later prompt assembly."""
        summary = _summarize_iteration(record)
        self._summaries.append(summary)

    def build_messages(
        self,
        *,
        iteration: int,
        previous_code: str | None,
        latest_failure: str | None,
    ) -> list[ChatMessage]:
        """Assemble system + user(+correction) messages within budget."""
        system = ChatMessage(role="system", content=self.system_prompt)

        parts: list[str] = [
            f"## Original task\n{self.user_prompt}",
            f"## Iteration\n{iteration}",
        ]

        if previous_code:
            parts.append(f"## Previous code\n```python\n{previous_code}\n```")

        older = self._older_summaries(iteration)
        if older:
            parts.append("## Earlier failures (compressed)\n" + "\n".join(older))

        if latest_failure:
            parts.append(
                "## Latest failure (full)\n"
                "Treat this as a systemic correction directive and return a complete "
                "corrected script in a single ```python``` fence.\n\n"
                f"{latest_failure}"
            )
        else:
            parts.append(
                "## Instruction\n"
                "Return a complete Python solution in a single ```python``` fence. "
                "Do not omit code."
            )

        user_content = "\n\n".join(parts)
        user_content = self._fit_to_budget(system.content, user_content)
        return [system, ChatMessage(role="user", content=user_content)]

    def estimate_prompt_tokens(self, messages: list[ChatMessage]) -> int:
        return sum(estimate_tokens(message.content) for message in messages)

    def _older_summaries(self, iteration: int) -> list[str]:
        if iteration <= _COMPRESS_AFTER_ITERATION or not self._summaries:
            # Still surface prior summaries when we have them, but keep full latest
            # failure separate via latest_failure argument.
            if len(self._summaries) <= 1:
                return []
            return self._summaries[:-1]
        # Compress everything except the most recent summary line.
        return self._summaries[:-1]

    def _fit_to_budget(self, system_text: str, user_text: str) -> str:
        budget = self.max_context_tokens - estimate_tokens(system_text)
        if budget < 256:
            budget = 256
        if estimate_tokens(user_text) <= budget:
            return user_text

        # Drop older compressed lines first, then truncate the middle of the body.
        lines = user_text.splitlines()
        compressed_idx = next(
            (i for i, line in enumerate(lines) if line.startswith("## Earlier failures")),
            None,
        )
        if compressed_idx is not None:
            # Remove the compressed section entirely if over budget.
            end = compressed_idx + 1
            while end < len(lines) and not lines[end].startswith("## "):
                end += 1
            trimmed = lines[:compressed_idx] + lines[end:]
            user_text = "\n".join(trimmed)
            if estimate_tokens(user_text) <= budget:
                return user_text

        # Hard clip from the middle while preserving head (task) and tail (latest failure).
        chars_budget = budget * 4
        if len(user_text) <= chars_budget:
            return user_text
        head = chars_budget // 3
        tail = chars_budget - head - 80
        return (
            user_text[:head]
            + "\n\n...[history truncated to fit token budget]...\n\n"
            + user_text[-tail:]
        )


def _summarize_iteration(record: IterationRecord) -> str:
    verification = record.verification
    execution = verification.execution
    if execution and execution.timed_out:
        kind = "timeout"
    elif not verification.success:
        kind = "failure"
    else:
        kind = "ok"
    summary = verification.summary.replace("\n", " ").strip()
    if len(summary) > 160:
        summary = summary[:157] + "..."
    return f"- iter {record.iteration}: {kind} — {summary}"
