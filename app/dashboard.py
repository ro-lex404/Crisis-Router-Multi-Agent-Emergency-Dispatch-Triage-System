import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Crisis-Router Dashboard", layout="wide")
st.title("🚨 Crisis-Router: Emergency Multi-Agent Dispatch")

# Sidebar navigation
st.sidebar.title("Operational Control")
role = st.sidebar.radio(
    "Switch System Console View:",
    ["Civilian Distress Console", "Dispatcher Ops Center"],
    help="Select the access role for the disaster response system."
)

st.sidebar.write("---")
use_mock_mode = st.sidebar.checkbox(
    "Use Offline Simulator",
    value=True,
    help="When enabled, bypasses the Gemini API rate limits and runs a rule-based mock model for visualization."
)

BACKEND_URL = "http://localhost:8000"

# Helper to fetch system state from backend
def get_system_state():
    try:
        response = requests.get(f"{BACKEND_URL}/api/system_state")
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {"units": [], "incidents": []}

# Helper to reset system
def reset_system():
    try:
        requests.post(f"{BACKEND_URL}/api/reset_system")
        st.session_state.active_incident = None
    except Exception:
        pass

# Initialize session state for active incident (last run)
if "active_incident" not in st.session_state:
    st.session_state.active_incident = None

if role == "Civilian Distress Console":
    st.subheader("Report an Emergency / Ingest Distress Signal")
    st.info("Your distress signal will be parsed instantly by our AI models and routed to the nearest emergency responder team.")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        presets = [
            "HELP! There is a high urgency fire at a house in San Francisco! Please send help!",
            "Flooding is getting worse near Miami downtown, need immediate boat rescue for 3 people.",
            "Tree fell down blocking the road in Seattle, utility grid is sparking."
        ]
        selected_preset = st.selectbox("Choose a sample emergency preset:", presets)
        raw_message = st.text_area("Or type a custom emergency distress message:", value=selected_preset)
        
        run_btn = st.button("Submit Emergency Signal", type="primary")
        
        if run_btn:
            with st.spinner("Processing emergency dispatch..."):
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/api/run_pipeline",
                        json={
                            "message": raw_message,
                            "use_mock": use_mock_mode
                        }
                    )
                    if response.status_code == 200:
                        st.session_state.active_incident = response.json()
                    else:
                        st.error(f"Backend returned an error: {response.status_code}")
                except Exception as e:
                    st.error(f"Could not connect to FastAPI backend: {e}")
                    
    with col2:
        if st.session_state.active_incident:
            data = st.session_state.active_incident
            urgency = data.get("urgency", "Moderate")
            incident_type = data.get("incident_type", "General")
            dispatch_plan = data.get("dispatch_plan", "")
            
            st.success("### ✅ Emergency Signal Ingested")
            
            # Simple civilian-friendly dispatch layout
            st.markdown(f"**Urgency Level:** {urgency}")
            st.markdown(f"**Emergency Type:** {incident_type}")
            
            st.info(f"👉 **First Responder Status:** {dispatch_plan if dispatch_plan else 'Unit Dispatching...'}")
            st.markdown("⚠️ **Please stay safe and remain calm. First responders have been notified.**")
        else:
            st.write("No submitted signals in this session yet.")

else:  # Dispatcher Ops Center
    # Fetch latest data from the backend registry database
    system_data = get_system_state()
    incidents = system_data.get("incidents", [])
    units = system_data.get("units", [])
    
    col1, col2 = st.columns([1.2, 1])
    
    with col1:
        st.subheader("🛠️ Operations Management")
        
        # Actions row
        if st.button("Reset System & Release All Units", type="secondary"):
            reset_system()
            st.rerun()
            
        st.write("---")
        
        # Rescue Units statuses
        st.subheader("🚒 Rescue Unit Status Registry")
        if units:
            # Render nice table for units
            import pandas as pd
            df_units = pd.DataFrame(units)
            # Reorder columns for readability
            df_units = df_units[["name", "type", "status", "dispatched_to"]]
            df_units.columns = ["Unit Name", "Unit Type", "Status", "Deployment Location"]
            st.dataframe(df_units, use_container_width=True, hide_index=True)
        else:
            st.warning("No units loaded. Check backend connection.")
            
        st.write("---")
        
        # Active Incidents log
        st.subheader("📋 Log of Distress Ingestions")
        if incidents:
            import pandas as pd
            df_incidents = pd.DataFrame(incidents)
            df_incidents = df_incidents[["urgency", "incident_type", "location_text", "dispatch_plan"]]
            df_incidents.columns = ["Urgency", "Incident Type", "Location", "Dispatch Action"]
            st.dataframe(df_incidents, use_container_width=True, hide_index=True)
        else:
            st.info("No active incidents logged in the system.")
            
    with col2:
        st.subheader("🗺️ Live Operational Map")
        
        default_location = [37.7749, -122.4194] # SF Default
        m = folium.Map(location=default_location, zoom_start=4)
        
        # Plot all logged incidents
        for inc in incidents:
            coords = inc.get("coordinates", {})
            if coords.get("lat") and coords.get("lon"):
                urgency = inc.get("urgency", "Moderate")
                inc_type = inc.get("incident_type", "General")
                dispatch = inc.get("dispatch_plan", "")
                
                color = "red" if urgency in ["High", "Critical"] else "orange"
                folium.Marker(
                    location=[coords["lat"], coords["lon"]],
                    popup=f"<b>{inc_type}</b><br>{dispatch}",
                    icon=folium.Icon(color=color, icon="info-sign")
                ).add_to(m)
                
        # Center map around the latest incident if available
        if incidents:
            latest = incidents[-1]
            coords = latest.get("coordinates", {})
            if coords.get("lat") and coords.get("lon"):
                m.location = [coords["lat"], coords["lon"]]
                m.zoom_start = 10
                
        st_folium(m, width=650, height=500)