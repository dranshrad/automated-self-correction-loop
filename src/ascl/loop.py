# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared generate → verify → correct orchestration loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ascl.agent import Agent, AgentError, create_agent
from ascl.history_manager import DEFAULT_MAX_CONTEXT_TOKENS, HistoryManager
from ascl.models import (
    ChatMessage,
    ExitReason,
    IterationRecord,
    Mode,
    ProviderName,
    RunReport,
    VerificationResult,
)
from ascl.parser import CodeParseError, extract_python_code
from ascl.prompts import SCAFFOLD_TESTS_PROMPT, system_prompt_for
from ascl.verifiers import ExitCodeVerifier, PytestVerifier, Verifier


@dataclass
class LoopConfig:
    prompt: str
    mode: Mode
    max_iterations: int = 5
    timeout_seconds: float = 5.0
    provider: ProviderName = ProviderName.ANTHROPIC
    model: str | None = None
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    artifact_dir: Path | None = None
    tests_path: Path | None = None
    scaffold_tests: bool = False
    mock_responses: list[str] | None = None


class CorrectionLoop:
    """Owns one full self-correction session."""

    def __init__(
        self,
        config: LoopConfig,
        *,
        agent: Agent | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        self.config = config
        self.agent = agent or create_agent(
            config.provider,
            model=config.model,
            mock_responses=config.mock_responses,
        )
        self.verifier = verifier or self._build_verifier()
        self.history = HistoryManager(
            system_prompt=system_prompt_for(config.mode),
            user_prompt=config.prompt,
            max_context_tokens=config.max_context_tokens,
        )

    def run(self) -> RunReport:
        if self.config.mode is Mode.HEAL:
            self._ensure_tests()

        iterations: list[IterationRecord] = []
        previous_code: str | None = None
        latest_failure: str | None = None
        exit_reason = ExitReason.MAX_ITERATIONS
        final_code: str | None = None

        for iteration in range(1, self.config.max_iterations + 1):
            messages = self.history.build_messages(
                iteration=iteration,
                previous_code=previous_code,
                latest_failure=latest_failure,
            )
            token_estimate = self.history.estimate_prompt_tokens(messages)
            raw = ""

            try:
                raw = self.agent.complete(messages)
                code = extract_python_code(raw)
            except (AgentError, CodeParseError) as exc:
                record = IterationRecord(
                    iteration=iteration,
                    code=previous_code or "",
                    verification=VerificationResult(
                        success=False,
                        summary=str(exc),
                        details=str(exc),
                    ),
                    prompt_tokens_estimate=token_estimate,
                    raw_model_response=raw,
                )
                iterations.append(record)
                self.history.ingest_failure(record)
                latest_failure = str(exc)
                if isinstance(exc, AgentError) and previous_code is None:
                    exit_reason = ExitReason.CONFIG_ERROR
                    break
                continue

            verification = self.verifier.verify(code)
            record = IterationRecord(
                iteration=iteration,
                code=code,
                verification=verification,
                prompt_tokens_estimate=token_estimate,
                raw_model_response=raw,
            )
            iterations.append(record)
            previous_code = code
            final_code = code
            self._write_iteration_artifact(record)

            if verification.success:
                exit_reason = ExitReason.SUCCESS
                break

            self.history.ingest_failure(record)
            latest_failure = verification.details or verification.summary

        report = RunReport(
            mode=self.config.mode,
            prompt=self.config.prompt,
            max_iterations=self.config.max_iterations,
            timeout_seconds=self.config.timeout_seconds,
            provider=self.agent.provider,
            model=self.agent.model,
            exit_reason=exit_reason,
            iterations=iterations,
            final_code=final_code,
        )
        self._write_report(report)
        return report

    def _build_verifier(self) -> Verifier:
        if self.config.mode is Mode.RUN:
            return ExitCodeVerifier(timeout_seconds=self.config.timeout_seconds)
        if self.config.tests_path is None and not self.config.scaffold_tests:
            raise AgentError("heal mode requires --tests or --scaffold-tests")
        # tests_path may be filled by scaffolding before verify; temporary placeholder
        # is resolved in _ensure_tests before the loop body runs.
        tests_path = self.config.tests_path or Path(".")
        return PytestVerifier(
            tests_path=tests_path,
            timeout_seconds=self.config.timeout_seconds,
            work_root=(self.config.artifact_dir / "workspace")
            if self.config.artifact_dir
            else None,
        )

    def _ensure_tests(self) -> None:
        if self.config.tests_path is not None and self.config.tests_path.exists():
            # Rebuild verifier with the resolved path.
            self.verifier = PytestVerifier(
                tests_path=self.config.tests_path,
                timeout_seconds=self.config.timeout_seconds,
                work_root=(self.config.artifact_dir / "workspace")
                if self.config.artifact_dir
                else None,
            )
            return
        if not self.config.scaffold_tests:
            raise AgentError("heal mode requires --tests PATH or --scaffold-tests")

        artifact = self.config.artifact_dir or Path(".ascl")
        artifact.mkdir(parents=True, exist_ok=True)
        tests_file = artifact / "scaffolded_tests.py"
        if not tests_file.exists():
            messages = [
                ChatMessage(role="system", content=system_prompt_for(Mode.HEAL)),
                ChatMessage(
                    role="user",
                    content=f"{SCAFFOLD_TESTS_PROMPT}\n\n## Task\n{self.config.prompt}",
                ),
            ]
            raw = self.agent.complete(messages)
            tests_file.write_text(extract_python_code(raw), encoding="utf-8")

        self.config.tests_path = tests_file
        self.verifier = PytestVerifier(
            tests_path=tests_file,
            timeout_seconds=self.config.timeout_seconds,
            work_root=(self.config.artifact_dir / "workspace")
            if self.config.artifact_dir
            else None,
        )

    def _write_report(self, report: RunReport) -> None:
        if self.config.artifact_dir is None:
            return
        self.config.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.artifact_dir / "report.json"
        path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        if report.final_code:
            (self.config.artifact_dir / "final_solution.py").write_text(
                report.final_code,
                encoding="utf-8",
            )

    def _write_iteration_artifact(self, record: IterationRecord) -> None:
        if self.config.artifact_dir is None:
            return
        folder = self.config.artifact_dir / f"iteration_{record.iteration:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "code.py").write_text(record.code, encoding="utf-8")
        (folder / "result.json").write_text(
            json.dumps(record.to_dict(), indent=2),
            encoding="utf-8",
        )
