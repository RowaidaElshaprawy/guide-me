# frontend/app.py
import os
import sys
import uuid

import requests
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.config import settings
from frontend.components.property_card import render_property_card

st.set_page_config(
    page_title=settings.app_name,
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    .stApp { background-color: #0d0d1a; }
    .brand-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 1rem 0 0.5rem 0;
        text-align: center;
    }
    .stChatMessage {
        background-color: #161630 !important;
        border: 1px solid #252545 !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        margin-bottom: 1rem !important;
    }
    .stChatInput input {
        background-color: #161630 !important;
        color: #f5f5ff !important;
        border: 1px solid #32325d !important;
        border-radius: 8px !important;
    }
    .stChatInput input:focus { border-color: #f39c12 !important; }
    h1, h2, h3 { color: #f5f5ff !important; font-family: 'Inter', sans-serif; }
    p { color: #b0b0d0; }
    .stSpinner { color: #f39c12; }
    section[data-testid="stSidebar"] {
        background-color: #090914;
        border-right: 1px solid #1c1c3a;
    }
</style>
""",
    unsafe_allow_html=True,
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "properties" not in st.session_state:
    st.session_state.properties = []
if "booking_intent" not in st.session_state:
    st.session_state.booking_intent = None

with st.sidebar:
    st.markdown("<div style='padding-top: 1.5rem;'></div>", unsafe_allow_html=True)
    st.markdown("### 🗺️ System Controls")
    st.markdown("---")
    st.markdown("**Try asking:**")
    st.markdown("- *Find me a hotel in Cairo*")
    st.markdown("- *Cheap apartments in Luxor under $70*")
    st.markdown("- *Beach villa in Hurghada with pool*")
    st.markdown("- *Show chalets in Siwa*")
    st.markdown("- *How far is Siwa from Cairo?*")
    st.markdown("- *Show current prices for hotels in Sharm*")
    st.markdown("- *I want to book the first one, check-in July 10 check-out July 15 for 2 guests*")
    st.markdown("---")

    if st.button("🗑️ Clear Chat Session", width="stretch"):
        st.session_state.messages = []
        st.session_state.properties = []
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.booking_intent = None
        st.rerun()

logo_path = "resources/logo.png"
if os.path.exists(logo_path):
    _, center_canvas, _ = st.columns([3, 6, 3])
    with center_canvas:
        st.image(logo_path, width="stretch")
else:
    _, center_canvas, _ = st.columns([2, 8, 2])
    with center_canvas:
        st.markdown("<h1 style='text-align: center;'>✈️ Guide Me</h1>", unsafe_allow_html=True)

st.markdown(
    """
<div class="brand-container">
    <div class="brand-tagline" style="color:#a0a0c0;font-size:0.9rem;">
        Multi-Agent Hybrid RAG • Egypt Travel Discovery • Production v3.0
    </div>
</div>
""",
    unsafe_allow_html=True,
)
st.markdown("<div style='margin-bottom: 2rem;'></div>", unsafe_allow_html=True)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if st.session_state.properties:
    st.markdown("---")
    st.markdown("### 🏨 Recommended Matches")

    passed = [p for p in st.session_state.properties if p.get("passed_review", True)]
    failed = [p for p in st.session_state.properties if not p.get("passed_review", True)]

    if passed:
        for prop in passed:
            render_property_card(prop)

    if failed:
        with st.expander(f"⚠️ {len(failed)} properties flagged during validation"):
            for prop in failed:
                render_property_card(prop)

if st.session_state.booking_intent:
    bi = st.session_state.booking_intent
    st.markdown("---")
    st.markdown("### 🎯 Booking Assistant")
    price = bi.get("nightly_price_usd")
    price_label = f"${price:.0f}/night" if price else "Price on request"
    price_source = str(bi.get("price_source", "database")).replace("_", " ").title()
    guest_name = bi.get("guest_name") or "Guest"
    st.success(
        f"**{bi.get('property_name', 'Property')}** - "
        f"Check-in: {bi.get('check_in', 'TBD')} → "
        f"Check-out: {bi.get('check_out', 'TBD')} - "
        f"{bi.get('guests', 2)} guests - "
        f"{bi.get('rooms', 1)} room"
    )
    st.caption(
        f"Traveler: {guest_name} · {price_label} · {price_source} · "
        f"{bi.get('status_message', '')}"
    )
    if bi.get("booking_url"):
        st.link_button("🎯 Complete Booking Now →", bi["booking_url"])

if prompt := st.chat_input("Where do you want to explore? (e.g., Show me hotels in Cairo)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Executing pipeline stages..."):
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

                reply = data.get("assistant_message", "No response received.")
                st.markdown(reply)

                st.session_state.properties = data.get("properties", [])
                st.session_state.booking_intent = data.get("booking_intent")

                if settings.debug:
                    stage = data.get("pipeline_stage_reached", "unknown")
                    st.caption(f"Pipeline stage: `{stage}`")

                st.session_state.messages.append({"role": "assistant", "content": reply})

                if st.session_state.properties or st.session_state.booking_intent:
                    st.rerun()

            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot reach backend. Is FastAPI running on port 8000?")
            except requests.exceptions.Timeout:
                st.error(
                    "⏱️ Request timed out. Live scraping can be slow; "
                    "try without asking for current prices."
                )
            except requests.exceptions.HTTPError as exc:
                st.error(f"❌ Backend error {exc.response.status_code}: {exc.response.text}")
            except Exception as exc:
                st.error(f"❌ Error: {str(exc)}")
