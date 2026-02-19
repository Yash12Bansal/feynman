.PHONY: setup dev dev-backend dev-frontend test test-backend test-frontend lint lint-backend lint-frontend format db-up db-down db-reset

# =============================================================================
# Feynman — Development Commands
# =============================================================================

# --- Setup ---
setup:
	@echo "Setting up Feynman..."
	cd backend && uv sync --all-extras
	cd frontend && pnpm install
	docker compose up -d
	@echo "Waiting for services..."
	@sleep 3
	@echo "Done! Run 'make dev' to start."

# --- Development ---
dev:
	@echo "Starting backend on :8000 and frontend on :5173"
	@make dev-backend & make dev-frontend & wait

dev-backend:
	cd backend && uv run uvicorn feynman.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && pnpm dev

# --- Testing ---
test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest -x -v

test-frontend:
	cd frontend && pnpm test --run

# --- Linting ---
lint: lint-backend lint-frontend

lint-backend:
	cd backend && uv run ruff check src/ tests/
	cd backend && uv run ruff format --check src/ tests/

lint-frontend:
	cd frontend && pnpm lint

# --- Formatting ---
format:
	cd backend && uv run ruff format src/ tests/
	cd backend && uv run ruff check --fix src/ tests/
	cd frontend && pnpm format

# --- Docker / Database ---
db-up:
	docker compose up -d

db-down:
	docker compose down

db-reset:
	docker compose down -v
	docker compose up -d
