# 🏎 Forza Tuner

Real-time Forza Motorsport & Forza Horizon telemetry analysis dashboard with deterministic physics-based tuning recommendations, customizable tuning goals, and optional Ollama LLM AI assist.

---

## Features

- **Live Telemetry Dashboard** — 15 Hz WebSocket feed of speed, tyre temps, suspension travel, lateral/longitudinal G-forces, RPM, and tyre slip ratios
- **Game Profile Toggle** — Switch between Forza Motorsport (FM) and Forza Horizon (FH) packet formats at runtime (with dynamic physics scaling)
- **Comprehensive Tuning Form** — Full metric/imperial toggle with a 10-section accordion layout mirroring the exact in-game menu (including Dampers, Aero, Brakes, Differential, and Gearing)
- **Tuning Goal Selector** — Tailor recommendations for **Balanced**, **Grip / Cornering**, **Drift**, or **Speed / Drag**
- **Deterministic Physics Engine** — Instant, reproducible tuning recommendations derived from tyre temperature deltas, peak suspension travel, and lateral roll ratios
- **Upgrade Detection & Hints** — Recommends upgrade parts (e.g. Race Springs, Race ARBs, or softer tyre compounds) when stock parts lack adjustability or overheat
- **AI Assist (Optional)** — Pluggable Ollama LLM strategy with an async GPU worker queue
- **Multi-Tenant Architecture** — Every entity scoped by `user_id` (defaults to `local_admin`); ready for Cloudflare Access SSO integration
- **Containerized & Portainer Ready** — Deploy easily via `docker compose` or Portainer stacks with configurable ports

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker on Linux (recommended)
- Or Python 3.11+ for local development

---

### Deployment Options

#### Option A: Docker Compose (Local / Server CLI)

```bash
# 1. Clone the repository
git clone https://github.com/DogTKD520/forza-tuner.git
cd forza-tuner

# 2. Copy and configure environment variables
cp .env.example .env

# 3. Build and start containers
docker compose up -d --build

# 4. Access the dashboard in your browser
open http://localhost:8000
```

#### Option B: Portainer / Server Stack Deployment

When deploying via Portainer, create a new Stack, paste the repository URL or `docker-compose.yml`, and configure your environment variables:

| Environment Variable | Recommended Value | Notes |
|----------------------|-------------------|-------|
| `PORT` | `8001` (or desired host port) | Host HTTP port mapping (`PORT:8000`) |
| `UDP_PORT` | `5300` | Host UDP telemetry port mapping (`UDP_PORT:5300/udp`) |
| `DEFAULT_GAME` | `FM` or `FH` | Initial active game profile |
| `USE_LLM` | `False` | Set `True` if Ollama is accessible |

> **Note on Port Mapping:** Host port `${PORT}` automatically forwards into container port `8000`. If you set `PORT=8001` in Portainer, access your dashboard at `http://<server-ip>:8001`.

#### Option C: Local Development (Python 3.11+)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows PowerShell
# source .venv/bin/activate   # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup environment and data directory
cp .env.example .env
mkdir data

# 4. Start server
python -m app.main
```

---

## Forza Game Setup (Data Out)

To stream telemetry into Forza Tuner, enable **Data Out** in your game settings:

1. Open Forza Motorsport or Forza Horizon.
2. Go to **Settings** → **HUD & Gameplay** → scroll to **Data Out**.
3. Configure the following fields:

| Setting | Value |
|---------|-------|
| **Data Out** | `On` |
| **Data Out IP Address** | Your server or PC local IP (e.g. `192.168.1.100`) |
| **Data Out IP Port** | `5300` (must match `UDP_PORT` in `.env`) |
| **Data Out Packet Format** | **`Car Dash`** |

---

## How to Use

1. **Select Game Profile**: Toggle between **FM** (Forza Motorsport) and **FH** (Forza Horizon) in the top header.
2. **Input Baseline Setup**: Fill in your car's current pressures, camber, springs, and ARB settings in the **Vehicle Setup** panel and click **Save**.
3. **Choose Tuning Goal**: Select your target driving style (**Balanced**, **Grip / Cornering**, **Drift**, or **Speed / Drag**).
4. **Record Session**: Click **▶ Start Recording** before taking your car out on track.
5. **Analyze**: Drive a few laps, click **■ Stop**, then click **⚡ Analyse Session**. Instant recommendations will populate showing exact parameter adjustments and mathematical justifications.

---

## Configuration Reference

All settings can be customized in `.env` (copied from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Host HTTP dashboard port |
| `UDP_PORT` | `5300` | Host UDP telemetry port |
| `DEFAULT_GAME` | `FM` | Default game format (`FM` \| `FH`) |
| `DEFAULT_USER_ID` | `local_admin` | Multi-tenant user identity scope |
| `DATABASE_URL` | `sqlite:///./data/forza_tuner.db` | SQLite database path |
| `WEBSOCKET_FPS` | `15` | Live dashboard refresh rate (Hz) |
| `USE_LLM` | `False` | Enable Ollama LLM strategy |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Model name for LLM analysis |

---

## Physics Rules & Tuning Thresholds

Tuning rule parameters are stored in [`config/tuning_rules.json`](config/tuning_rules.json). You can modify target temperature deltas and adjustment step sizes without touching application code:

| Component | Rule Logic |
|-----------|------------|
| **Tyre Pressure** | Compares center temperature against average of inner and outer edge temperatures to fix over/under-inflation. |
| **Camber** | Measures inner vs outer edge temperature differential under lateral load. Adjusts negative camber magnitude toward goal target. |
| **Spring Rates** | Monitors peak suspension travel. Recommends stiffening on bottom-out (`>= 95%`) or softening on under-travel (`< 70%`). |
| **Anti-Roll Bars (ARBs)** | Evaluates front vs rear roll compression ratios to balance turn-in understeer vs oversteer. |
| **Upgrades & Advice** | Warns when non-tunable stock parts prevent adjustments, or when sustained tyre overheating suggests softer compound upgrades within PI budget. |

---

## Running Tests

Run the full pytest suite (31+ tests covering packet parsing, strategy analysis, tuning goals, and GPU queuing):

```bash
pytest -v
```

---

## Future / SaaS Roadmap

The codebase is structured to allow future expansion **without refactoring**:

- **SSO Authentication**: Replace `DEFAULT_USER_ID` in `repositories.py` with Cloudflare Access header (`CF-Access-Authenticated-User-Email`).
- **Remote Telemetry Agents**: Implement `AbstractTelemetryProcessor` over WebSockets for client PCs running far from the server.
- **GPU Queueing**: Enable `USE_LLM=True` to queue AI analysis requests sequentially without VRAM collisions.

---

## License

MIT
