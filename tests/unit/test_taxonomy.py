# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from ascl.models import ExecutionResult, VerificationResult
from ascl.taxonomy import FailureClass, classify_failure


def _exec(
    *,
    exit_code: int = 1,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
) -> ExecutionResult:
    return ExecutionResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=12.0,
    )


def test_classify_syntax() -> None:
    result = VerificationResult(
        success=False,
        summary="SyntaxError — static stage failed",
        details="unexpected EOF",
        stage="syntax",
    )
    classification = classify_failure(result)
    assert classification.failure_class is FailureClass.SYNTAX
    assert "parse" in classification.repair_hint.lower()


def test_classify_timeout() -> None:
    result = VerificationResult(
        success=False,
        summary="Timed out",
        details="",
        execution=_exec(timed_out=True, exit_code=-9),
        stage="behavioral",
    )
    classification = classify_failure(result)
    assert classification.failure_class is FailureClass.TIMEOUT


def test_classify_import() -> None:
    result = VerificationResult(
        success=False,
        summary="pytest failed",
        details="ModuleNotFoundError: No module named 'foo'",
        execution=_exec(stderr="ModuleNotFoundError: No module named 'foo'"),
        stage="behavioral",
    )
    classification = classify_failure(result)
    assert classification.failure_class is FailureClass.IMPORT


def test_classify_assertion() -> None:
    result = VerificationResult(
        success=False,
        summary="pytest failed",
        details="AssertionError: assert 2 == 3\nFAILED",
        execution=_exec(stdout="FAILED tests/test_x.py::test_add - AssertionError"),
        stage="behavioral",
    )
    classification = classify_failure(result)
    assert classification.failure_class is FailureClass.ASSERTION


def test_classify_oscillation_overlay() -> None:
    result = VerificationResult(
        success=False,
        summary="pytest failed",
        details="AssertionError",
        execution=_exec(stdout="AssertionError"),
        stage="behavioral",
    )
    classification = classify_failure(result, oscillated=True)
    assert classification.failure_class is FailureClass.OSCILLATION
