# Code Style

- Never add decorative or separator comments (e.g. `# ----`, `# ====`, `# ***`). The code structure should speak for itself.
- Never add doc comments unless the entity genuinely needs an explanation that good naming and scoping cannot convey.
- Don't make sweeping refactors alongside feature work. Keep diffs focused.

# Testing

- Tests are mandatory for new functions, methods, and classes.
- Tests must verify actual behavior, not just mock everything.

# Public API

- This package is published to PyPI. Before modifying any public API, flag whether the change is breaking and get explicit approval.

# Git

- Always use [Conventional Commits](https://www.conventionalcommits.org/) for PR titles (PRs are squash-merged, so the title becomes the commit message).

# Guides

- [Adding a data provider](docs/add-provider.md)
