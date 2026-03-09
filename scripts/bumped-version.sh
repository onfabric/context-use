#!/bin/bash

set -euo pipefail

raw=$(uv run git-cliff --bumped-version 2>/dev/null)
echo "${raw#v}"
