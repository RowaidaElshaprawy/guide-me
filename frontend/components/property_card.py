import streamlit as st


def render_property_card(prop: dict) -> None:
    """
    Renders a single verified property as a styled card in Streamlit.
    Receives a dict (parsed from ChatResponse JSON).
    """
    passed = prop.get("passed_review", True)
    border_color = "#2ecc71" if passed else "#e74c3c"
    status_icon = "✅" if passed else "❌"

    # Availability badge
    is_available = prop.get("is_available")
    if is_available is True:
        avail_badge = "🟢 Available"
    elif is_available is False:
        avail_badge = "🔴 Unavailable"
    else:
        avail_badge = "🟡 Check site"

    # Price display
    nightly = prop.get("nightly_price_usd")
    price_display = f"${nightly:.0f}/night" if nightly else "Price on request"

    # Star rating
    stars = prop.get("star_rating")
    star_display = "⭐" * int(stars) if stars else "Not rated"

    # Amenities
    amenities = prop.get("amenities", [])
    amenity_tags = " ".join([f"`{a}`" for a in amenities[:6]])

    # Distance info
    distance_info = prop.get("distance_info")
    distance_display = ""
    if distance_info:
        distance_display = (
            f"📍 **{distance_info['distance_km']} km** from {distance_info['origin']} "
            f"({distance_info['duration_minutes']:.0f} min drive)"
        )

    st.markdown(f"""
<div style="
    border: 1px solid {border_color};
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 16px;
    background: #1a1a2e;
">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <h3 style="color: #f0f0f0; margin: 0;">{status_icon} {prop['name']}</h3>
        <span style="color: #f39c12; font-size: 1.2rem; font-weight: bold;">{price_display}</span>
    </div>
    <p style="color: #a0a0b0; margin: 4px 0 8px 0;">
        📍 {prop['city']}, {prop['country']} &nbsp;|&nbsp;
        🏠 {prop['property_type'].title()} &nbsp;|&nbsp;
        {star_display} &nbsp;|&nbsp;
        {avail_badge}
    </p>
    <p style="color: #c0c0d0; margin: 4px 0;">{amenity_tags}</p>
    <p style="color: #888; font-size: 0.85rem; margin: 8px 0 4px 0;
        font-style: italic;">{prop.get('reviewer_notes', '')}</p>
    {"<p style='color: #5dade2; font-size: 0.9rem;'>" + distance_display + "</p>" if distance_display else ""}
</div>
""", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 4])
    with col1:
        st.link_button("View & Book →", prop.get("source_url", "#"))