# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import json
import logging
import os
import urllib.request
import urllib.parse
from typing import Literal, Optional

# Align API keys so that if the SDK insists on using GOOGLE_API_KEY, it uses the valid GEMINI_API_KEY value
if "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]



from pydantic import BaseModel, Field

from google.adk.agents import Agent, Context
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.workflow import Workflow, START, node
from google.genai import types

# Setup logger
logger = logging.getLogger("crisis_router")


# ==============================================================================
# 2. Agent Output Schemas
# ==============================================================================

class ListenerOutput(BaseModel):
    is_emergency: bool = Field(description="True if this is a genuine disaster, emergency, hazard, or crisis needing emergency first responder dispatch. False if it is spam, general conversation, or non-incident info.")
    urgency: Literal['Critical', 'High', 'Moderate', 'Informational']
    incident_type: str
    location_text: str

class CartographerOutput(BaseModel):
    lat: float
    lon: float

class DispatcherOutput(BaseModel):
    dispatch_plan: str

# ==============================================================================
# 1. Shared State Definition
# ==============================================================================

class CrisisState(BaseModel):
    """Shared state object containing all fields for crisis response pipeline."""
    raw_message: str = ""
    is_emergency: bool = True
    urgency: Literal['Critical', 'High', 'Moderate', 'Informational'] = 'Moderate'
    incident_type: str = ""
    location_text: str = ""
    coordinates: dict[str, float] = Field(default_factory=dict)
    dispatch_plan: str = ""
    
    # ADK agent output storage fields
    listener_output: Optional[ListenerOutput] = None
    coordinates_output: Optional[CartographerOutput] = None
    dispatcher_output: Optional[DispatcherOutput] = None


# ==============================================================================
# 3. Custom Tools
# ==============================================================================

def geocode_location(location_text: str) -> dict[str, float]:
    """Queries the OpenStreetMap Nominatim API to get coordinates (lat, lon) for a location.

    Args:
        location_text: The location text to geocode.

    Returns:
        A dictionary with keys 'lat' and 'lon'.
    """
    logger.info(f"Geocoding location: {location_text}")
    if not location_text:
        return {"lat": 0.0, "lon": 0.0}

    # OpenStreetMap Nominatim API request
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(location_text)}&format=json&limit=1"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Crisis-Router/1.0 (disaster-response-capstone)"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data:
                return {
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"])
                }
    except Exception as e:
        logger.warning(f"Nominatim online geocoding lookup failed: {e}. Using local fallback.")

    # Local fallback/mock logic
    loc_lower = location_text.lower()
    if "san francisco" in loc_lower or "sf" in loc_lower:
        return {"lat": 37.7749, "lon": -122.4194}
    if "new york" in loc_lower or "ny" in loc_lower:
        return {"lat": 40.7128, "lon": -74.0060}
    if "miami" in loc_lower:
        return {"lat": 25.7617, "lon": -80.1918}
    if "chicago" in loc_lower:
        return {"lat": 41.8781, "lon": -87.6298}
    if "houston" in loc_lower:
        return {"lat": 29.7604, "lon": -95.3698}
    return {"lat": 34.0522, "lon": -118.2437}

SYSTEM_DB_PATH = "app/disaster_system.json"

DEFAULT_UNITS = [
    {"name": "Fire Engine 1", "type": "Fire", "status": "Available", "dispatched_to": ""},
    {"name": "Rescue Boat 2", "type": "Flood", "status": "Available", "dispatched_to": ""},
    {"name": "Ambulance 3", "type": "Medical", "status": "Available", "dispatched_to": ""},
    {"name": "Utility Crew 4", "type": "Infrastructure", "status": "Available", "dispatched_to": ""},
    {"name": "Rescue Helicopter 5", "type": "Trapped", "status": "Available", "dispatched_to": ""},
    {"name": "Hazmat Engine 6", "type": "Other", "status": "Available", "dispatched_to": ""},
]

