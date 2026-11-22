# Contributing to wasitme

Thank you for your interest in contributing to `wasitme`!

## 1. Ground Rules & Invariants
- **Scope Discipline:** `wasitme` solves one problem: post-deploy blame attribution. Feature requests for in-cluster dashboards, persistent databases, or cluster mutations will be politely closed.
- **Client-Side Only:** No cluster mutations (`kubectl apply/delete/patch`). Read-only `kubectl get` only.
- **Zero Heavy Dependencies:** Runtime dependencies are strictly limited to `typer` and `rich`. All other capabilities use the standard library.
- **Determinism:** `differ.py` must remain 100% deterministic with zero I/O.
- **DCO Sign-Off:** All commits require Developer Certificate of Origin (`git commit -s`).

## 2. Local Development Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/nithink/wasitme.git
   cd wasitme
   ```
2. Set up virtual environment using `uv` (recommended) or standard venv:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e ".[dev]"
   ```
3. Run test suite:
   ```bash
   pytest
   ```
4. Run linters & typecheckers:
   ```bash
   ruff check src tests
   mypy src
   ```

## 3. Submitting Pull Requests
- Keep PRs small and focused on a single concern.
- Add unit tests for any bugfix or edge case.
- PRs modifying `differ.py` must maintain $\ge 95\%$ test coverage.
