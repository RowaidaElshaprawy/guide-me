import streamlit as st
import requests
import uuid
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.config import settings
from frontend.components.property_card import render_property_card

st.set_page_config(
    page_title=settings.app_name,
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ──
st.markdown("""
<style>
    .stApp { background-color: #0d0d1a; }
    .stChatMessage { background-color: #1a1a2e !important; border-radius: 12px; }
    .stChatInput input { background-color: #1a1a2e !important; color: #f0f0f0 !important; }
    h1, h2, h3 { color: #f0f0f0 !important; }
    p { color: #c0c0d0; }
    .stSpinner { color: #f39c12; }
    section[data-testid="stSidebar"] { background-color: #12122a; }
</style>
""", unsafe_allow_html=True)

# ── Session State ──
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "properties" not in st.session_state:
    st.session_state.properties = []

# ── Sidebar ──
with st.sidebar:
    st.markdown("### 🗺️ Travel Agent")
    st.markdown("---")
    st.markdown("**Try asking:**")
    st.markdown("- *Find me a luxury hotel in Cairo*")
    st.markdown("- *Cheap apartments in Luxor under $60*")
    st.markdown("- *Beach villa in Hurghada with a pool*")
    st.markdown("- *How far is Siwa from Cairo?*")
    st.markdown("- *Show me current prices for chalets in Siwa*")
    st.markdown("---")

    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.session_state.properties = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# ── Header ──
st.title("✈️ Travel Agent")
st.caption("AI-powered travel discovery · Powered by local AI + Gemini Flash")

# ── Chat History ──
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ── Property Cards (shown after last assistant response) ──
if st.session_state.properties:
    st.markdown("---")
    st.markdown("### 🏨 Recommended Properties")

    passed = [p for p in st.session_state.properties if p.get("passed_review", True)]
    failed = [p for p in st.session_state.properties if not p.get("passed_review", True)]

    if passed:
        for prop in passed:
            render_property_card(prop)

    if failed:
        with st.expander(f"⚠️ {len(failed)} properties didn't meet your criteria"):
            for prop in failed:
                render_property_card(prop)

# ── Chat Input ──
if prompt := st.chat_input("Where do you want to go?"):

    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call backend
    with st.chat_message("assistant"):
        with st.spinner("Searching..."):
            try:
                response = requests.post(
                    f"{settings.api_base_url}/api/chat",
                    json={
                        "session_id": st.session_state.session_id,
                        "user_message": prompt,
                        "conversation_history": st.session_state.messages,
                    },
                    timeout=120,  # Scrapling can take up to 60s per property
                )
                response.raise_for_status()
                data = response.json()

                reply = data.get("assistant_message", "No response received.")
                st.markdown(reply)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": reply,
                })

                # Store properties for card rendering
                st.session_state.properties = data.get("properties", [])

                # Show pipeline stage in debug mode
                if settings.debug:
                    stage = data.get("pipeline_stage_reached", "unknown")
                    st.caption(f"Pipeline stage: `{stage}`")

                if st.session_state.properties:
                    st.rerun()

            except requests.exceptions.ConnectionError:
                msg = "❌ Cannot reach the backend. Is FastAPI running? Run: `uv run uvicorn backend.main:app --reload`"
                st.error(msg)
            except requests.exceptions.Timeout:
                msg = "⏱️ Request timed out. Live scraping can be slow — try again or ask without requesting current prices."
                st.error(msg)
            except requests.exceptions.HTTPError as e:
                st.error(f"❌ Backend error {e.response.status_code}: {e.response.text}")
            except Exception as e:
                st.error(f"❌ Unexpected error: {str(e)}")