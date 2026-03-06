#!/bin/bash

set -euxo pipefail

uv run --env-file .env.tests pytest

echo "Tests completed"
