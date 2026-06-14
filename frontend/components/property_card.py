from html import escape
from urllib.parse import quote_plus

import streamlit as st


def render_property_card(prop: dict) -> None:
    passed = prop.get("passed_review", True)
    scrape_status = prop.get("scrape_status", "skipped")
    border_color = "#2ecc71" if passed else "#e74c3c"
    status_icon = "✅" if passed else "❌"

    is_available = prop.get("is_available")
    if is_available is True:
        avail_badge = "🟢 Available"
    elif is_available is False:
        avail_badge = "🔴 Unavailable"
    else:
        avail_badge = "🟡 Check site"

    nightly = prop.get("nightly_price_usd")
    price_display = f"${nightly:.0f}/night" if nightly else "Price on request"

    if scrape_status == "success":
        price_badge = "<span style='color:#2ecc71;font-size:0.75rem;'>● Live price</span>"
    elif scrape_status in ("structure_changed", "failed"):
        price_badge = "<span style='color:#f39c12;font-size:0.75rem;'>● Estimated price</span>"
    else:
        price_badge = "<span style='color:#888;font-size:0.75rem;'>● Database price</span>"

    stars = prop.get("star_rating")
    star_display = "⭐" * int(stars) if stars else "Not rated"

    amenities = prop.get("amenities", [])
    amenity_tags = " ".join([f"`{escape(str(a))}`" for a in amenities[:6]])

    distance_info = prop.get("distance_info")
    distance_html = ""
    if distance_info:
        if isinstance(distance_info, dict):
            km = distance_info.get("distance_km", "")
            origin = distance_info.get("origin", "")
            mins = distance_info.get("duration_minutes", "")
        else:
            km = getattr(distance_info, "distance_km", "")
            origin = getattr(distance_info, "origin", "")
            mins = getattr(distance_info, "duration_minutes", "")
        if km:
            distance_html = (
                "<p style='color:#5dade2;font-size:0.9rem;margin:6px 0;'>"
                f"📍 <b>{escape(str(km))} km</b> from {escape(str(origin))} "
                f"({float(mins):.0f} min drive)</p>"
            )

    city = escape(str(prop.get("city", "")))
    country = escape(str(prop.get("country", "")))
    name = escape(str(prop.get("name", "")))
    property_type = escape(str(prop.get("property_type", "")).title())
    reviewer_notes = escape(str(prop.get("reviewer_notes", "")))
    reviewer_note_html = ""
    if reviewer_notes and not passed:
        reviewer_note_html = (
            '<p style="color:#777;font-size:0.82rem;margin:10px 0 4px 0;'
            f'font-style:italic;">{reviewer_notes}</p>'
        )

    st.markdown(
        f"""
<div style="
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 18px 22px;
    margin-bottom: 18px;
    background: #161630;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;">
        <h3 style="color:#f5f5ff;margin:0;font-size:1.1rem;">
            {status_icon} {name}
        </h3>
        <div style="text-align:right;min-width:120px;">
            <div style="color:#f39c12;font-size:1.15rem;font-weight:bold;">{price_display}</div>
            {price_badge}
        </div>
    </div>
    <p style="color:#a0a0c0;margin:6px 0 10px 0;font-size:0.9rem;">
        📍 {city}, {country} &nbsp;|&nbsp;
        🏠 {property_type} &nbsp;|&nbsp;
        {star_display} &nbsp;|&nbsp;
        {avail_badge}
    </p>
    <p style="color:#c0c0d8;margin:4px 0;">{amenity_tags}</p>
    {distance_html}
    {reviewer_note_html}
</div>
""",
        unsafe_allow_html=True,
    )

    booking_url = prop.get("booking_url")
    source_url = prop.get("source_url", "")

    def is_valid_url(url: str) -> bool:
        return bool(url) and url.startswith("http") and "example.com" not in url

    col1, col2 = st.columns([1, 1])

    with col1:
        if booking_url and is_valid_url(booking_url):
            st.link_button("🎯 Book Now (Pre-filled)", booking_url)
        elif source_url and is_valid_url(source_url):
            st.link_button("View Property →", source_url)
        else:
            fallback = _booking_search_url(prop)
            st.link_button("Search on Booking.com →", fallback)

    with col2:
        st.link_button("🔍 Search on Booking", _booking_search_url(prop))


def _booking_search_url(prop: dict) -> str:
    city = prop.get("city", "Egypt")
    name = prop.get("name", "")
    query = quote_plus(f"{name} {city} Egypt")
    return f"https://www.booking.com/searchresults.html?ss={query}"
