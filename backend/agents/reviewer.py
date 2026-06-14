# backend/agents/reviewer.py

import logging
import re
from urllib.parse import quote_plus, urlparse

from backend.core.schemas import (
    DistanceResult,
    LivePriceData,
    PropertyRecord,
    ScrapeStatus,
    VerifiedProperty,
)

logger = logging.getLogger(__name__)

EXACT_PROPERTY_URLS = {
    "prop_005": "https://www.booking.com/hotel/eg/luxor-guest-house.en-gb.html",
}

CITY_ALIASES = {
    "cairo": "cairo",
    "giza": "cairo",
    "pyramid": "cairo",
    "pyramids": "cairo",
    "great pyramid": "cairo",
    "great pyramids": "cairo",
    "sphinx": "cairo",
    "luxor": "luxor",
    "hurghada": "hurghada",
    "sharm el sheikh": "sharm el sheikh",
    "sharm": "sharm el sheikh",
    "siwa": "siwa",
    "dahab": "dahab",
}

PROPERTY_TYPE_ALIASES = {
    "hotel": "hotel",
    "hotels": "hotel",
    "resort": "hotel",
    "resorts": "hotel",
    "guesthouse": "hotel",
    "guesthouses": "hotel",
    "apartment": "apartment",
    "apartments": "apartment",
    "flat": "apartment",
    "flats": "apartment",
    "chalet": "chalet",
    "chalets": "chalet",
    "villa": "villa",
    "villas": "villa",
}


class ReviewerAgent:
    async def review(
        self,
        properties: list[PropertyRecord],
        live_prices: dict[str, LivePriceData],
        user_message: str,
        max_budget_usd: float | None = None,
        distance_info: DistanceResult | None = None,
    ) -> tuple[list[VerifiedProperty], str]:
        if not properties:
            return [], (
                "I couldn't find any properties matching your request. "
                "We have listings in Cairo, Luxor, Hurghada, Sharm El Sheikh, Siwa, and Dahab. "
                "Try searching by city name."
            )

        try:
            verified = []
            request_filters = _extract_request_filters(user_message)
            for record in properties:
                live = live_prices.get(record.property_id)
                scrape_status = live.scrape_status if live else ScrapeStatus.SKIPPED

                if live and live.nightly_price_usd and scrape_status == ScrapeStatus.SUCCESS:
                    display_price = live.nightly_price_usd
                else:
                    display_price = record.avg_price_usd

                safe_url = _safe_property_url(record)

                passed, notes = self._review_property(
                    record=record,
                    live=live,
                    display_price=display_price,
                    max_budget_usd=max_budget_usd,
                    scrape_status=scrape_status,
                    request_filters=request_filters,
                )

                if scrape_status == ScrapeStatus.STRUCTURE_CHANGED:
                    passed = False
                    notes = (
                        "Live pricing unavailable - booking page structure changed. "
                        f"Showing estimated ${display_price}/night from database. "
                        "Click the link to verify current rates."
                    )
                elif scrape_status == ScrapeStatus.FAILED:
                    notes += " Live price check failed; showing database estimate."

                verified.append(
                    VerifiedProperty(
                        property_id=record.property_id,
                        name=record.name,
                        property_type=record.property_type,
                        city=record.city,
                        country=record.country,
                        latitude=record.latitude,
                        longitude=record.longitude,
                        amenities=record.amenities,
                        star_rating=record.star_rating,
                        nightly_price_usd=display_price,
                        total_price_usd=live.total_price_usd if live else None,
                        is_available=live.is_available if live else None,
                        source_url=safe_url,
                        reviewer_notes=notes,
                        passed_review=passed,
                        distance_info=distance_info,
                        scrape_status=scrape_status,
                    )
                )

            return verified, self._build_summary(verified, request_filters)

        except Exception as exc:
            logger.error("[Reviewer] Error: %s", exc)
            verified = []
            for record in properties:
                live = live_prices.get(record.property_id)
                verified.append(
                    VerifiedProperty(
                        property_id=record.property_id,
                        name=record.name,
                        property_type=record.property_type,
                        city=record.city,
                        country=record.country,
                        latitude=record.latitude,
                        longitude=record.longitude,
                        amenities=record.amenities,
                        star_rating=record.star_rating,
                        nightly_price_usd=live.nightly_price_usd if live else record.avg_price_usd,
                        total_price_usd=live.total_price_usd if live else None,
                        is_available=live.is_available if live else None,
                        source_url=_safe_property_url(record),
                        reviewer_notes="Review engine error; showing unfiltered result.",
                        passed_review=True,
                        distance_info=distance_info,
                        scrape_status=live.scrape_status if live else ScrapeStatus.SKIPPED,
                    )
                )
            return verified, "Here are the properties I found."

    def _review_property(
        self,
        record: PropertyRecord,
        live: LivePriceData | None,
        display_price: float | None,
        max_budget_usd: float | None,
        scrape_status: ScrapeStatus,
        request_filters: dict[str, str | None],
    ) -> tuple[bool, str]:
        if live and live.is_available is False:
            return False, "This property is currently marked unavailable."

        if (
            max_budget_usd is not None
            and display_price is not None
            and display_price > max_budget_usd
        ):
            return (
                False,
                f"Estimated nightly price is ${display_price:.0f}, above your ${max_budget_usd:.0f} budget.",
            )

        price_source = "live price" if scrape_status == ScrapeStatus.SUCCESS else "database price"
        exact_city = (
            not request_filters.get("city")
            or record.city.lower() == request_filters["city"]
        )
        exact_type = (
            not request_filters.get("property_type")
            or record.property_type.value == request_filters["property_type"]
        )
        requested_label = _request_label(request_filters)
        if not exact_city or not exact_type:
            if display_price is not None:
                return (
                    True,
                    f"Related alternative to your {requested_label}: "
                    f"{record.city} {record.property_type.value} at about "
                    f"${display_price:.0f}/night ({price_source}).",
                )
            return (
                True,
                f"Related alternative to your {requested_label}: "
                f"{record.city} {record.property_type.value}; check the site for pricing.",
            )

        if display_price is not None:
            if not request_filters.get("property_type"):
                return (
                    True,
                    f"Matches your {requested_label}: {record.property_type.value} "
                    f"at about ${display_price:.0f}/night ({price_source}).",
                )
            return (
                True,
                f"Matches your {record.city} {record.property_type.value} search at about ${display_price:.0f}/night ({price_source}).",
            )

        if not request_filters.get("property_type"):
            return (
                True,
                f"Matches your {requested_label}: {record.property_type.value}; "
                "check the site for pricing.",
            )
        return True, f"Matches your {record.city} {record.property_type.value} search; check the site for pricing."

    def _build_summary(
        self,
        properties: list[VerifiedProperty],
        request_filters: dict[str, str | None],
    ) -> str:
        passed = [p for p in properties if p.passed_review]
        if not passed:
            return (
                "I found properties for your search, but they need a closer check before booking. "
                "Review the flagged matches below and verify current availability on the booking site."
            )

        exact = [
            p
            for p in passed
            if (
                not request_filters.get("city")
                or p.city.lower() == request_filters["city"]
            )
            and (
                not request_filters.get("property_type")
                or p.property_type.value == request_filters["property_type"]
            )
        ]
        primary = exact or passed
        names = ", ".join(p.name for p in primary[:3])
        city = primary[0].city.title()
        type_name = primary[0].property_type.value

        if len(primary) == 1 and len(passed) == 1:
            return (
                f"I found one {type_name} in {city}: {names}. "
                "Check the card below for price, amenities, and booking links."
            )

        if exact and len(exact) < len(passed):
            return (
                f"I found {len(exact)} exact match"
                f"{'' if len(exact) == 1 else 'es'} for your search, including {names}. "
                f"I also included {len(passed) - len(exact)} related alternative"
                f"{'' if len(passed) - len(exact) == 1 else 's'} below."
            )

        if not exact and (request_filters.get("city") or request_filters.get("property_type")):
            return (
                f"I could not find an exact match for every filter, so I included "
                f"{len(passed)} closest alternatives, including {names}."
            )

        return (
            f"I found {len(passed)} matching options in {city}, including {names}. "
            "Check the cards below for prices, amenities, and booking links."
        )


