# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deterministic failure taxonomy for diagnosis-driven repair."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ascl.models import VerificationResult


class FailureClass(StrEnum):
    SYNTAX = "syntax"
    LINT = "lint"
    TIMEOUT = "timeout"
    MEMORY = "memory"
    IMPORT = "import"
    DEPENDENCY = "dependency"
    ASSERTION = "assertion"
    LOGIC = "logic"
    ENVIRONMENT = "environment"
    OSCILLATION = "oscillation"
    FLAKY = "flaky"
    NONDETERMINISM = "nondeterminism"
    UNKNOWN = "unknown"


_REPAIR_HINTS: dict[FailureClass, str] = {
    FailureClass.SYNTAX: (
        "Repair strategy: fix parse/syntax errors only. Do not redesign algorithms."
    ),
    FailureClass.LINT: (
        "Repair strategy: resolve the reported ruff E/F diagnostics with minimal edits."
    ),
    FailureClass.TIMEOUT: (
        "Repair strategy: eliminate unbounded loops/recursion; ensure the program terminates "
        "within the execution timeout."
    ),
    FailureClass.MEMORY: (
        "Repair strategy: reduce memory use — avoid huge allocations, unbounded lists, "
        "or recursive structures that grow without bound."
    ),
    FailureClass.IMPORT: (
        "Repair strategy: remove or replace missing imports; prefer the Python standard library "
        "or define missing helpers locally."
    ),
    FailureClass.DEPENDENCY: (
        "Repair strategy: avoid third-party packages that are not available in the sandbox; "
        "rewrite using stdlib."
    ),
    FailureClass.ASSERTION: (
        "Repair strategy: satisfy the failing assertion/test expectation; keep the public "
        "API unchanged and prefer a correct algorithm over cosmetic patches."
    ),
    FailureClass.LOGIC: (
        "Repair strategy: correct the behavioral logic that causes nonzero exit / wrong output. "
        "Re-check edge cases and return values."
    ),
    FailureClass.ENVIRONMENT: (
        "Repair strategy: this failure is environmental/config-related. Ensure the solution "
        "module is self-contained and does not rely on missing paths or host state."
    ),
    FailureClass.OSCILLATION: (
        "Repair strategy: you are repeating a failing implementation. Change the architectural "
        "approach rather than oscillating between prior patches."
    ),
    FailureClass.FLAKY: ("Repair strategy: remove timing/randomness; make behavior deterministic."),
    FailureClass.NONDETERMINISM: (
        "Repair strategy: remove sources of nondeterminism (random, clock, unordered sets)."
    ),
    FailureClass.UNKNOWN: (
        "Repair strategy: inspect the failure details carefully and return a "
        "complete corrected script."
    ),
}


@dataclass(frozen=True)
class FailureClassification:
    failure_class: FailureClass
    confidence: float
    evidence: str
    repair_hint: str
    hypothesis: str

    def to_dict(self) -> dict[str, object]:
        return {
            "failure_class": self.failure_class.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "repair_hint": self.repair_hint,
            "hypothesis": self.hypothesis,
        }


