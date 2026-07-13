# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

from ascl.verifiers import ExitCodeVerifier, PytestVerifier


def test_exit_code_verifier_success() -> None:
    verifier = ExitCodeVerifier(timeout_seconds=5)
    result = verifier.verify("print('hi')")
    assert result.success is True


def test_exit_code_verifier_timeout() -> None:
    verifier = ExitCodeVerifier(timeout_seconds=0.4)
    result = verifier.verify("while True:\n    pass\n")
    assert result.success is False
    assert result.execution is not None
    assert result.execution.timed_out is True


def test_pytest_verifier(tmp_path: Path) -> None:
    tests = tmp_path / "test_add.py"
    tests.write_text(
        "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    verifier = PytestVerifier(tests_path=tests, timeout_seconds=10)
    ok = verifier.verify("def add(a, b):\n    return a + b\n")
    assert ok.success is True
    bad = verifier.verify("def add(a, b):\n    return a - b\n")
    assert bad.success is False
    assert "pytest failed" in bad.summary
