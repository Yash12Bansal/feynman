# Feynman

AI teaching agent for school classrooms. Real-time voice + rich visual aids.

## Prerequisites

- **Python 3.13+** — `brew install python@3.13`
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node.js 18+** — `brew install node`
- **pnpm** — `npm install -g pnpm`
- **Docker Desktop** — [docker.com](https://www.docker.com/products/docker-desktop/)

## Setup

```bash
# 1. Clone and enter
git clone <repo-url> && cd feynman

# 2. Create .env and fill in API keys
cp .env.example .env

# 3. Start containers (Postgres:5433, Redis:6379, LiveKit:7880)
docker compose up -d

# 4. Install deps + run DB migrations
make setup

# 5. Start dev servers (backend :8000, frontend :5173)
make dev
```

### Required API keys in `.env`

| Key | What for |
|-----|----------|
| `ANTHROPIC_API_KEY` | LLM (Claude) |
| `OPENAI_API_KEY` | LLM (GPT) |
| `DEEPGRAM_API_KEY` | Speech-to-text |
| `CARTESIA_API_KEY` | Text-to-speech |

LiveKit, Postgres, and Redis keys have working local defaults — no changes needed.

### LiveKit agent worker (separate terminal)

```bash
make dev-worker
```

## Design Agent (standalone diagram tool)

Separate mini-app in `design_agent/`. Has its own deps — does not use `uv` or `pnpm`.

```bash
# 1. Backend setup
cd design_agent/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY

# 2. Start backend (from design_agent/)
cd ..
python -m backend.main   # http://localhost:8000

# 3. Frontend setup + start (separate terminal)
cd design_agent/frontend
npm install && npm start   # http://localhost:3001
```

> **Note:** Design agent backend also uses port 8000. Don't run it simultaneously with the main backend.

## Common Commands

```bash
make dev              # Start backend + frontend
make dev-backend      # Backend only
make dev-frontend     # Frontend only
make dev-worker       # LiveKit agent worker
make test             # Run all tests
make lint             # Lint everything
make format           # Auto-format
make db-up            # Start containers
make db-down          # Stop containers
make db-reset         # Wipe DB + restart containers
make migrate          # Run DB migrations
```
