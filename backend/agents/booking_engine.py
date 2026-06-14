# backend/agents/booking_engine.py

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.core.schemas import BookingIntent, LivePriceData, PropertyRecord, ScrapeStatus


ORDINAL_SELECTIONS = {
    "first": 0,
    "1st": 0,
    "one": 0,
    "second": 1,
    "2nd": 1,
    "two": 1,
    "third": 2,
    "3rd": 2,
    "three": 2,
    "fourth": 3,
    "4th": 3,
    "four": 3,
    "fifth": 4,
    "5th": 4,
    "five": 4,
}

MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def generate_booking_deeplink(
    property_record: PropertyRecord,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int = 2,
    rooms: int = 1,
) -> str:
    check_in, check_out = default_booking_dates(check_in, check_out)
    source_url = property_record.source_url
    parsed = urlparse(source_url)
    domain = parsed.netloc.lower()

    if "booking.com" in domain:
        params = {
            "checkin": check_in,
            "checkout": check_out,
            "group_adults": guests,
            "no_rooms": rooms,
            "selected_currency": "USD",
        }
        search_params = {
            "ss": f"{property_record.name}, {property_record.city}, Egypt",
            **params,
        }
        return f"https://www.booking.com/searchresults.html?{urlencode(search_params)}"

    if "airbnb.com" in domain:
        params = {
            "check_in": check_in,
            "check_out": check_out,
            "adults": guests,
        }
        return _merge_query_params(source_url, params)

    params = {
        "checkin": check_in,
        "checkout": check_out,
        "guests": guests,
    }
    return _merge_query_params(source_url, params)


def default_booking_dates(
    check_in: str | None = None,
    check_out: str | None = None,
) -> tuple[str, str]:
    if not check_in:
        check_in = (date.today() + timedelta(days=1)).isoformat()
    if not check_out:
        check_out = (date.fromisoformat(check_in) + timedelta(days=1)).isoformat()
    if date.fromisoformat(check_out) <= date.fromisoformat(check_in):
        check_out = (date.fromisoformat(check_in) + timedelta(days=1)).isoformat()
    return check_in, check_out


def extract_booking_details_from_conversation(
    user_message: str,
    conversation_history: list[dict],
) -> dict:
    combined_text = " ".join(
        [m.get("content", "") for m in conversation_history[-8:]] + [user_message]
    )
    dates_found = _extract_dates(combined_text)

    guest_match = re.search(
        r"\b(\d+)\s*(?:guests?|people|adults?|persons?)\b",
        combined_text,
        re.IGNORECASE,
    )
    room_match = re.search(r"\b(\d+)\s*(?:rooms?)\b", combined_text, re.IGNORECASE)

    return {
        "check_in": dates_found[0] if len(dates_found) > 0 else None,
        "check_out": dates_found[1] if len(dates_found) > 1 else None,
        "guests": int(guest_match.group(1)) if guest_match else 2,
        "rooms": int(room_match.group(1)) if room_match else 1,
        "guest_name": _extract_guest_name(combined_text),
        "selected_property_index": _extract_selected_property_index(combined_text),
        "selected_property_name": _extract_selected_property_name(user_message),
    }


def select_property_for_booking(
    records: list[PropertyRecord],
    booking_details: dict,
) -> PropertyRecord | None:
    if not records:
        return None

    selected_index = booking_details.get("selected_property_index")
    if selected_index is not None and 0 <= selected_index < len(records):
        return records[selected_index]

    selected_name = (booking_details.get("selected_property_name") or "").lower().strip()
    if selected_name:
        exact_match = next((p for p in records if p.name.lower() == selected_name), None)
        if exact_match:
            return exact_match
        partial_match = next((p for p in records if selected_name in p.name.lower()), None)
        if partial_match:
            return partial_match

    return records[0]