def load_system_db() -> dict:
    if not os.path.exists(SYSTEM_DB_PATH):
        os.makedirs(os.path.dirname(SYSTEM_DB_PATH), exist_ok=True)
        data = {"units": DEFAULT_UNITS, "incidents": []}
        with open(SYSTEM_DB_PATH, "w") as f:
            json.dump(data, f, indent=2)
        return data
    try:
        with open(SYSTEM_DB_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"units": DEFAULT_UNITS, "incidents": []}

def save_system_db(data: dict):
    os.makedirs(os.path.dirname(SYSTEM_DB_PATH), exist_ok=True)
    with open(SYSTEM_DB_PATH, "w") as f:
        json.dump(data, f, indent=2)

def allocate_rescue_unit(incident_type: str, location_text: str) -> str:
    """Allocates an available rescue unit matching the incident type and deploys it to the location.

    Args:
        incident_type: The type of incident (e.g. 'Fire', 'Flood', 'Medical', 'Infrastructure', 'Trapped', 'Other').
        location_text: The location text of the emergency.

    Returns:
        A description of the allocated rescue unit deployment action.
    """
    logger.info(f"Allocating rescue unit for type: {incident_type} at location: {location_text}")
    db = load_system_db()
    units = db.get("units", DEFAULT_UNITS)
    
    target_unit = None
    inc_type_lower = incident_type.lower()
    
    for u in units:
        if u["status"] == "Available" and u["type"].lower() in inc_type_lower:
            target_unit = u
            break
            
    if not target_unit:
        for u in units:
            if u["status"] == "Available":
                target_unit = u
                break
                
    if target_unit:
        target_unit["status"] = "Busy"
        target_unit["dispatched_to"] = location_text
        save_system_db(db)
        return f"{target_unit['name']} (Type: {target_unit['type']}) allocated and deployed to {location_text}."
    else:
        return f"No rescue units available. Dispatch request for {incident_type} at {location_text} has been queued."

# ==============================================================================
# 4. Processing & Mapping Nodes
# ==============================================================================

@node
def ingest_message(ctx: Context, node_input: str):
    """Sets the raw_message from the incoming user request into the shared state."""
    ctx.state["raw_message"] = node_input

@node
async def update_listener_state(ctx: Context) -> str:
    """Saves the output from the Listener agent into the top-level shared state fields."""
    await asyncio.sleep(3.0)
    output = ctx.state.get("listener_output")
    is_emergency = True
    if output:
        if isinstance(output, dict):
            is_emergency = output.get("is_emergency", True)
            ctx.state["is_emergency"] = is_emergency
            ctx.state["urgency"] = output.get("urgency", "Moderate")
            ctx.state["incident_type"] = output.get("incident_type", "")
            ctx.state["location_text"] = output.get("location_text", "")
        else:
            is_emergency = output.is_emergency
            ctx.state["is_emergency"] = is_emergency
            ctx.state["urgency"] = output.urgency
            ctx.state["incident_type"] = output.incident_type
            ctx.state["location_text"] = output.location_text
    return "emergency" if is_emergency else "non-emergency"

@node
async def update_cartographer_state(ctx: Context):
    """Saves the coordinates from the Cartographer agent into the shared state."""
    await asyncio.sleep(3.0)
    output = ctx.state.get("coordinates_output")
    if output:
        if isinstance(output, dict):
            ctx.state["coordinates"] = {"lat": output.get("lat", 0.0), "lon": output.get("lon", 0.0)}
        else:
            ctx.state["coordinates"] = {"lat": output.lat, "lon": output.lon}

@node
async def update_dispatcher_state(ctx: Context):
    """Saves the dispatch plan from the Dispatcher agent into the shared state."""
    await asyncio.sleep(3.0)
    output = ctx.state.get("dispatcher_output")
    if output:
        if isinstance(output, dict):
            ctx.state["dispatch_plan"] = output.get("dispatch_plan", "")
        else:
            ctx.state["dispatch_plan"] = output.dispatch_plan

@node
def finalize_response(ctx: Context) -> str:
    """Returns a final summary of the disaster response state."""
    state = ctx.state
    if not state.get("is_emergency", True):
        return "Message processed. Classified as non-emergency/informational. No dispatch required."
    return (
        f"Incident Ingested & Handled Successfully:\n"
        f"- Urgency: {state.get('urgency')}\n"
        f"- Type: {state.get('incident_type')}\n"
        f"- Location: {state.get('location_text')}\n"
        f"- Coordinates: {state.get('coordinates')}\n"
        f"- Dispatch Plan: {state.get('dispatch_plan')}"
    )

