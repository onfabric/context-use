# context-use

## Run locally

### Start the local environment

Make sure to have the environment file `.env.docker` with the correct values. See [`env.docker.example`](.env.docker.example).

Then, start the local development environment:

```bash
./scripts/start-local.sh
```

### Stop the local environment

```bash
./scripts/stop-local.sh
```

## Development

Install the dependencies:

```bash
uv sync
```

Install the pre-commit hooks:

```bash
uv run pre-commit install
```

## Testing

Make sure to have the environment file `.env.tests` with the correct values. See [`env.tests.example`](.env.tests.example).

Prepare the test environment:

```bash
./scripts/prepare-tests.sh
```

Run the tests:

```bash
./scripts/run-tests.sh
```

Stop the test environment:

```bash
./scripts/shutdown-tests.sh
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
