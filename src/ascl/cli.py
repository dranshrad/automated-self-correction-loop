# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Typer CLI for Automated Self-Correction Loop."""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from ascl import __version__
from ascl.agent import DEFAULT_MODELS, AgentError
from ascl.history_manager import DEFAULT_MAX_CONTEXT_TOKENS
from ascl.loop import CorrectionLoop, LoopConfig
from ascl.metrics import RunMetrics, aggregate_metrics
from ascl.models import ExitReason, Mode, ProviderName
from ascl.runner import DEFAULT_MAX_PROCS, DEFAULT_MEMORY_MB, DEFAULT_TIMEOUT_SECONDS

app = typer.Typer(
    name="ascl",
    help="Automated Self-Correction Loop — process-isolated self-healing Python agent harness.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(stderr=True)


def _default_provider() -> str:
    return os.environ.get("ASCL_PROVIDER", ProviderName.ANTHROPIC.value)


def _resolve_provider(value: str) -> ProviderName:
    try:
        return ProviderName(value.lower())
    except ValueError as exc:
        allowed = ", ".join(p.value for p in ProviderName)
        raise typer.BadParameter(f"Unknown provider '{value}'. Choose from: {allowed}") from exc


def _exit_code_for(reason: ExitReason) -> int:
    if reason is ExitReason.SUCCESS:
        return 0
    if reason is ExitReason.CONFIG_ERROR:
        return 2
    if reason is ExitReason.INTERRUPTED:
        return 130
    return 1


def _shared_options(
    prompt: str,
    max_iterations: int,
    timeout: float,
    provider: str,
    model: str | None,
    max_context_tokens: int,
    artifact_dir: Path | None,
    *,
    enable_lint: bool,
    memory_mb: int,
    max_procs: int,
    resource_limits: bool,
) -> LoopConfig:
    return LoopConfig(
        prompt=prompt,
        mode=Mode.RUN,
        max_iterations=max_iterations,
        timeout_seconds=timeout,
        provider=_resolve_provider(provider),
        model=model,
        max_context_tokens=max_context_tokens,
        artifact_dir=artifact_dir,
        enable_lint=enable_lint,
        memory_mb=memory_mb,
        max_procs=max_procs,
        resource_limits_enabled=resource_limits,
    )


def _print_report_summary(
    mode: Mode,
    reason: ExitReason,
    iterations: int,
    model: str,
    metrics: RunMetrics | None = None,
) -> None:
    style = "green" if reason is ExitReason.SUCCESS else "red"
    body = (
        f"[bold]{mode.value}[/bold] finished: [bold {style}]{reason.value}[/bold {style}]\n"
        f"iterations={iterations}  model={model}"
    )
    if metrics is not None:
        body += "\n\n" + metrics.format_summary()
    console.print(Panel.fit(body, title="ascl"))


@app.callback()
def main() -> None:
    """Automated Self-Correction Loop."""


@app.command("version")
def version_cmd() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command("run")
def run_cmd(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Task description for code generation."),
    max_iterations: int = typer.Option(5, "--max-iterations", "-n", min=1, help="Retry budget."),
    timeout: float = typer.Option(
        DEFAULT_TIMEOUT_SECONDS,
        "--timeout",
        "-t",
        help="Subprocess timeout in seconds.",
    ),
    provider: str = typer.Option(
        _default_provider(),
        "--provider",
        help="LLM provider: anthropic | openai | mock.",
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Override provider model id."),
    max_context_tokens: int = typer.Option(
        DEFAULT_MAX_CONTEXT_TOKENS,
        "--max-context-tokens",
        help="Token budget for compressed error history.",
    ),
    artifact_dir: Path | None = typer.Option(
        None,
        "--artifact-dir",
        help="Directory for report.json and per-iteration artifacts.",
    ),
    lint: bool = typer.Option(
        True,
        "--lint/--no-lint",
        help="Run ruff E/F after syntax checks (skipped if ruff missing).",
    ),
    memory_mb: int = typer.Option(
        DEFAULT_MEMORY_MB,
        "--memory-mb",
        help="RLIMIT_AS soft ceiling for child processes (MiB).",
    ),
    max_procs: int = typer.Option(
        DEFAULT_MAX_PROCS,
        "--max-procs",
        help="RLIMIT_NPROC ceiling to mitigate fork bombs.",
    ),
    resource_limits: bool = typer.Option(
        True,
        "--resource-limits/--no-resource-limits",
        help="Apply Unix resource limits in the child process.",
    ),
) -> None:
    """Generate and execute a script until it exits 0 (or retries are exhausted)."""
    config = _shared_options(
        prompt,
        max_iterations,
        timeout,
        provider,
        model,
        max_context_tokens,
        artifact_dir,
        enable_lint=lint,
        memory_mb=memory_mb,
        max_procs=max_procs,
        resource_limits=resource_limits,
    )
    config.mode = Mode.RUN
    _execute(config)


@app.command("heal")
def heal_cmd(
    prompt: str = typer.Option(
        ...,
        "--prompt",
        "-p",
        help="Task description for the implementation.",
    ),
    tests: Path | None = typer.Option(
        None,
        "--tests",
        help="Path to a pytest file or directory (frozen during healing).",
    ),
    scaffold_tests: bool = typer.Option(
        False,
        "--scaffold-tests",
        help="Ask the LLM once for a pytest suite, then freeze it.",
    ),
    max_iterations: int = typer.Option(5, "--max-iterations", "-n", min=1, help="Retry budget."),
    timeout: float = typer.Option(
        DEFAULT_TIMEOUT_SECONDS,
        "--timeout",
        "-t",
        help="Pytest/subprocess timeout in seconds.",
    ),
    provider: str = typer.Option(
        _default_provider(),
        "--provider",
        help="LLM provider: anthropic | openai | mock.",
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Override provider model id."),
    max_context_tokens: int = typer.Option(
        DEFAULT_MAX_CONTEXT_TOKENS,
        "--max-context-tokens",
        help="Token budget for compressed error history.",
    ),
    artifact_dir: Path | None = typer.Option(
        None,
        "--artifact-dir",
        help="Directory for report.json and per-iteration artifacts.",
    ),
    lint: bool = typer.Option(
        True,
        "--lint/--no-lint",
        help="Run ruff E/F after syntax checks (skipped if ruff missing).",
    ),
    memory_mb: int = typer.Option(
        DEFAULT_MEMORY_MB,
        "--memory-mb",
        help="RLIMIT_AS soft ceiling for child processes (MiB).",
    ),
    max_procs: int = typer.Option(
        DEFAULT_MAX_PROCS,
        "--max-procs",
        help="RLIMIT_NPROC ceiling to mitigate fork bombs.",
    ),
    resource_limits: bool = typer.Option(
        True,
        "--resource-limits/--no-resource-limits",
        help="Apply Unix resource limits in the child process.",
    ),
) -> None:
    """Heal an implementation until a frozen pytest suite passes."""
    if tests is None and not scaffold_tests:
        console.print("[red]heal requires --tests PATH or --scaffold-tests[/red]")
        raise typer.Exit(code=2)

    config = _shared_options(
        prompt,
        max_iterations,
        timeout,
        provider,
        model,
        max_context_tokens,
        artifact_dir,
        enable_lint=lint,
        memory_mb=memory_mb,
        max_procs=max_procs,
        resource_limits=resource_limits,
    )
    config.mode = Mode.HEAL
    config.tests_path = tests
    config.scaffold_tests = scaffold_tests
    _execute(config)


def _execute(config: LoopConfig) -> None:
    if config.model is None:
        config.model = DEFAULT_MODELS.get(config.provider)

    try:
        report = CorrectionLoop(config).run()
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted[/yellow]")
        raise typer.Exit(code=130) from None
    except AgentError as exc:
        console.print(f"[red]Configuration/API error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        console.print(f"[red]Unexpected error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    metrics = aggregate_metrics(report)
    _print_report_summary(
        report.mode,
        report.exit_reason,
        len(report.iterations),
        report.model,
        metrics=metrics,
    )
    if config.artifact_dir:
        console.print(f"Artifacts written to {config.artifact_dir.resolve()}")
    raise typer.Exit(code=_exit_code_for(report.exit_reason))


def run() -> None:
    app()


if __name__ == "__main__":
    app()
