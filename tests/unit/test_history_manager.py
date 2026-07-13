# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from ascl.history_manager import HistoryManager, estimate_tokens
from ascl.models import IterationRecord, VerificationResult


def test_estimate_tokens() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_preserves_system_and_task() -> None:
    hist = HistoryManager(
        system_prompt="SYS_RULES",
        user_prompt="Build a fibonacci function",
        max_context_tokens=8000,
    )
    messages = hist.build_messages(iteration=1, previous_code=None, latest_failure=None)
    assert messages[0].content == "SYS_RULES"
    assert "Build a fibonacci function" in messages[1].content
    assert "## Iteration\n1" in messages[1].content


def test_compresses_older_failures() -> None:
    hist = HistoryManager(
        system_prompt="SYS",
        user_prompt="task",
        max_context_tokens=8000,
    )
    for i in range(1, 5):
        hist.ingest_failure(
            IterationRecord(
                iteration=i,
                code="x=1",
                verification=VerificationResult(
                    success=False,
                    summary=f"boom {i}",
                    details=f"long traceback {i} " * 20,
                ),
            )
        )
    messages = hist.build_messages(
        iteration=5,
        previous_code="x=2",
        latest_failure="FULL LATEST FAILURE LOG",
    )
    body = messages[1].content
    assert "Earlier failures (compressed)" in body
    assert "iter 1" in body
    assert "FULL LATEST FAILURE LOG" in body
    assert "long traceback 1" not in body


def test_token_budget_truncates() -> None:
    hist = HistoryManager(
        system_prompt="SYS",
        user_prompt="task",
        max_context_tokens=200,
    )
    huge = "ERR " * 5000
    messages = hist.build_messages(
        iteration=4,
        previous_code="print(1)\n" * 200,
        latest_failure=huge,
    )
    assert hist.estimate_prompt_tokens(messages) <= 250
    assert "history truncated" in messages[1].content or "Latest failure" in messages[1].content


def test_structural_diff_preferred_over_full_dump() -> None:
    hist = HistoryManager(system_prompt="SYS", user_prompt="task")
    hist.note_code("def add(a, b):\n    return a - b\n", iteration=1)
    hist.ingest_failure(
        IterationRecord(
            iteration=1,
            code="def add(a, b):\n    return a - b\n",
            verification=VerificationResult(success=False, summary="fail", details="boom"),
        )
    )
    hist.note_code("def add(a, b):\n    return a + b\n", iteration=2)
    messages = hist.build_messages(
        iteration=3,
        previous_code="def add(a, b):\n    return a + b\n",
        latest_failure="assertion failed",
    )
    body = messages[1].content
    assert "Structural changes" in body
    assert "modified: add" in body
    assert "Previous code reference" in body
    assert "## Previous code\n```python" not in body
    assert "return a + b" not in body  # full dump omitted
