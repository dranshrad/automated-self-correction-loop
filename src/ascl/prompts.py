# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""System and task prompt templates."""

from __future__ import annotations

from ascl.models import Mode

SYSTEM_PROMPT = """\
You are a senior Python engineer inside an automated self-correction loop.
Your job is to emit a complete, runnable Python solution that satisfies the task.

Rules:
1. Respond with exactly one fenced ```python``` code block containing the full script/module.
2. Do not omit code, use placeholders, or ask clarifying questions.
3. Prefer small, correct fixes when previous code and a failure log are provided.
4. Avoid infinite loops; respect that execution is hard-capped by a process timeout.
5. Do not access the network, read secrets from the environment, or write outside
   the working directory.
"""

HEAL_SYSTEM_ADDENDUM = """\
You are healing an implementation so that a frozen pytest suite passes.
Do not modify or regenerate tests unless explicitly asked to scaffold them once.
Only change the implementation module.
"""

SCAFFOLD_TESTS_PROMPT = """\
Given the user task below, emit a complete pytest module in a single ```python``` fence.
The tests must be deterministic, self-contained, and import the implementation from `solution.py`
(e.g. `from solution import ...`). Do not implement the solution itself—only the tests.
"""


def system_prompt_for(mode: Mode) -> str:
    if mode is Mode.HEAL:
        return SYSTEM_PROMPT + "\n" + HEAL_SYSTEM_ADDENDUM
    return SYSTEM_PROMPT


def format_failure_directive(
    *,
    summary: str,
    details: str,
    timed_out: bool,
) -> str:
    timeout_note = (
        "The process was killed due to a timeout (possible infinite loop).\n" if timed_out else ""
    )
    return (
        f"{timeout_note}"
        f"Summary: {summary}\n\n"
        f"Details:\n{details.strip() or '(no additional details)'}\n"
    )
