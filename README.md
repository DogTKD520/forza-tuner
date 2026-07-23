# 🏎 Forza Tuner

Real-time Forza Motorsport & Forza Horizon telemetry analysis dashboard with deterministic physics-based tuning recommendations and optional Ollama LLM AI assist.

---

## Features

- **Live Telemetry Dashboard** — 15 Hz WebSocket feed of speed, tyre temps, suspension travel
- **Game Profile Toggle** — Switch between Forza Motorsport (FM) and Forza Horizon (FH) packet formats at runtime
- **Deterministic Tuning Engine** — Instant, reproducible recommendations from tyre temperature deltas and suspension data (no LLM required)
- **AI Assist (Optional)** — Pluggable Ollama LLM strategy with a GPU-safe async queue
- **Multi-Tenant Architecture** — Every entity scoped by `user_id` (defaults to `local_admin`); ready for Cloudflare Access SSO integration
- **Containerized** — Single `docker compose up` to run

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (recommended)
- Or Python 3.11+ for local development

### With Docker (recommended)

```bash
# 1. Copy and edit the environment file
cp .env.example .env

# 2. Build and start
docker compose up --build

# 3. Open your browser
open http://localhost:8000
```

### Local Development (Python 3.11+)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy environment template
cp .env.example .env

# 4. Create the data directory
mkdir data

# 5. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Forza Configuration

In your Forza game's HUD & Gameplay settings, enable **Data Out** and point it to your machine's IP address on port **5300**.

| Setting | Value |
|---------|-------|
| Data Out | On |
| Data Out IP Address | `<your machine's IP>` |
| Data Out IP Port | `5300` |
| Data Out Packet Format | **Car Dash** |

---

## Usage

1. **Select your game** using the FM / FH toggle in the header
2. **Enter your current car setup** in the Vehicle Setup panel and click **Save**
3. **Click Start Recording** before heading out on track
4. **Drive your session** — telemetry data streams in live via UDP
5. **Click Stop** when done, then **Analyse Session** for instant recommendations
6. **Enable AI Assist** toggle before analysing to use the Ollama LLM (requires `USE_LLM=True` in `.env` and a running Ollama instance)

---

## Configuration

All options are set in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | HTTP server port |
| `UDP_PORT` | `5300` | Forza telemetry UDP port |
| `DEFAULT_GAME` | `FM` | Default game profile (`FM` or `FH`) |
| `DEFAULT_USER_ID` | `local_admin` | User identity for all database records |
| `DATABASE_URL` | `sqlite:///./data/forza_tuner.db` | SQLite database path |
| `WEBSOCKET_FPS` | `15` | Live telemetry WebSocket frame rate |
| `USE_LLM` | `False` | Enable Ollama LLM analysis strategy |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Model name for LLM analysis |

---

## Tuning Rules

The `MathBaselineAnalyzer` rules and thresholds are in [`config/tuning_rules.json`](config/tuning_rules.json). Edit this file to adjust sensitivities without touching code:

| Rule | Logic |
|------|-------|
| **Tyre Pressure** | Centre tyre temperature vs average of inner+outer edges |
| **Camber** | Inner vs outer temperature differential under lateral load |
| **Spring Rate** | Peak suspension travel utilisation (target: 70–90%) |
| **Anti-Roll Bars** | Front vs rear average suspension travel ratio |

---

## Project Structure

```
forza-tuner/
├── app/
│   ├── main.py              # FastAPI entry point + lifespan
│   ├── config.py            # Pydantic Settings (all config in one place)
│   ├── analysis/            # Strategy pattern analysis engine
│   │   ├── base.py          # AnalysisStrategy ABC
│   │   ├── math_analyzer.py # MathBaselineAnalyzer (deterministic)
│   │   ├── ollama_analyzer.py # OllamaAnalyzer (LLM)
│   │   └── gpu_queue.py     # Async single-concurrency task queue
│   ├── api/
│   │   ├── routes.py        # REST endpoints
│   │   └── websocket.py     # Live telemetry WebSocket
│   ├── db/
│   │   ├── models.py        # SQLModel ORM tables
│   │   ├── database.py      # Engine + session factory
│   │   └── repositories.py  # user_id-scoped data access layer
│   ├── ingestion/
│   │   ├── base.py          # AbstractTelemetryProcessor interface
│   │   ├── parser.py        # ForzaPacketParser (FM + FH byte layouts)
│   │   ├── session_aggregator.py # Rolling session statistics
│   │   └── udp_listener.py  # Async UDP socket → TelemetryProcessor
│   └── static/              # Dashboard frontend (HTML/CSS/JS)
├── config/
│   └── tuning_rules.json    # Configurable analysis thresholds
├── tests/                   # pytest test suite
├── .env.example             # Environment template
├── docker-compose.yml
└── Dockerfile
```

---

## Running Tests

```bash
pip install -r requirements.txt
pytest
```

---

## Future / SaaS Roadmap

The architecture is explicitly designed to support these features **without refactoring**:

- **Multi-tenant users** — replace `DEFAULT_USER_ID` with Cloudflare Access `CF-Access-Authenticated-User-Email` header in `repositories.py`
- **Remote telemetry agents** — implement `AbstractTelemetryProcessor` with a WebSocket client instead of UDP listener
- **GPU LLM analysis** — set `USE_LLM=True` and point `OLLAMA_HOST` at your Ollama instance
- **Additional game support** — add a new layout to `ForzaPacketParser` without touching other modules

---

## License

MIT
