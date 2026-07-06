# Project Name: Crisis-Router Multi-Agent System
**Track:** Agents for Good (Kaggle AI Agents Intensive)

## 1. Core Objective
Build an autonomous, multi-agent backend utilizing the Google Agent Development Kit (ADK). The system ingests raw, unstructured text representing natural disaster distress signals, structures the data, geolocates the incident, and dispatches the appropriate rescue resources.

## 2. Technical Stack
* **Framework:** Google ADK 2.0 (for state routing and agent definitions).
* **Models:** Gemini 1.5 Flash (for fast NLP parsing).
* **State Management:** Strictly typed Pydantic models.
* **Environment:** Python 3.12+ managed via `uv`.

## 3. Global State Object (`CrisisState`)
All agents must read from and write to a single Pydantic state object passed sequentially through the pipeline.
* `raw_message` (str): The original unstructured input.
* `urgency` (Literal['Critical', 'High', 'Moderate', 'Informational'])
* `incident_type` (str): e.g., "Medical", "Trapped", "Infrastructure".
* `location_text` (str): Extracted geographic entity.
* `coordinates` (dict): `{"lat": float, "lon": float}`
* `dispatch_plan` (str): The final assigned resource.

## 4. Agent Architecture (Sequential Routing)

### Agent 1: The Listener (Ingestion & Triage)
* **Role:** NLP processor.
* **Input:** `raw_message`.
* **Action:** Uses strict system prompting and structured JSON output to extract `urgency`, `incident_type`, and `location_text`.

### Agent 2: The Cartographer (Geocoding)
* **Role:** Tool Caller.
* **Input:** `location_text`.
* **Action:** Executes a custom Python tool calling the Nominatim (OpenStreetMap) API to fetch latitude and longitude. Updates the `coordinates` state.
* **Constraint:** Must handle API timeouts and "location not found" errors gracefully.

### Agent 3: The Dispatcher (Resource Allocation)
* **Role:** Logic Engine.
* **Input:** The populated `CrisisState`.
* **Action:** Evaluates urgency and location to assign a simulated rescue unit (e.g., "Unit 4 deployed to [Lat, Lon] for Medical emergency"). Updates the `dispatch_plan`.

## 5. Coding Rules & Guidelines
* Do not write monolithic functions; keep agent definitions isolated.
* Enforce strict type hints (`typing`) across all tool definitions.
* Include detailed docstrings for all custom tools so the ADK models understand how to use them.
* Never hardcode API keys; always use `os.environ.get()`.