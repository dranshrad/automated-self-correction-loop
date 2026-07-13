# Contributing

Thanks for improving Automated Self-Correction Loop (ASCL).

## Development setup

```bash
poetry install --with dev
poetry run ruff check src tests
poetry run ruff format src tests
poetry run mypy
ASCL_PROVIDER=mock poetry run pytest
```

## Guidelines

- Keep types strict (`mypy --strict` on `src/ascl`).
- Prefer small, focused PRs.
- Do not commit API keys, `.env`, or live run artifacts containing secrets.
- New verifier behavior needs unit tests; loop behavior needs an integration test with `MockAgent`.
- Never weaken timeout / process-group kill / output-cap guarantees without discussion.

## License of contributions

By contributing, you agree that your contributions are licensed under the **AGPL-3.0-or-later**, the same license as this repository.
