# Contributing to context-use

## Development setup

```bash
git clone https://github.com/onfabric/context-use.git
cd context-use
uv sync
uv run pre-commit install
```

`uv sync` installs all dependencies including dev and all optional extras (`gcs`, `mcp-use`, `adk`).

Run tests:

```bash
uv run pytest
```

Type checking and linting:

```bash
uv run pyright
uv run ruff check --fix
uv run ruff format
```

---

## Releasing

Releases are automated via GitHub Actions and [git-cliff](https://git-cliff.org/) for changelog generation. Follow [Conventional Commits](https://www.conventionalcommits.org/) so that changelogs are generated correctly.

The `context-use` package is published to [PyPI](https://pypi.org/).

### 1. Prepare a release

Trigger the **prepare-release** workflow from the Actions tab (manual `workflow_dispatch` on `main`). It will:

- Compute the next version from commit history using git-cliff
- Update `version` in `pyproject.toml`
- Regenerate `CHANGELOG.md`
- Push a `release/v<version>` branch and open a PR

### 2. Merge the release PR

Review and merge the PR into `main`.

### 3. Tag and publish

After merging, tag the release and push the tag:

```bash
git checkout main && git pull
git tag v<version>
git push origin v<version>
```

Pushing the tag triggers the **publish** workflow, which builds the package, publishes to PyPI via [trusted publishing](https://docs.pypi.org/trusted-publishers/), and creates a GitHub Release with the changelog.
