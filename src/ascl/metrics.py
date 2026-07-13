# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Aggregate run metrics for artifact dashboards."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from ascl.models import ExitReason, RunReport


@dataclass(frozen=True)
class RunMetrics:
    """Rich summary derived from a completed ``RunReport``."""

    iterations: int
    max_iterations: int
    success: bool
    first_pass_success: bool
    exit_reason: str
    oscillation_count: int
    oscillation_rate: float
    prompt_tokens_estimate_total: int
    prompt_tokens_estimate_mean: float
    total_execution_ms: float
    stage_failure_counts: dict[str, int]
    failure_class_histogram: dict[str, int]
    mean_classification_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "max_iterations": self.max_iterations,
            "success": self.success,
            "first_pass_success": self.first_pass_success,
            "exit_reason": self.exit_reason,
            "oscillation_count": self.oscillation_count,
            "oscillation_rate": self.oscillation_rate,
            "prompt_tokens_estimate_total": self.prompt_tokens_estimate_total,
            "prompt_tokens_estimate_mean": self.prompt_tokens_estimate_mean,
            "total_execution_ms": self.total_execution_ms,
            "stage_failure_counts": self.stage_failure_counts,
            "failure_class_histogram": self.failure_class_histogram,
            "mean_classification_confidence": self.mean_classification_confidence,
        }

    def format_summary(self) -> str:
        hist = (
            ", ".join(
                f"{name}={count}" for name, count in sorted(self.failure_class_histogram.items())
            )
            or "(none)"
        )
        stages = (
            ", ".join(
                f"{name}={count}" for name, count in sorted(self.stage_failure_counts.items())
            )
            or "(none)"
        )
        return (
            f"success={self.success}  first_pass={self.first_pass_success}\n"
            f"iterations={self.iterations}/{self.max_iterations}  "
            f"exit={self.exit_reason}\n"
            f"oscillations={self.oscillation_count} "
            f"({self.oscillation_rate:.0%})  "
            f"tokens≈{self.prompt_tokens_estimate_total}  "
            f"exec_ms={self.total_execution_ms:.0f}\n"
            f"failure_classes: {hist}\n"
            f"stage_failures: {stages}"
        )


def aggregate_metrics(report: RunReport) -> RunMetrics:
    """Compute dashboard metrics from a finished correction run."""
    iterations = report.iterations
    n = len(iterations)
    success = report.exit_reason is ExitReason.SUCCESS
    first_pass = bool(iterations) and iterations[0].verification.success and success

    oscillation_count = sum(1 for item in iterations if item.oscillation_detected)
    oscillation_rate = (oscillation_count / n) if n else 0.0

    token_total = sum(item.prompt_tokens_estimate for item in iterations)
    token_mean = (token_total / n) if n else 0.0

    total_exec_ms = 0.0
    stage_failures: Counter[str] = Counter()
    class_hist: Counter[str] = Counter()
    confidences: list[float] = []

    for item in iterations:
        verification = item.verification
        if verification.execution is not None:
            total_exec_ms += verification.execution.duration_ms
        if not verification.success:
            stage = verification.stage or "unknown"
            stage_failures[stage] += 1
        if item.failure_class:
            class_hist[item.failure_class] += 1
        if item.classification_confidence is not None:
            confidences.append(item.classification_confidence)

    mean_conf = (sum(confidences) / len(confidences)) if confidences else 0.0

    return RunMetrics(
        iterations=n,
        max_iterations=report.max_iterations,
        success=success,
        first_pass_success=first_pass,
        exit_reason=report.exit_reason.value,
        oscillation_count=oscillation_count,
        oscillation_rate=oscillation_rate,
        prompt_tokens_estimate_total=token_total,
        prompt_tokens_estimate_mean=token_mean,
        total_execution_ms=total_exec_ms,
        stage_failure_counts=dict(stage_failures),
        failure_class_histogram=dict(class_hist),
        mean_classification_confidence=mean_conf,
    )
