#!/bin/bash

uv run --env-file .env.tests pytest

echo "Tests completed"
