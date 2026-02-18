# context-use

## Development

Install the dependencies:

```bash
uv sync
```

Install the pre-commit hooks:

```bash
uv run pre-commit install
```

Test the project:

```bash
uv run pytest
```

Run the tests:
```bash
uv run pytest
```

## Type Checking

Run the type checker:

```bash
uv run pyright
```

## Code Style

Lint:

```bash
uv run ruff check --fix
```

Format:

```bash
uv run ruff format
```
