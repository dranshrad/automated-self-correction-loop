# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Success-gate verifiers for run and heal modes."""

from __future__ import annotations

import shutil
import sys
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from ascl.models import ExecutionResult, VerificationResult
from ascl.prompts import format_failure_directive
from ascl.runner import DEFAULT_MAX_OUTPUT_BYTES, run_command, run_python_script


class Verifier(ABC):
    """Pluggable observer that decides whether an iteration succeeded."""

    @abstractmethod
    def verify(self, code: str) -> VerificationResult:
        """Evaluate generated ``code`` and return a structured result."""


class ExitCodeVerifier(Verifier):
    """``ascl run`` gate: success iff exit code 0 and no timeout."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    def verify(self, code: str) -> VerificationResult:
        execution = run_python_script(
            code,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
        )
        return _from_execution(execution, success_predicate=_exit_ok)


class PytestVerifier(Verifier):
    """``ascl heal`` gate: success iff pytest exits 0 under the same isolation."""

    def __init__(
        self,
        *,
        tests_path: Path,
        timeout_seconds: float,
        module_name: str = "solution.py",
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        work_root: Path | None = None,
    ) -> None:
        self._tests_path = tests_path.resolve()
        self._timeout_seconds = timeout_seconds
        self._module_name = module_name
        self._max_output_bytes = max_output_bytes
        self._work_root = work_root

    def verify(self, code: str) -> VerificationResult:
        if not self._tests_path.exists():
            return VerificationResult(
                success=False,
                summary=f"Tests path not found: {self._tests_path}",
                details="",
            )

        if self._work_root is not None:
            workdir = self._work_root
            workdir.mkdir(parents=True, exist_ok=True)
            return _pytest_result(self._run_in(workdir, code))

        with tempfile.TemporaryDirectory(prefix="ascl-heal-") as tmp:
            return _pytest_result(self._run_in(Path(tmp), code))

    def _run_in(self, workdir: Path, code: str) -> ExecutionResult:
        workdir = workdir.resolve()
        (workdir / self._module_name).write_text(code, encoding="utf-8")
        dest_tests = workdir / "tests"
        if self._tests_path.is_file():
            dest_tests.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self._tests_path, dest_tests / self._tests_path.name)
            # Target must be relative to cwd=workdir (or absolute). A repo-relative
            # path would be resolved incorrectly from inside the workspace.
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
        )


def _exit_ok(execution: ExecutionResult) -> bool:
    return execution.exit_code == 0 and not execution.timed_out


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
