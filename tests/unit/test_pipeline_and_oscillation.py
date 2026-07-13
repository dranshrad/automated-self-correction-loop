# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from ascl.loop import OscillationDetector
from ascl.verifiers import ExitCodeVerifier, check_syntax


def test_syntax_stage_rejects_invalid_code() -> None:
    result = check_syntax("def broken(\n")
    assert result is not None
    assert result.success is False
    assert result.stage == "syntax"


def test_exit_code_verifier_stops_at_syntax() -> None:
    verifier = ExitCodeVerifier(timeout_seconds=5, enable_lint=False)
    result = verifier.verify("def broken(\n")
    assert result.success is False
    assert result.stage == "syntax"
    assert result.execution is None


def test_oscillation_detector_flags_repeats() -> None:
    detector = OscillationDetector(window=3)
    assert detector.observe("aaa") is False
    assert detector.observe("bbb") is False
    assert detector.observe("aaa") is True
