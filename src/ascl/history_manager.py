# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Token-aware rolling window with AST structural diff injection."""

from __future__ import annotations

from dataclasses import dataclass, field

from ascl.ast_diff import StructuralDiff, compute_structural_diff
from ascl.models import ChatMessage, IterationRecord

DEFAULT_MAX_CONTEXT_TOKENS = 8000

OSCILLATION_CIRCUIT_BREAKER = (
    "System Warning: You are oscillating between identical failing states. "
    "Change your architectural approach rather than patching this function line-by-line. "
    "Propose a materially different implementation."
)


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
    - latest crash/pytest log
    - structural AST diff vs prior iteration (instead of full monolith when possible)

    After iteration > 3, older failures collapse to one-line summaries.
    """

    system_prompt: str
    user_prompt: str
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    _summaries: list[str] = field(default_factory=list)
    _last_code: str | None = None
    _last_diff: StructuralDiff | None = None
    _last_diff_iteration: int | None = None

    def ingest_failure(self, record: IterationRecord) -> None:
        """Record a failed iteration summary (structural delta already via note_code)."""
        self._summaries.append(_summarize_iteration(record))

    def note_code(self, code: str, iteration: int) -> StructuralDiff | None:
        """Track code and return the structural diff vs the previous iteration."""
        diff: StructuralDiff | None = None
        if self._last_code is not None:
            diff = compute_structural_diff(self._last_code, code)
            self._last_diff = diff
            self._last_diff_iteration = iteration
        self._last_code = code
        return diff

    def build_messages(
        self,
        *,
        iteration: int,
        previous_code: str | None,
        latest_failure: str | None,
        oscillation_warning: bool = False,
        include_full_previous: bool = False,
        diagnosis_block: str | None = None,
    ) -> list[ChatMessage]:
        """Assemble system + user(+correction) messages within budget."""
        system = ChatMessage(role="system", content=self.system_prompt)

        parts: list[str] = [
            f"## Original task\n{self.user_prompt}",
            f"## Iteration\n{iteration}",
        ]

        if oscillation_warning:
            parts.append(f"## Circuit breaker\n{OSCILLATION_CIRCUIT_BREAKER}")

        if diagnosis_block:
            parts.append(diagnosis_block)

        if self._last_diff is not None:
            parts.append(
                "## Structural changes\n"
                + self._last_diff.format_block(iteration=self._last_diff_iteration)
            )
            if self._last_diff.modified:
                anchors = ", ".join(self._last_diff.modified)
                parts.append(
                    f"## Attention anchor\nFocus corrections on: {anchors}. "
                    "Avoid unrelated rewrites."
                )

        # Prefer structural diffs; only dump full prior source when requested or
        # when we have no diff yet (first correction).
        if previous_code and (include_full_previous or self._last_diff is None):
            parts.append(f"## Previous code\n```python\n{previous_code}\n```")
        elif previous_code and self._last_diff is not None:
            # Compact footprint: keep a short hash pointer, not the monolith.
            from ascl.ast_diff import code_hash

            parts.append(
                "## Previous code reference\n"
                f"sha256={code_hash(previous_code)[:16]}… "
                f"({len(previous_code.splitlines())} lines; "
                "full dump omitted — see structural diff)"
            )

        older = self._older_summaries(iteration)
        if older:
            parts.append("## Earlier failures (compressed)\n" + "\n".join(older))

        if latest_failure:
            failure_header = "## Latest failure (full)\n"
            if self._last_diff is not None and self._last_diff.modified:
                changed = ", ".join(self._last_diff.modified)
                failure_header = (
                    f"## Latest failure (full)\n"
                    f"In iteration {self._last_diff_iteration}, you changed "
                    f"{changed}. This modification produced the following exception/"
                    f"verification failure:\n\n"
                )
            parts.append(
                failure_header
                + "Treat this as a systemic correction directive and return a complete "
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
        if not self._summaries:
            return []
        if len(self._summaries) <= 1:
            return []
        return self._summaries[:-1]

    def _fit_to_budget(self, system_text: str, user_text: str) -> str:
        budget = self.max_context_tokens - estimate_tokens(system_text)
        if budget < 256:
            budget = 256
        if estimate_tokens(user_text) <= budget:
            return user_text

        lines = user_text.splitlines()
        compressed_idx = next(
            (i for i, line in enumerate(lines) if line.startswith("## Earlier failures")),
            None,
        )
        if compressed_idx is not None:
            end = compressed_idx + 1
            while end < len(lines) and not lines[end].startswith("## "):
                end += 1
            trimmed = lines[:compressed_idx] + lines[end:]
            user_text = "\n".join(trimmed)
            if estimate_tokens(user_text) <= budget:
                return user_text

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
    stage = f"[{verification.stage}] " if verification.stage else ""
    klass = f"{{{record.failure_class}}} " if record.failure_class else ""
    summary = verification.summary.replace("\n", " ").strip()
    if len(summary) > 160:
        summary = summary[:157] + "..."
    diff_note = ""
    if record.structural_diff:
        diff_note = f" | {record.structural_diff.splitlines()[0]}"
    return f"- iter {record.iteration}: {stage}{klass}{kind} — {summary}{diff_note}"
