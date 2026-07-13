# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from ascl.runner import run_python_script


def test_successful_script() -> None:
    result = run_python_script("print('ok')", timeout_seconds=5)
    assert result.exit_code == 0
    assert result.timed_out is False
    assert "ok" in result.stdout


def test_nonzero_exit() -> None:
    result = run_python_script("raise SystemExit(7)", timeout_seconds=5)
    assert result.exit_code == 7
    assert result.timed_out is False


def test_timeout_kills_infinite_loop() -> None:
    result = run_python_script("while True:\n    pass\n", timeout_seconds=0.5)
    assert result.timed_out is True
    assert result.exit_code != 0


def test_output_cap_truncates() -> None:
    code = "print('x' * 10000)"
    result = run_python_script(code, timeout_seconds=5, max_output_bytes=200)
    assert result.truncated is True
    assert "truncated" in result.stdout
