#!/bin/bash

# Check if the environment file exists
if [ ! -f .env.docker ]; then
    echo "Environment file .env.docker not found"
    exit 1
fi

docker compose --env-file .env.docker up -d

echo "Local development environment started"