def _safe_property_url(record: PropertyRecord) -> str:
    if record.property_id in EXACT_PROPERTY_URLS:
        return EXACT_PROPERTY_URLS[record.property_id]

    source_url = record.source_url or ""
    parsed = urlparse(source_url)

    if not source_url or source_url == "None" or not parsed.scheme.startswith("http"):
        return _property_search_url(record)

    if "example.com" in parsed.netloc.lower():
        return _property_search_url(record)

    if "airbnb.com" in parsed.netloc.lower() and parsed.path.startswith("/rooms/"):
        return _property_search_url(record)

    return source_url


def _property_search_url(record: PropertyRecord) -> str:
    query = quote_plus(f"{record.name}, {record.city}, {record.country}")
    return f"https://www.booking.com/searchresults.html?ss={query}"


def _extract_request_filters(user_message: str) -> dict[str, str | None]:
    text = user_message.lower()
    return {
        "city": _find_city(text),
        "property_type": _find_property_type(text),
    }


def _find_city(text: str) -> str | None:
    matches = [
        (text.find(alias), len(alias), city)
        for alias, city in CITY_ALIASES.items()
        if alias in text
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: (item[0], -item[1]))[0][2]


def _find_property_type(text: str) -> str | None:
    tokens = set(re.findall(r"[a-z]+", text))
    for alias, property_type in PROPERTY_TYPE_ALIASES.items():
        if alias in tokens:
            return property_type
    return None


def _request_label(request_filters: dict[str, str | None]) -> str:
    city = request_filters.get("city")
    property_type = request_filters.get("property_type")
    if city and property_type:
        return f"{city} {property_type} search"
    if city:
        return f"{city} search"
    if property_type:
        return f"{property_type} search"
    return "search"
