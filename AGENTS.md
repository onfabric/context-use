# Code Style

- Never add decorative or separator comments (e.g. `# ----`, `# ====`, `# ***`). The code structure should speak for itself.
- Never add doc comments unless the entity genuinely needs an explanation that good naming and scoping cannot convey.
- Don't make sweeping refactors alongside feature work. Keep diffs focused.
- Always clean up after yourself: remove unused imports, variables, functions, fields, classes, and modules. Eliminate code duplication.
- Write type-safe code. Add type annotations to all function signatures and avoid `Any` where a concrete type is possible.

# Workflow for Non-Trivial Tasks

1. **Plan first.** Before writing code, identify the files that need changes and consider edge cases.
2. **Implement.** Write clean, minimal code that solves the problem.
3. **Verify.** Run `uv run pyright` and `uv run pytest` and fix any errors before committing.
4. **Update docs.** If your changes affect documented behavior, update `README.md` and any relevant files in `docs/` in the same PR.

# Testing

- Tests are mandatory for new functions, methods, and classes.
- Tests must verify actual behavior, not just mock everything.
- Cover both happy paths and edge cases.
- Aim for high coverage — if you add or change logic, it should be exercised by tests.
- **CLI:** There are no automated tests for the CLI yet (TODO). When changing CLI behavior, verify manually by running `uv run context-use ...` directly.

# Public API

- This package is published to PyPI. Before modifying any public API, flag whether the change is breaking and get explicit approval.

# Git

- Always use [Conventional Commits](https://www.conventionalcommits.org/) for PR titles (PRs are squash-merged, so the title becomes the commit message).

# Guides

- [Adding a data provider](docs/add-provider/AGENTS.md)
