#!/usr/bin/env bash
set -euo pipefail

echo "=== Feynman — Local Setup ==="

# Backend
echo "Installing backend dependencies..."
cd "$(dirname "$0")/../backend"
uv sync --all-extras

# Frontend
echo "Installing frontend dependencies..."
cd "$(dirname "$0")/../frontend"
pnpm install

# Docker services
echo "Starting Docker services (PostgreSQL, Redis, LiveKit)..."
cd "$(dirname "$0")/.."
docker compose up -d

echo ""
echo "Waiting for services to be healthy..."
sleep 5

echo ""
echo "=== Setup complete! ==="
echo "Run 'make dev' to start the development servers."
