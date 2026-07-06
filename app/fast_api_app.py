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

import contextlib
import os
from collections.abc import AsyncIterator

# Align API keys so that if the SDK insists on using GOOGLE_API_KEY, it uses the valid GEMINI_API_KEY value
if "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]



import google.auth
from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.cloud import logging as google_cloud_logging

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.app_utils.reasoning_engine_adapter import (
    attach_reasoning_engine_routes,
)
from app.app_utils.telemetry import (
    setup_agent_engine_telemetry,
    setup_telemetry,
)
from app.app_utils.typing import Feedback

load_dotenv(override=True)
# Align API keys so that if the SDK insists on using GOOGLE_API_KEY, it uses the valid GEMINI_API_KEY value
if "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


try:
    import google.auth
    google.auth.default()
except Exception:
    from google.auth.credentials import AnonymousCredentials
    google.auth.default = lambda *args, **kwargs: (AnonymousCredentials(), "mock-project")


setup_telemetry()
# Must run before get_fast_api_app to set the tracer provider resource.
try:
    setup_agent_engine_telemetry()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Could not setup Agent Engine telemetry: {e}")

try:
    _, project_id = google.auth.default()
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Could not initialize Cloud Logging (using standard logging): {e}")

allow_origins = (

    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runner for the A2A path, sharing the same session/artifact services as the
    # adk_api and reasoning_engine paths (see services.py). Imported here so the
    # agent is built after env/telemetry setup.
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    # Shared by the A2A path and the reasoning_engine adapter routes.
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=False,
    lifespan=lifespan,
)
app.title = "disaster-response"
app.description = "API for interacting with the Agent disaster-response"


# Proxy routes so the Vertex AI Console Playground (reasoning_engine SDK) can
attach_reasoning_engine_routes(app)


def run_local_mock_pipeline(message: str, session_id: str) -> dict:
    msg_lower = message.lower()
    urgency = "Moderate"
    if any(k in msg_lower for k in ["help", "critical", "immediate", "emergency"]):
        urgency = "Critical" if "immediate" in msg_lower or "critical" in msg_lower else "High"
    elif "tree" in msg_lower:
        urgency = "Moderate"
        
    incident_type = "Other"
    if "fire" in msg_lower:
        incident_type = "Fire"
    elif "flood" in msg_lower or "water" in msg_lower or "rain" in msg_lower:
        incident_type = "Flood"
    elif "medical" in msg_lower or "hurt" in msg_lower or "injury" in msg_lower:
        incident_type = "Medical"
    elif "trapped" in msg_lower:
        incident_type = "Trapped"
    elif "tree" in msg_lower or "road" in msg_lower or "block" in msg_lower:
        incident_type = "Infrastructure"
        
    location_text = "Unknown Location"
    if "san francisco" in msg_lower or "sf" in msg_lower:
        location_text = "San Francisco"
    elif "miami" in msg_lower:
        location_text = "Miami"
    elif "seattle" in msg_lower:
        location_text = "Seattle"
    elif "new york" in msg_lower or "ny" in msg_lower:
        location_text = "New York"
        
    from app.agent import geocode_location
    coords = geocode_location(location_text)
    
    from app.agent import allocate_rescue_unit
    dispatch_plan = allocate_rescue_unit(incident_type, location_text)
    
    from app.agent import load_system_db, save_system_db
    db = load_system_db()
    
    state_dict = {
        "raw_message": message,
        "urgency": urgency,
        "incident_type": incident_type,
        "location_text": location_text,
        "coordinates": coords,
        "dispatch_plan": dispatch_plan,
        "listener_output": {
            "urgency": urgency,
            "incident_type": incident_type,
            "location_text": location_text
        },
        "coordinates_output": coords,
        "dispatcher_output": {
            "dispatch_plan": dispatch_plan
        }
    }
    
    db["incidents"].append({
        "id": session_id,
        "raw_message": message,
        "urgency": urgency,
        "incident_type": incident_type,
        "location_text": location_text,
        "coordinates": coords,
        "dispatch_plan": dispatch_plan,
    })
    save_system_db(db)
    
    return state_dict


@app.post("/api/run_pipeline")
async def run_pipeline(request: Request) -> dict:
    body = await request.json()
    message = body.get("message", "")
    use_mock = body.get("use_mock", False)
    
    import uuid
    user_id = "streamlit_user"
    session_id = f"s-{uuid.uuid4()}"
    
    if use_mock:
        return run_local_mock_pipeline(message, session_id)
        
    from google.genai import types
    content = types.Content(role="user", parts=[types.Part(text=message)])
    
    runner = app.state.runner
    events = runner.run_async(
        new_message=content,
        user_id=user_id,
        session_id=session_id
    )
    async for _ in events:
        pass
        
    session = await runner.session_service.get_session(
        app_name=app.state.agent_app_name,
        user_id=user_id,
        session_id=session_id
    )
    
    state_dict = session.state if session else {}
    if state_dict:
        from app.agent import load_system_db, save_system_db
        db = load_system_db()
        db["incidents"].append({
            "id": session_id,
            "raw_message": state_dict.get("raw_message", ""),
            "urgency": state_dict.get("urgency", "Moderate"),
            "incident_type": state_dict.get("incident_type", "General"),
            "location_text": state_dict.get("location_text", "Unknown"),
            "coordinates": state_dict.get("coordinates", {}),
            "dispatch_plan": state_dict.get("dispatch_plan", ""),
        })
        save_system_db(db)
        
    return state_dict


@app.get("/api/system_state")
def get_system_state() -> dict:
    from app.agent import load_system_db
    return load_system_db()


@app.post("/api/reset_system")
def reset_system() -> dict:
    from app.agent import save_system_db, DEFAULT_UNITS
    data = {
        "units": [dict(u) for u in DEFAULT_UNITS],
        "incidents": []
    }
    save_system_db(data)
    return {"status": "success", "message": "System database reset successfully."}




@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