# ==============================================================================
# 5. Agent Definitions
# ==============================================================================

from functools import cached_property

class CustomGemini(Gemini):
    @cached_property
    def api_client(self):
        from google import genai
        import os
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        kwargs = {}
        if self.base_url:
            kwargs['http_options'] = {'api_version': 'v1alpha'}
            kwargs['vertex_ai'] = True
            if not self._is_vertex_ai_endpoint(self.base_url):
                kwargs['base_url'] = self.base_url
        if self.retry_options:
            kwargs['http_options'] = kwargs.get('http_options', {}) | {
                'retry_options': self.retry_options
            }
        return genai.Client(api_key=api_key, **kwargs)

# Shared Gemini configuration
shared_model = CustomGemini(
    model="gemini-2.5-flash-lite",
    retry_options=types.HttpRetryOptions(attempts=6, initial_delay=3.0),
)


listener_agent = Agent(
    name="listener_agent",
    model=shared_model,
    instruction="""You are the Listener Agent (Ingestion & Triage).
Your task is to analyze the incoming natural disaster distress signal and perform Named Entity Recognition (NER).
Extract the following information:
- is_emergency: Set to True if this is a genuine disaster, emergency, hazard, or crisis needing emergency first responder dispatch. Set to False if it is spam, a greeting, general conversation, or non-incident info.
- urgency: Must be one of 'Critical', 'High', 'Moderate', 'Informational'.
- incident_type: The type of incident, e.g., 'Flood', 'Fire', 'Medical', 'Trapped', 'Infrastructure', 'Other'.
- location_text: The location name or address mentioned.

Here is the raw message to analyze:
"{raw_message}"

Output the results strictly matching the requested output schema.""",
    output_schema=ListenerOutput,
    output_key="listener_output",
)

cartographer_agent = Agent(
    name="cartographer_agent",
    model=shared_model,
    instruction="""You are the Cartographer Agent (Geocoding).
Your task is to find the geographic coordinates (latitude and longitude) for the location.

Location to geocode:
"{location_text}"

Use the `geocode_location` tool to fetch the coordinates.
Once you receive the coordinates from the tool, output them strictly matching the requested output schema.""",
    tools=[geocode_location],
    output_schema=CartographerOutput,
    output_key="coordinates_output",
)

dispatcher_agent = Agent(
    name="dispatcher_agent",
    model=shared_model,
    instruction="""You are the Dispatcher Agent (Resource Allocation).
Your task is to assign a simulated rescue unit based on the incident state.

Incident Details:
- Urgency: {urgency}
- Incident Type: {incident_type}
- Location: {location_text}
- Coordinates: {coordinates}

Use the `allocate_rescue_unit` tool, passing the incident_type and location_text, to allocate a unit and get the dispatch description.
Do not make up a unit or dispatch plan on your own; rely strictly on the tool's response.
Output the result from the tool strictly matching the requested output schema's `dispatch_plan` field.""",
    tools=[allocate_rescue_unit],
    output_schema=DispatcherOutput,
    output_key="dispatcher_output",
)

# ==============================================================================
# 6. Workflow Creation & Orchestration
# ==============================================================================

# Sequential multi-agent workflow with conditional emergency routing
root_agent = Workflow(
    name="crisis_workflow",
    edges=[
        (START, ingest_message),
        (ingest_message, listener_agent),
        (listener_agent, update_listener_state),
        (update_listener_state, {
            "emergency": cartographer_agent,
            "non-emergency": finalize_response
        }),
        (cartographer_agent, update_cartographer_state),
        (update_cartographer_state, dispatcher_agent),
        (dispatcher_agent, update_dispatcher_state),
        (update_dispatcher_state, finalize_response),
    ],
    state_schema=CrisisState,
)

# Root App container
app = App(
    root_agent=root_agent,
    name="app",
)
