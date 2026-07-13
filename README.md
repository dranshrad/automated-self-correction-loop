# Automated Self-Correction Loop (ASCL)

**AGPL-3.0-or-later** · Python 3.11+ · Typer CLI

A production-minded self-healing execution harness: an LLM generates Python, an isolated subprocess runs it under hard timeouts, and a pluggable verifier decides success. Failed iterations feed a **token-aware history compressor** so long correction loops do not overflow the context window.

## Dual modes

| Command | Success gate |
|---|---|
| `ascl run` | Generated script exits `0` within `--timeout` |
| `ascl heal` | Frozen **pytest** suite passes (exit `0` alone is not enough) |

```text
generate → isolate-execute → verify → compress-history → retry
```

Only the verifier differs between `run` and `heal`.

## Why these safeguards

1. **Context-insulated execution** — Unix `resource` limits (`RLIMIT_AS`, `RLIMIT_NPROC`, `RLIMIT_CPU`) plus process-group kill, timeouts, and stdout/stderr caps.
2. **Multi-stage verification** — `ast.parse` → optional `ruff` E/F → behavioral (`run` exit code / `heal` pytest). Static failures never spawn the heavyweight runner.
3. **AST diff history** — structural function/class deltas replace monolithic code dumps in the correction prompt.
4. **Oscillation circuit breaker** — rolling code hashes detect A↔B thrashing and inject an architectural-change directive.
5. **Frozen test scaffolds in `heal`** — the model cannot “fix” the goalposts.

```text
generate → static checks → isolate-execute → verify → AST-diff history → retry
                 ↘ syntax/lint fail (cheap)        ↗ oscillation warning
```

## Install

```bash
# Requires Python 3.11+ and Poetry
poetry install

# Or with pip / venv
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"  # if using a PEP 621 export; otherwise: poetry install
```

With Poetry (recommended):

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
| 1 | Max iterations exhausted / verification never passed |
| 2 | Configuration or API error |
| 130 | Interrupted |

## Layout

```text
src/ascl/
  cli.py              # Typer: run | heal | version
  loop.py             # Shared loop + oscillation detector
  agent.py            # Anthropic / OpenAI / Mock
  runner.py           # Tempdir + Popen + timeout + RLIMIT_* caps
  parser.py           # Fenced code extraction
  history_manager.py  # Token-budget pruning + AST diff injection
  ast_diff.py         # Structural function/class diffs
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

ASCL executes **model-generated code** in a subprocess. Timeouts and output caps are **best-effort isolation**, not a container/seccomp jail. See [SECURITY.md](SECURITY.md).

## License

This project is licensed under the **GNU Affero General Public License v3.0 or later**. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

If you run a modified version as a network service, AGPL requires you to offer the corresponding source to users who interact with it remotely.

## Roadmap (out of v1)

- Docker / seccomp / gVisor jail (beyond `resource` limits)
- cgroup memory limits on Linux hosts
- Multi-file project healing
- Exact tokenizer-backed budgets (tiktoken)
