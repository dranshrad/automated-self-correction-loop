# Automated Self-Correction Loop (ASCL)

**Execution-grounded verified repair engine** · **AGPL-3.0-or-later** · Python 3.11+ · Typer CLI

ASCL is not an LLM retry wrapper. It is a sandboxed, diagnosis-driven repair loop:

**Reasoning → Execution → Observation → Diagnosis → Repair → Verification → Metrics**

An LLM proposes Python; static checks and an isolated subprocess observe the result; a deterministic **failure taxonomy** diagnoses the class of failure; taxonomy-conditioned repair directives + AST-diff history steer the next attempt; rich metrics make reliability measurable.

## Dual modes

| Command | Success gate |
|---|---|
| `ascl run` | Generated script exits `0` within `--timeout` |
| `ascl heal` | Frozen **pytest** suite passes (exit `0` alone is not enough) |

## Architecture

```mermaid
flowchart TD
  prompt[TaskPrompt] --> gen[Generator]
  gen --> static[StaticAnalysis]
  static -->|fail| classify[FailureClassifier]
  static -->|pass| exec[SandboxedExecution]
  exec --> verify[BehavioralVerifier]
  verify -->|fail| classify
  classify --> repairHint[TaxonomyRepairDirective]
  repairHint --> hist[ASTDiffHistory]
  hist --> gen
  verify -->|pass| metrics[MetricsAggregator]
  classify --> metrics
  metrics --> artifacts[report_json_plus_metrics_json]
```

```text
generate → static checks → isolate-execute → verify → diagnose → AST-diff history → retry
                 ↘ syntax/lint fail (cheap)              ↗ oscillation / taxonomy hints
```

Only the behavioral verifier differs between `run` and `heal`.

## Why these safeguards

1. **Context-insulated execution** — Unix `resource` limits (`RLIMIT_AS`, `RLIMIT_NPROC`, `RLIMIT_CPU`) plus process-group kill, timeouts, and stdout/stderr caps.
2. **Multi-stage verification** — `ast.parse` → optional `ruff` E/F → behavioral (`run` exit code / `heal` pytest).
3. **Failure taxonomy** — deterministic classification (syntax, lint, timeout, memory, import, assertion, logic, …) with specialized repair directives.
4. **AST diff history** — structural function/class deltas replace monolithic code dumps.
5. **Oscillation circuit breaker** — rolling code hashes detect A↔B thrashing.
6. **Frozen test scaffolds in `heal`** — the model cannot “fix” the goalposts.
7. **Rich metrics** — `metrics.json` + CLI summary (iterations, first-pass, oscillations, token estimates, class histogram).

## Failure taxonomy

| Class | Typical signal | Repair focus |
|---|---|---|
| `syntax` | `ast.parse` / SyntaxError | Fix parse errors only |
| `lint` | ruff E/F | Minimal lint fixes |
| `timeout` | process timed out | Remove unbounded work |
| `memory` | MemoryError / RLIMIT hints | Shrink allocations |
| `import` | ModuleNotFoundError | Stdlib / local helpers |
| `dependency` | ImportError | Avoid missing packages |
| `assertion` | pytest / AssertionError | Meet test expectations |
| `logic` | nonzero exit, unclear signal | Correct behavior |
| `environment` | missing tests / config | Self-contained module |
| `oscillation` | repeated code digest | Change architecture |
| `unknown` | fallback | Inspect details |

## Design rationale (vs retry wrappers)

Most “agent coding” demos ask a model to regenerate until something works. ASCL treats the LLM as a proposer inside a **control loop** with:

- cheap static rejection before sandbox spend
- process isolation against runaway code
- diagnosis before the next prompt (not raw stderr alone)
- measurable outcomes for research and regression

## Install

```bash
poetry install --with dev
export ASCL_PROVIDER=mock   # no API key needed for demos/CI
```

## Quick start

```bash
# Exit-code mode (mock provider — no API key)
poetry run ascl run \
  --provider mock \
  --prompt "Print hello from ascl mock and exit 0" \
  --artifact-dir ./artifacts/hello

# Heal mode against a frozen pytest suite
poetry run ascl heal \
  --provider mock \
  --prompt "$(cat examples/fibonacci/PROMPT.txt)" \
  --tests examples/fibonacci/test_fib.py \
  --max-iterations 4 \
  --artifact-dir ./artifacts/fib
```

Artifacts include `report.json` (per-iteration taxonomy) and `metrics.json`.

Live providers:

```bash
export ANTHROPIC_API_KEY=sk-...
poetry run ascl run --provider anthropic --prompt "Write a script that prints 42"

export OPENAI_API_KEY=sk-...
poetry run ascl heal --provider openai --tests path/to/tests --prompt "..."
```

## CLI exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Max iterations / oscillation / verification never passed |
| 2 | Configuration or API error |
| 130 | Interrupted |

## Layout

```text
src/ascl/
  cli.py              # Typer: run | heal | version
  loop.py             # Shared loop + oscillation + diagnosis wiring
  agent.py            # Anthropic / OpenAI / Mock
  runner.py           # Tempdir + Popen + timeout + RLIMIT_* caps
  parser.py           # Fenced code extraction
  history_manager.py  # Token-budget pruning + AST diff injection
  ast_diff.py         # Structural function/class diffs
  taxonomy.py         # Failure classifier + repair hints
  metrics.py          # Run metrics aggregation
  verifiers.py        # syntax → lint → behavioral pipeline
  models.py           # Dataclasses / enums
  prompts.py          # System + correction templates
```

## Sandbox knobs

```bash
poetry run ascl run --provider mock --prompt "..." \
  --memory-mb 256 --max-procs 32 --lint \
  --resource-limits
```

Use `--no-resource-limits` or `--no-lint` when debugging the harness itself.

## Security

ASCL executes **model-generated code** in a subprocess. Timeouts, output caps, and `resource` limits are **best-effort isolation**, not a container/seccomp jail. See [SECURITY.md](SECURITY.md).

## Roadmap

| Version | Focus |
|---|---|
| **v0.3** (current) | Failure taxonomy, taxonomy-aware repair directives, rich metrics, positioning docs |
| **v0.5** | Learning memory (persist successful repair patterns), semantic traces |
| **v1.0** | Multi-agent specialized repair, knowledge retrieval, adaptive policies |
| **v2.0** | Autonomous software improvement platform (repo-wide graphs, benchmarks) |

Also deferred: Docker/gVisor jail, cgroup limits, multi-file healing, tiktoken budgets, HumanEval/SWE-bench harnesses.

## License

This project is licensed under the **GNU Affero General Public License v3.0 or later**. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

If you run a modified version as a network service, AGPL requires you to offer the corresponding source to users who interact with it remotely.
