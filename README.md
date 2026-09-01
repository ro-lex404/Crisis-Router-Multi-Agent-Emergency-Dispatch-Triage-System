# Crisis-Router: Multi-Agent Emergency Dispatch & Triage System

Crisis-Router is a multi-agent emergency workflow built with Google ADK, FastAPI, and Streamlit.  
It ingests distress messages, classifies urgency and incident type, geocodes locations, and allocates rescue units from a tracked registry.

## Key Features

- Multi-agent orchestration for triage, geocoding, and dispatch
- Conditional routing for emergency vs non-emergency messages
- Live FastAPI backend with stateful unit/incident tracking
- Streamlit dashboard with role-based views:
  - Civilian Distress Console
  - Dispatcher Operations Center
- Offline simulator mode for demos without live model/API calls

## Architecture

The core workflow in `/app/agent.py` is composed of:

1. **Listener Agent**: Classifies emergency status, urgency, incident type, and location
2. **Cartographer Agent**: Resolves location coordinates via `geocode_location`
3. **Dispatcher Agent**: Allocates an available rescue unit via `allocate_rescue_unit`

Shared workflow state is stored in `CrisisState`, and persistent system data is saved in `app/disaster_system.json` at runtime.

## Repository Structure

```text
app/
  agent.py           # Multi-agent workflow and tool functions
  fast_api_app.py    # FastAPI app + API routes
  dashboard.py       # Streamlit operational dashboard
  app_utils/         # Service adapters, telemetry, typing, A2A helpers
tests/
  unit/              # Unit tests
  integration/       # Integration tests
  eval/              # Evaluation datasets
```

## Prerequisites

- Python 3.11–3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- `agents-cli` (`uv tool install google-agents-cli`)

## Local Setup

1. Install project dependencies:

```bash
agents-cli install
```

2. Configure environment:

```bash
cp .env.example .env
```

Set your key in `.env`:

```env
GEMINI_API_KEY=your-gemini-api-key
```

## Run Locally

### 1) Start the FastAPI backend

```bash
uv run python -m uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000
```

### 2) Start the Streamlit dashboard (in a new terminal)

```bash
uv run streamlit run app/dashboard.py
```

### 3) Optional: ADK playground

```bash
agents-cli playground
```

## API Endpoints

- `POST /api/run_pipeline` — Process incoming distress message
- `GET /api/system_state` — Read current incidents and unit registry
- `POST /api/reset_system` — Reset incidents and unit availability
- `POST /feedback` — Submit feedback payload

## Testing & Quality

Run tests:

```bash
uv run pytest tests/unit tests/integration
```

Run lint checks:

```bash
agents-cli lint
```

## Deployment

Deploy to Agent Runtime (requires cloud setup and credentials):

```bash
agents-cli deploy
```
