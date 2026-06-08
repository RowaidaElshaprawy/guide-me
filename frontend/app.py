# frontend/app.py
import streamlit as st
import requests
import uuid
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.config import settings
from frontend.components.property_card import render_property_card

# Configure viewport layout first
st.set_page_config(
    page_title=settings.app_name,
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Elite SaaS Cyberpunk CSS Customizations ──
st.markdown("""
<style>
    /* Main background canvas */
    .stApp { 
        background-color: #0d0d1a; 
    }
    
    /* Center and scale the main brand block */
    .brand-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 1rem 0 0.5rem 0;
        text-align: center;
    }

    /* Custom centering block specifically for our massive logo asset */
    .logo-centered-wrapper {
        display: flex;
        justify-content: center;
        align-items: center;
        width: 100%;
        margin: 0 auto;
        padding: 1rem 0;
    }

    /* Polishing the conversational chat block components */
    .stChatMessage { 
        background-color: #161630 !important; 
        border: 1px solid #252545 !important;
        border-radius: 14px !important; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        margin-bottom: 1rem !important;
    }
    
    /* Input layout customization */
    .stChatInput input { 
        background-color: #161630 !important; 
        color: #f5f5ff !important; 
        border: 1px solid #32325d !important;
        border-radius: 10px !important;
    }
    
    .stChatInput input:focus {
        border-color: #f39c12 !important;
    }
    
    h1, h2, h3 { color: #f5f5ff !important; font-family: 'Inter', sans-serif; }
    p { color: #b0b0d0; }
    .stSpinner { color: #f39c12; }
    
    /* Sidebar aesthetic */
    section[data-testid="stSidebar"] { 
        background-color: #090914; 
        border-right: 1px solid #1c1c3a;
    }
</style>
""", unsafe_allow_html=True)

# ── Session State Configuration ──
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "properties" not in st.session_state:
    st.session_state.properties = []

# ── Sidebar Configurations ──
with st.sidebar:
    st.markdown("<div style='padding-top: 1.5rem;'></div>", unsafe_allow_html=True)
    st.markdown("### 🗺️ System Controls")
    st.markdown("---")
    st.markdown("**Try asking:**")
    st.markdown("- *Find me a luxury hotel in Cairo*")
    st.markdown("- *Cheap apartments in Luxor under $60*")
    st.markdown("- *Beach villa in Hurghada with a pool*")
    st.markdown("- *How far is Siwa from Cairo?*")
    st.markdown("- *Show me current prices for chalets in Siwa*")
    st.markdown("---")

    # Fixed syntax warning by replacing use_container_width with width='stretch'
    if st.button("🗑️ Clear Chat Session", width="stretch"):
        st.session_state.messages = []
        st.session_state.properties = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# ── Massive Display Logo Placement ──
logo_path = "resources/logo.png"

if os.path.exists(logo_path):
    # Using a wide middle column layout [3, 6, 3] so the logo expands across the layout cleanly
    left_spacer, center_canvas, right_spacer = st.columns([3, 6, 3])
    with center_canvas:
        # Fixed syntax warning by replacing use_container_width with width='stretch'
        st.image(logo_path, width="stretch")
else:
    # If the logo isn't found, fall back cleanly to centered hero typography text
    left_spacer, center_canvas, right_spacer = st.columns([2, 8, 2])
    with center_canvas:
        st.markdown("<h1 style='text-align: center;'>✈️ Travel Agent Discovery</h1>", unsafe_allow_html=True)

st.markdown("""
<div class="brand-container">
    <div class="brand-tagline">Multi-Agent Hybrid RAG Architecture • Production Layer v2.5</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='margin-bottom: 2rem;'></div>", unsafe_allow_html=True)

# ── Chat History Viewport ──
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ── Evaluated Property Generation Cards ──
if st.session_state.properties:
    st.markdown("---")
    st.markdown("### 🏨 Recommended Matches")

    passed = [p for p in st.session_state.properties if p.get("passed_review", True)]
    failed = [p for p in st.session_state.properties if not p.get("passed_review", True)]

    if passed:
        for prop in passed:
            render_property_card(prop)

    if failed:
        with st.expander(f"⚠️ {len(failed)} properties flagged during rule-matching logic constraints"):
            for prop in failed:
                render_property_card(prop)

# ── Operational Chat Ingestion Pipeline ──
if prompt := st.chat_input("Where do you want to explore? (e.g., Show me current prices for chalets in Siwa)"):

    # Store user action
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Ingest through our FastAPI backend router orchestrator
    with st.chat_message("assistant"):
        with st.spinner("Executing Pipeline Stages..."):
            try:
                response = requests.post(
                    f"{settings.api_base_url}/api/chat",
                    json={
                        "session_id": st.session_state.session_id,
                        "user_message": prompt,
                        "conversation_history": st.session_state.messages,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()

                reply = data.get("assistant_message", "No structural response payload parsed.")
                st.markdown(reply)

                # Cache target records
                st.session_state.properties = data.get("properties", [])

                if settings.debug:
                    stage = data.get("pipeline_stage_reached", "unknown")
                    st.caption(f"Pipeline Trace Target: `{stage}`")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": reply,
                })

                if st.session_state.properties:
                    st.rerun()

            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot reach the backend. Verify that your Uvicorn service is actively listening.")
            except requests.exceptions.Timeout:
                st.error("⏱️ Pipeline execution timed out during real-time scrap hydration cycles.")
            except requests.exceptions.HTTPError as e:
                st.error(f"❌ Structural Gateway Error [{e.response.status_code}]: {e.response.text}")
            except Exception as e:
                st.error(f"❌ Pipeline parsing failure: {str(e)}")