def classify_failure(
    verification: VerificationResult,
    *,
    oscillated: bool = False,
) -> FailureClassification:
    """
    Classify a failed verification using stage, exit signals, and stderr heuristics.

    When ``oscillated`` is True, overlay OSCILLATION as the primary class so the
    repair directive prioritizes architectural change.
    """
    if verification.success:
        return FailureClassification(
            failure_class=FailureClass.UNKNOWN,
            confidence=1.0,
            evidence="verification succeeded",
            repair_hint="",
            hypothesis="No failure to classify.",
        )

    if oscillated:
        return _make(
            FailureClass.OSCILLATION,
            confidence=0.95,
            evidence="repeated code digest in oscillation window",
            hypothesis="Agent is thrashing between previously seen failing states.",
        )

    stage = (verification.stage or "").lower()
    blob = _blob(verification)

    if stage == "syntax" or "syntaxerror" in blob.lower():
        return _make(
            FailureClass.SYNTAX,
            confidence=0.99,
            evidence=verification.summary or "syntax stage failed",
            hypothesis="Source failed static parse before execution.",
        )

    if stage == "lint" or "lint stage" in blob.lower():
        return _make(
            FailureClass.LINT,
            confidence=0.9,
            evidence=verification.summary or "lint stage failed",
            hypothesis="Static lint diagnostics blocked behavioral execution.",
        )

    if "tests path not found" in blob.lower() or "configuration" in blob.lower():
        return _make(
            FailureClass.ENVIRONMENT,
            confidence=0.85,
            evidence=verification.summary or "environment/config failure",
            hypothesis="Harness or workspace configuration is incorrect.",
        )

    execution = verification.execution
    if execution is not None and execution.timed_out:
        return _make(
            FailureClass.TIMEOUT,
            confidence=0.98,
            evidence=f"timed_out after {execution.duration_ms:.0f}ms",
            hypothesis="Candidate likely contains an infinite loop or unbounded work.",
        )

    if _matches(blob, r"MemoryError|Cannot allocate memory|RLIMIT_AS"):
        return _make(
            FailureClass.MEMORY,
            confidence=0.9,
            evidence="memory-related signal in output",
            hypothesis="Process exceeded memory limits or raised MemoryError.",
        )

    if _matches(blob, r"ModuleNotFoundError"):
        return _make(
            FailureClass.IMPORT,
            confidence=0.95,
            evidence="ModuleNotFoundError",
            hypothesis="Missing module import in the candidate or test environment.",
        )

    if _matches(blob, r"ImportError"):
        return _make(
            FailureClass.DEPENDENCY,
            confidence=0.85,
            evidence="ImportError",
            hypothesis="Import failed — possibly a missing dependency or bad relative import.",
        )

    if _matches(blob, r"AssertionError|assert |FAILED"):
        return _make(
            FailureClass.ASSERTION,
            confidence=0.9,
            evidence="assertion/pytest failure signal",
            hypothesis="Behavioral tests rejected the candidate output/state.",
        )

    if _matches(blob, r"random\.|time\.sleep|uuid4|nondetermin"):
        return _make(
            FailureClass.NONDETERMINISM,
            confidence=0.55,
            evidence="possible nondeterminism markers",
            hypothesis="Failure may stem from nondeterministic behavior.",
        )

    if execution is not None and execution.exit_code != 0:
        return _make(
            FailureClass.LOGIC,
            confidence=0.7,
            evidence=f"exit_code={execution.exit_code}",
            hypothesis="Process failed without a more specific taxonomy match.",
        )

    return _make(
        FailureClass.UNKNOWN,
        confidence=0.4,
        evidence=verification.summary or "unclassified failure",
        hypothesis="Insufficient signal to classify precisely.",
    )


def format_classification_block(classification: FailureClassification) -> str:
    """Render a dense diagnosis block for the next LLM turn."""
    if not classification.repair_hint:
        return ""
    return (
        f"## Diagnosis\n"
        f"- class: {classification.failure_class.value}\n"
        f"- confidence: {classification.confidence:.2f}\n"
        f"- hypothesis: {classification.hypothesis}\n"
        f"- evidence: {classification.evidence}\n\n"
        f"## Repair directive\n{classification.repair_hint}"
    )


def _make(
    failure_class: FailureClass,
    *,
    confidence: float,
    evidence: str,
    hypothesis: str,
) -> FailureClassification:
    return FailureClassification(
        failure_class=failure_class,
        confidence=confidence,
        evidence=evidence,
        repair_hint=_REPAIR_HINTS[failure_class],
        hypothesis=hypothesis,
    )


def _blob(verification: VerificationResult) -> str:
    parts = [verification.summary, verification.details]
    if verification.execution is not None:
        parts.append(verification.execution.stdout)
        parts.append(verification.execution.stderr)
    return "\n".join(part for part in parts if part)


def _matches(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None
