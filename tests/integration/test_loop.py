# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

from ascl.agent import MockAgent
from ascl.loop import CorrectionLoop, LoopConfig
from ascl.models import ExitReason, Mode, ProviderName


def test_run_mode_succeeds_with_mock(tmp_path: Path) -> None:
    agent = MockAgent(
        responses=[
            "```python\nprint('hello from ascl mock')\n```",
        ]
    )
    config = LoopConfig(
        prompt="Print a greeting",
        mode=Mode.RUN,
        provider=ProviderName.MOCK,
        max_iterations=3,
        artifact_dir=tmp_path / "artifacts",
    )
    report = CorrectionLoop(config, agent=agent).run()
    assert report.exit_reason is ExitReason.SUCCESS
    assert (tmp_path / "artifacts" / "report.json").exists()


def test_run_mode_self_heals_after_failure(tmp_path: Path) -> None:
    agent = MockAgent(
        responses=[
            "```python\nraise SystemExit(1)\n```",
            "```python\nprint('recovered')\n```",
        ]
    )
    config = LoopConfig(
        prompt="Print recovered",
        mode=Mode.RUN,
        provider=ProviderName.MOCK,
        max_iterations=3,
        artifact_dir=tmp_path / "run-heal",
    )
    report = CorrectionLoop(config, agent=agent).run()
    assert report.exit_reason is ExitReason.SUCCESS
    assert len(report.iterations) == 2


def test_heal_mode_with_frozen_tests(tmp_path: Path) -> None:
    tests = tmp_path / "test_fib.py"
    tests.write_text(
        "from solution import fib\n\n"
        "def test_fib_base():\n"
        "    assert fib(0) == 0\n"
        "    assert fib(1) == 1\n\n"
        "def test_fib_10():\n"
        "    assert fib(10) == 55\n",
        encoding="utf-8",
    )
    broken = (
        "```python\n"
        "def fib(n: int) -> int:\n"
        "    if n < 2:\n"
        "        return n\n"
        "    return fib(n - 1) + fib(n - 2) + 1\n"
        "```"
    )
    fixed = (
        "```python\n"
        "def fib(n: int) -> int:\n"
        "    if n < 2:\n"
        "        return n\n"
        "    a, b = 0, 1\n"
        "    for _ in range(2, n + 1):\n"
        "        a, b = b, a + b\n"
        "    return b\n"
        "```"
    )
    agent = MockAgent(responses=[broken, fixed])
    config = LoopConfig(
        prompt="Implement fib(n)",
        mode=Mode.HEAL,
        provider=ProviderName.MOCK,
        tests_path=tests,
        max_iterations=4,
        timeout_seconds=15,
        artifact_dir=tmp_path / "heal",
    )
    report = CorrectionLoop(config, agent=agent).run()
    assert report.exit_reason is ExitReason.SUCCESS
    assert report.final_code is not None
    assert "a, b = 0, 1" in report.final_code
