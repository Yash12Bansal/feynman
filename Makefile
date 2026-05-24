.PHONY: setup dev dev-backend dev-frontend dev-worker dev-preview-server test test-backend test-frontend lint lint-backend lint-frontend format db-up db-down db-reset migrate migrate-create

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
	cd backend && uv run alembic upgrade head
	@echo "Done! Run 'make dev' to start."

# --- Development ---
dev:
	@echo "Starting backend on :8000, frontend on :5173, preview server on :8080"
	@make dev-backend & make dev-frontend & make dev-preview-server & wait

dev-backend:
	cd backend && uv run uvicorn feynman.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && pnpm dev

dev-worker:
	cd backend && uv run python -m feynman.livekit.worker dev

# Serves /lecture-api/chapters + /lecture-api/chapter/{id} from Neo4j on :8080.
# Required for the LectureHomeScreen picker and LectureViewer chapter fetch.
dev-preview-server:
	cd data_pre_compute_v2 && poetry run python tools/preview_server.py --port 8080

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

# --- Migrations ---
migrate:
	cd backend && uv run alembic upgrade head

migrate-create:
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

# --- Docker / Database ---
db-up:
	docker compose up -d

db-down:
	docker compose down

db-reset:
	docker compose down -v
	docker compose up -d
