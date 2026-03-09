#!/bin/bash

set -euxo pipefail

{
    uv run git-cliff --bump --unreleased
    echo
    cat CHANGELOG.md
} > CHANGELOG.tmp && mv CHANGELOG.tmp CHANGELOG.md
