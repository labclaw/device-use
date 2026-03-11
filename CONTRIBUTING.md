# Contributing to device-use

## Setup

```bash
pip install -e ".[dev,nmr]"
pre-commit install
```

## Running tests

```bash
make test
```

Tests run with `PYTHONPATH=src` so imports resolve correctly.

## Code style

- **Linter/formatter:** ruff (line-length 100)
- **Lint rules:** E, F, I, N, W, UP
- **Type hints** required on all public function signatures
- **Pydantic** for all data schemas
- **`from __future__ import annotations`** in every module

Run `make lint` to check and `make format` to auto-fix.

## Branch naming

- `feat/` -- new features
- `fix/` -- bug fixes
- `docs/` -- documentation only
- `refactor/` -- code restructuring, no behavior change
- `test/` -- adding or updating tests

## Commit format

Use [conventional commits](https://www.conventionalcommits.org/):

```
feat(nmr): add temperature series processing
fix(orchestrator): handle timeout in parallel steps
test(plate-reader): add edge cases for empty wells
```

## Pull request process

1. One concern per PR -- do not bundle unrelated changes.
2. `make lint` and `make test` must pass.
3. Add or update tests for any behavior change.
4. Fill out the PR template completely.
5. Request review from `@labclaw/core-team`.
