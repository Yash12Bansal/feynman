.PHONY: setup dev dev-backend dev-frontend dev-worker dev-preview-server test test-backend test-frontend lint lint-backend lint-frontend format db-up db-down db-reset migrate migrate-create share

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
	@echo "Starting worker first, then backend :8000 + frontend :5173 + preview :8080 after 3s warmup"
	@make dev-worker & \
		( sleep 3 ; make dev-backend ) & \
		( sleep 3 ; make dev-frontend ) & \
		( sleep 3 ; make dev-preview-server ) & \
		wait

# PYTHONPATH bypass: macOS Sequoia stamps UF_HIDDEN on every file inside
# `.venv/`, including `_editable_impl_*.pth`. CPython skips hidden .pth files
# silently, so editable installs of `feynman` + `feynman_teaching_kernel`
# never make it onto sys.path. Setting PYTHONPATH explicitly adds them up
# front, before site.py runs — no flag manipulation, survives every `uv sync`.
BACKEND_PYTHONPATH = src:../feynman_teaching_kernel/src

dev-backend:
	cd backend && PYTHONPATH=$(BACKEND_PYTHONPATH) uv run uvicorn feynman.main:app --reload --reload-dir src --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && pnpm dev

dev-worker:
	cd backend && PYTHONPATH=$(BACKEND_PYTHONPATH) uv run python -m feynman.livekit.worker dev

# Serves /lecture-api/chapters + /lecture-api/chapter/{id} from Neo4j on :8080.
# Required for the LectureHomeScreen picker and LectureViewer chapter fetch.
# Binds 0.0.0.0 so both IPv4 and IPv6 wildcards are covered (avoids the
# IPv4-only-bind + IPv6-localhost-resolution mismatch that bit us in Phase 2).
dev-preview-server:
	cd data_pre_compute_v2 && poetry run python tools/preview_server.py --port 8080 --host 0.0.0.0

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

# --- Sharing via ngrok (stable public URL) ---
# Tunnels the local dev stack to a public ngrok URL. The frontend on :5173
# proxies /api -> :8000 and /lecture-api -> :8080, so one tunnel exposes the
# whole app. Run `make dev` in another terminal first.
#
# Set your free ngrok static domain once (either works):
#   echo your-name.ngrok-free.app > .ngrok-domain     # recommended; gitignored
#   make share NGROK_DOMAIN=your-name.ngrok-free.app
NGROK_DOMAIN ?= $(shell cat .ngrok-domain 2>/dev/null)
share:
	@if [ -z "$(NGROK_DOMAIN)" ]; then \
		echo "No ngrok domain set. Do one of:"; \
		echo "  echo your-name.ngrok-free.app > .ngrok-domain"; \
		echo "  make share NGROK_DOMAIN=your-name.ngrok-free.app"; \
		exit 1; \
	fi
	@echo "Public link  ->  https://$(NGROK_DOMAIN)"
	@echo "Make sure 'make dev' is running and the domain is in Firebase Authorized Domains."
	ngrok http --url=$(NGROK_DOMAIN) 5173
