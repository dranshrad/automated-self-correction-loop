# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from ascl.metrics import aggregate_metrics
from ascl.models import (
    ExecutionResult,
    ExitReason,
    IterationRecord,
    Mode,
    ProviderName,
    RunReport,
    VerificationResult,
)


def test_aggregate_metrics_histogram_and_first_pass() -> None:
    report = RunReport(
        mode=Mode.RUN,
        prompt="x",
        max_iterations=5,
        timeout_seconds=5.0,
        provider=ProviderName.MOCK,
        model="mock-v1",
        exit_reason=ExitReason.SUCCESS,
        iterations=[
            IterationRecord(
                iteration=1,
                code="raise SystemExit(1)",
                verification=VerificationResult(
                    success=False,
                    summary="exit 1",
                    stage="behavioral",
                    execution=ExecutionResult(
                        exit_code=1,
                        stdout="",
                        stderr="",
                        timed_out=False,
                        duration_ms=10.0,
                    ),
                ),
                prompt_tokens_estimate=100,
                failure_class="logic",
                classification_confidence=0.7,
                oscillation_detected=False,
            ),
            IterationRecord(
                iteration=2,
                code="print('ok')",
                verification=VerificationResult(
                    success=True,
                    summary="ok",
                    stage="behavioral",
                    execution=ExecutionResult(
                        exit_code=0,
                        stdout="ok",
                        stderr="",
                        timed_out=False,
                        duration_ms=5.0,
                    ),
                ),
                prompt_tokens_estimate=120,
                oscillation_detected=True,
            ),
        ],
    )
    metrics = aggregate_metrics(report)
    assert metrics.success is True
    assert metrics.first_pass_success is False
    assert metrics.iterations == 2
    assert metrics.failure_class_histogram == {"logic": 1}
    assert metrics.oscillation_count == 1
    assert metrics.prompt_tokens_estimate_total == 220
    assert metrics.total_execution_ms == 15.0
    assert "logic=1" in metrics.format_summary()
