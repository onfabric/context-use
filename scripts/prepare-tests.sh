#!/bin/bash

set -euxo pipefail

docker compose --env-file .env.tests up -d
