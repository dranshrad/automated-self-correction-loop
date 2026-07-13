# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Isolated subprocess execution with timeouts and output caps."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ascl.models import ExecutionResult

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_OUTPUT_BYTES = 256 * 1024


class RunnerError(RuntimeError):
    """Raised for runner configuration failures."""


def run_python_script(
    code: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    cwd: Path | None = None,
    filename: str = "script.py",
    extra_env: dict[str, str] | None = None,
) -> ExecutionResult:
    """
    Write ``code`` to a temp file (or ``cwd``) and execute it under a hard timeout.

    Uses a new process session so the entire process group can be killed on timeout.
    """
    if timeout_seconds <= 0:
        raise RunnerError("timeout_seconds must be positive")
    if max_output_bytes <= 0:
        raise RunnerError("max_output_bytes must be positive")

    workdir: Path
    cleanup: tempfile.TemporaryDirectory[str] | None = None
    if cwd is None:
        cleanup = tempfile.TemporaryDirectory(prefix="ascl-run-")
        workdir = Path(cleanup.name)
    else:
        workdir = cwd
        workdir.mkdir(parents=True, exist_ok=True)

    script_path = workdir / filename
    try:
        script_path.write_text(code, encoding="utf-8")
        return _execute(
            [sys.executable, str(script_path)],
            cwd=workdir,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            extra_env=extra_env,
        )
    finally:
        if cleanup is not None:
            cleanup.cleanup()


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    extra_env: dict[str, str] | None = None,
) -> ExecutionResult:
    """Run an arbitrary command in ``cwd`` with the same isolation guarantees."""
    if not command:
        raise RunnerError("command must be non-empty")
    cwd.mkdir(parents=True, exist_ok=True)
    return _execute(
        command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
        extra_env=extra_env,
    )


def _execute(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    extra_env: dict[str, str] | None,
) -> ExecutionResult:
    env = os.environ.copy()
    # Keep generated code from inheriting secrets by default; callers can opt in.
    for key in list(env):
        if key.endswith("_API_KEY") or key in {"ANTHROPIC_API_KEY", "OPENAI_API_KEY"}:
            env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    started = time.perf_counter()
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    timed_out = False
    truncated = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_group(proc)
        stdout_b, stderr_b = proc.communicate(timeout=2)
        stdout = stdout_b or ""
        stderr = stderr_b or ""
        if not stderr:
            stderr = f"Process timed out after {timeout_seconds:.1f}s and was killed."

    duration_ms = (time.perf_counter() - started) * 1000.0
    stdout, trunc_out = _cap_output(stdout or "", max_output_bytes)
    stderr, trunc_err = _cap_output(stderr or "", max_output_bytes)
    truncated = trunc_out or trunc_err

    exit_code = proc.returncode if proc.returncode is not None else -1
    if timed_out and exit_code == 0:
        exit_code = -9

    return ExecutionResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=duration_ms,
        truncated=truncated,
    )


def _kill_process_group(proc: subprocess.Popen[str]) -> None:
    if proc.pid is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        with contextlib.suppress(ProcessLookupError):
            proc.kill()


def _cap_output(text: str, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    clipped = encoded[:max_bytes].decode("utf-8", errors="replace")
    notice = f"\n...[truncated: output exceeded {max_bytes} bytes]..."
    return clipped + notice, True
