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

1. **Dynamic safe-execution / test harness** — `heal` runs candidates against a user-provided or once-scaffolded pytest suite; tests are frozen so the model cannot “fix” the goalposts.
2. **Infinite-loop & timeout protections** — `subprocess.Popen` with process-group kill, default 5s timeout, and stdout/stderr byte caps.
3. **Token-aware context window decimator** — preserves system rules, the original task, and the latest crash log; compresses older iterations after iteration 3 under `--max-context-tokens`.

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
  loop.py             # Shared correction loop
  agent.py            # Anthropic / OpenAI / Mock
  runner.py           # Tempdir + Popen + timeout + caps
  parser.py           # Fenced code extraction
  history_manager.py  # Token-budget pruning
  verifiers.py        # ExitCodeVerifier | PytestVerifier
  models.py           # Dataclasses / enums
  prompts.py          # System + correction templates
```

## Security

ASCL executes **model-generated code** in a subprocess. Timeouts and output caps are **best-effort isolation**, not a container/seccomp jail. See [SECURITY.md](SECURITY.md).

## License

This project is licensed under the **GNU Affero General Public License v3.0 or later**. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

If you run a modified version as a network service, AGPL requires you to offer the corresponding source to users who interact with it remotely.

## Roadmap (out of v1)

- Docker / seccomp jail
- cgroup memory limits
- Multi-file project healing
- Exact tokenizer-backed budgets (tiktoken)
