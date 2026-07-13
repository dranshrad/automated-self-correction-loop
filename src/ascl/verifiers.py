# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Multi-stage success-gate verifiers for run and heal modes."""

from __future__ import annotations

import ast
import shutil
import sys
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from ascl.models import ExecutionResult, VerificationResult
from ascl.prompts import format_failure_directive
from ascl.runner import (
    DEFAULT_MAX_OUTPUT_BYTES,
    ResourceLimits,
    run_command,
    run_python_script,
)


class VerificationStage(StrEnum):
    SYNTAX = "syntax"
    LINT = "lint"
    BEHAVIORAL = "behavioral"


class Verifier(ABC):
    """Pluggable observer that decides whether an iteration succeeded."""

    @abstractmethod
    def verify(self, code: str) -> VerificationResult:
        """Evaluate generated ``code`` and return a structured result."""


class ExitCodeVerifier(Verifier):
    """``ascl run`` gate: static pipeline then exit code 0 / no timeout."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        enable_lint: bool = True,
        resource_limits: ResourceLimits | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._enable_lint = enable_lint
        self._resource_limits = resource_limits or ResourceLimits()

    def verify(self, code: str) -> VerificationResult:
        static = run_static_pipeline(code, enable_lint=self._enable_lint)
        if static is not None:
            return static
        execution = run_python_script(
            code,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
            resource_limits=self._resource_limits,
        )
        result = _from_execution(execution, success_predicate=_exit_ok)
        return _with_stage(result, VerificationStage.BEHAVIORAL)


class PytestVerifier(Verifier):
    """``ascl heal`` gate: static pipeline then frozen pytest under isolation."""

    def __init__(
        self,
        *,
        tests_path: Path,
        timeout_seconds: float,
        module_name: str = "solution.py",
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        work_root: Path | None = None,
        enable_lint: bool = True,
        resource_limits: ResourceLimits | None = None,
    ) -> None:
        self._tests_path = tests_path.resolve()
        self._timeout_seconds = timeout_seconds
        self._module_name = module_name
        self._max_output_bytes = max_output_bytes
        self._work_root = work_root
        self._enable_lint = enable_lint
        self._resource_limits = resource_limits or ResourceLimits()

    def verify(self, code: str) -> VerificationResult:
        if not self._tests_path.exists():
            return VerificationResult(
                success=False,
                summary=f"Tests path not found: {self._tests_path}",
                details="",
                stage=VerificationStage.BEHAVIORAL.value,
            )

        static = run_static_pipeline(code, enable_lint=self._enable_lint)
        if static is not None:
            return static

        if self._work_root is not None:
            workdir = self._work_root
            workdir.mkdir(parents=True, exist_ok=True)
            result = _pytest_result(self._run_in(workdir, code))
            return _with_stage(result, VerificationStage.BEHAVIORAL)

        with tempfile.TemporaryDirectory(prefix="ascl-heal-") as tmp:
            result = _pytest_result(self._run_in(Path(tmp), code))
            return _with_stage(result, VerificationStage.BEHAVIORAL)

    def _run_in(self, workdir: Path, code: str) -> ExecutionResult:
        workdir = workdir.resolve()
        (workdir / self._module_name).write_text(code, encoding="utf-8")
        dest_tests = workdir / "tests"
        if self._tests_path.is_file():
            dest_tests.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self._tests_path, dest_tests / self._tests_path.name)
            pytest_target = f"tests/{self._tests_path.name}"
        else:
            if dest_tests.exists():
                shutil.rmtree(dest_tests)
            shutil.copytree(self._tests_path, dest_tests)
            pytest_target = "tests"

        return run_command(
            [sys.executable, "-m", "pytest", "-q", "--tb=short", pytest_target],
            cwd=workdir,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
            resource_limits=self._resource_limits,
        )


def run_static_pipeline(code: str, *, enable_lint: bool = True) -> VerificationResult | None:
    """
    Run syntax (+ optional lint) before spending a behavioral subprocess.

    Returns a failure ``VerificationResult`` or ``None`` when static checks pass.
    """
    syntax = check_syntax(code)
    if syntax is not None:
        return syntax
    if enable_lint:
        lint = check_lint(code)
        if lint is not None:
            return lint
    return None


def check_syntax(code: str) -> VerificationResult | None:
    """Return a failure result if ``ast.parse`` rejects the source."""
    try:
        ast.parse(code)
    except SyntaxError as exc:
        detail = f"{exc.msg} (line {exc.lineno}, offset {exc.offset})"
        directive = format_failure_directive(
            summary="SyntaxError — static stage failed",
            details=detail,
            timed_out=False,
        )
        return VerificationResult(
            success=False,
            summary="SyntaxError — static stage failed",
            details=directive,
            stage=VerificationStage.SYNTAX.value,
        )
    return None


def check_lint(code: str) -> VerificationResult | None:
    """
    Optional ruff check. Skips cleanly when ruff is not installed.

    Only treats hard errors (E/F) as pipeline failures so stylistic noise does not
    trap the correction loop.
    """
    ruff_bin = shutil.which("ruff")
    with tempfile.TemporaryDirectory(prefix="ascl-lint-") as tmp:
        workdir = Path(tmp)
        path = workdir / "candidate.py"
        path.write_text(code, encoding="utf-8")
        if ruff_bin is not None:
            command = [ruff_bin, "check", "--select", "E,F", path.name]
        else:
            try:
                import importlib.util

                if importlib.util.find_spec("ruff") is None:
                    return None
            except (ImportError, ValueError):
                return None
            command = [sys.executable, "-m", "ruff", "check", "--select", "E,F", path.name]

        execution = run_command(
            command,
            cwd=workdir,
            timeout_seconds=10.0,
            max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
            resource_limits=ResourceLimits(enabled=False),
            extra_env={"RUFF_NO_CACHE": "1"},
        )

    if execution.timed_out:
        directive = format_failure_directive(
            summary="Lint stage timed out",
            details=_combine_streams(execution),
            timed_out=True,
        )
        return VerificationResult(
            success=False,
            summary="Lint stage timed out",
            details=directive,
            execution=execution,
            stage=VerificationStage.LINT.value,
        )

    # ruff exits 0 on clean, 1 on diagnostics found; other codes → skip stage.
    if execution.exit_code == 0:
        return None
    if execution.exit_code != 1:
        return None

    directive = format_failure_directive(
        summary="Lint stage failed (ruff E/F)",
        details=_combine_streams(execution),
        timed_out=False,
    )
    return VerificationResult(
        success=False,
        summary="Lint stage failed (ruff E/F)",
        details=directive,
        execution=execution,
        stage=VerificationStage.LINT.value,
    )


def _exit_ok(execution: ExecutionResult) -> bool:
    return execution.exit_code == 0 and not execution.timed_out


def _with_stage(result: VerificationResult, stage: VerificationStage) -> VerificationResult:
    if result.stage:
        return result
    return VerificationResult(
        success=result.success,
        summary=result.summary,
        details=result.details,
        execution=result.execution,
        stage=stage.value,
    )


def _from_execution(
    execution: ExecutionResult,
    *,
    success_predicate: Callable[[ExecutionResult], bool],
) -> VerificationResult:
    success = success_predicate(execution)
    details = _combine_streams(execution)
    if success:
        return VerificationResult(
            success=True,
            summary="Process exited 0",
            details=details,
            execution=execution,
            stage=VerificationStage.BEHAVIORAL.value,
        )
    if execution.timed_out:
        summary = f"Timed out after {execution.duration_ms:.0f}ms"
    else:
        summary = f"Process exited {execution.exit_code}"
    directive = format_failure_directive(
        summary=summary,
        details=details,
        timed_out=execution.timed_out,
    )
    return VerificationResult(
        success=False,
        summary=summary,
        details=directive,
        execution=execution,
        stage=VerificationStage.BEHAVIORAL.value,
    )


def _pytest_result(execution: ExecutionResult) -> VerificationResult:
    success = _exit_ok(execution)
    combined = _combine_streams(execution)
    if success:
        return VerificationResult(
            success=True,
            summary="pytest passed",
            details=combined,
            execution=execution,
            stage=VerificationStage.BEHAVIORAL.value,
        )
    if execution.timed_out:
        summary = "pytest timed out"
    else:
        summary = f"pytest failed (exit {execution.exit_code})"
    directive = format_failure_directive(
        summary=summary,
        details=combined,
        timed_out=execution.timed_out,
    )
    return VerificationResult(
        success=False,
        summary=summary,
        details=directive,
        execution=execution,
        stage=VerificationStage.BEHAVIORAL.value,
    )


def _combine_streams(execution: ExecutionResult) -> str:
    parts: list[str] = []
    if execution.stdout.strip():
        parts.append("stdout:\n" + execution.stdout.strip())
    if execution.stderr.strip():
        parts.append("stderr:\n" + execution.stderr.strip())
    if not parts:
        return "(no stdout/stderr)"
    return "\n\n".join(parts)
