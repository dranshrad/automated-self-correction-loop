# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

from ascl.agent import MockAgent
from ascl.loop import CorrectionLoop, LoopConfig
from ascl.models import ExitReason, Mode, ProviderName


def test_oscillation_injects_circuit_breaker(tmp_path: Path) -> None:
    failing = "```python\nraise SystemExit(1)\n```"
    agent = MockAgent(responses=[failing, failing, failing])
    config = LoopConfig(
        prompt="Always fail",
        mode=Mode.RUN,
        provider=ProviderName.MOCK,
        max_iterations=3,
        enable_lint=False,
        artifact_dir=tmp_path / "osc",
        oscillation_window=3,
    )
    report = CorrectionLoop(config, agent=agent).run()
    assert any(item.oscillation_detected for item in report.iterations)
    # Final exit may be oscillation or max_iterations depending on last-iter flag.
    assert report.exit_reason in {ExitReason.OSCILLATION, ExitReason.MAX_ITERATIONS}
    # Messages path exercised: at least one iteration after the repeat.
    assert len(report.iterations) == 3