def build_booking_intent(
    property_record: PropertyRecord,
    check_in: str | None,
    check_out: str | None,
    guests: int,
    rooms: int = 1,
    guest_name: str | None = None,
    live_price: LivePriceData | None = None,
) -> BookingIntent:
    check_in, check_out = default_booking_dates(check_in, check_out)
    booking_url = generate_booking_deeplink(
        property_record=property_record,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        rooms=rooms,
    )

    nightly_price = property_record.avg_price_usd
    total_price = None
    is_available = None
    scrape_status = ScrapeStatus.SKIPPED
    price_source = "database"

    if live_price:
        scrape_status = live_price.scrape_status
        is_available = live_price.is_available
        if live_price.scrape_status == ScrapeStatus.SUCCESS and live_price.nightly_price_usd:
            nightly_price = live_price.nightly_price_usd
            total_price = live_price.total_price_usd
            price_source = "live"
        elif live_price.scrape_status in (ScrapeStatus.FAILED, ScrapeStatus.STRUCTURE_CHANGED):
            price_source = "database_fallback"

    return BookingIntent(
        property_id=property_record.property_id,
        property_name=property_record.name,
        source_url=property_record.source_url,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        rooms=rooms,
        guest_name=guest_name,
        booking_url=booking_url,
        nightly_price_usd=nightly_price,
        total_price_usd=total_price,
        is_available=is_available,
        scrape_status=scrape_status,
        price_source=price_source,
        status_message=_booking_status_message(price_source, is_available),
    )


def _booking_status_message(price_source: str, is_available: bool | None) -> str:
    if is_available is False:
        return "The booking site currently reports this property as unavailable."
    if price_source == "live":
        return "Live price check succeeded; the deeplink is pre-filled for final confirmation."
    if price_source == "database_fallback":
        return (
            "Live scraping was blocked or changed; using the ChromaDB baseline price "
            "with a pre-filled deeplink."
        )
    return "Using the ChromaDB baseline price with a pre-filled deeplink."


def _merge_query_params(url: str, params: dict) -> str:
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update({key: str(value) for key, value in params.items() if value is not None})
    return urlunparse(parsed._replace(query=urlencode(existing)))


def _extract_dates(text: str) -> list[str]:
    dates = []

    for match in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", text):
        dates.append(match.group(1))

    for match in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text):
        month, day, year = [int(part) for part in match.groups()]
        if year < 100:
            year += 2000
        dates.append(date(year, month, day).isoformat())

    month_pattern = "|".join(MONTHS)
    for match in re.finditer(
        rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b",
        text,
        re.IGNORECASE,
    ):
        month_name, day_text, year_text = match.groups()
        parsed = _future_date(
            month=MONTHS[month_name.lower()],
            day=int(day_text),
            year=int(year_text) if year_text else None,
        )
        dates.append(parsed.isoformat())

    unique_dates = []
    for value in dates:
        if value not in unique_dates:
            unique_dates.append(value)
    return unique_dates


def _future_date(month: int, day: int, year: int | None) -> date:
    today = date.today()
    candidate = date(year or today.year, month, day)
    if year is None and candidate < today:
        candidate = date(today.year + 1, month, day)
    return candidate


def _extract_guest_name(text: str) -> str | None:
    match = re.search(
        r"\b(?:my name is|name is|guest name is|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
        text,
    )
    return match.group(1).strip() if match else None


def _extract_selected_property_index(text: str) -> int | None:
    lowered = text.lower()
    for token, index in ORDINAL_SELECTIONS.items():
        pattern = (
            rf"\b(?:book|reserve|choose|select|want|take|get)?\s*"
            rf"(?:the\s+)?{token}\s+"
            r"(?:one|property|hotel|listing|option)?\b"
        )
        if re.search(pattern, lowered):
            return index

    number_match = re.search(r"\b(?:property|option|listing|hotel)\s*#?\s*(\d+)\b", lowered)
    if number_match:
        return max(int(number_match.group(1)) - 1, 0)

    hash_match = re.search(r"#\s*(\d+)\b", lowered)
    if hash_match:
        return max(int(hash_match.group(1)) - 1, 0)

    return None


def _extract_selected_property_name(user_message: str) -> str | None:
    match = re.search(
        r"\b(?:book|reserve|choose|select)\s+(.+?)(?:\s+(?:from|for|check-in|checkin|on)\b|$)",
        user_message,
        re.IGNORECASE,
    )
    if not match:
        return None

    candidate = match.group(1).strip(" .,")
    ordinal_targets = {
        "it",
        "this",
        "this one",
        "the first one",
        "first one",
        "the second one",
        "second one",
        "the third one",
        "third one",
    }
    if candidate.lower() in ordinal_targets:
        return None
    return candidate
