# backend/agents/gemini_searcher.py
import httpx
import json
import re
from backend.core.config import settings
from backend.core.schemas import (
    VectorSearchResult, PropertyRecord, PropertyType,
    GeocodingResult, DistanceResult,
)
from backend.core import database
from backend.agents.providers import ProviderRouter, ProviderError


class GeminiSearcher:
    """
    Agent 1 — Intent Parser & Vector Search Coordinator.
    Uses ProviderRouter for automatic Gemini → Groq failover.
    """

    def __init__(self):
        self._router: ProviderRouter | None = None

    @property
    def router(self) -> ProviderRouter:
        if self._router is None:
            self._router = ProviderRouter()
        return self._router

    def _fallback_intent(
        self,
        user_message: str,
        conversation_history: list | None = None,
    ) -> dict:
        text = user_message.lower()
        city_aliases = {
            "cairo": "Cairo",
            "giza": "Cairo",
            "pyramid": "Cairo",
            "pyramids": "Cairo",
            "great pyramid": "Cairo",
            "great pyramids": "Cairo",
            "sphinx": "Cairo",
            "luxor": "Luxor",
            "hurghada": "Hurghada",
            "sharm el sheikh": "Sharm El Sheikh",
            "sharm": "Sharm El Sheikh",
            "siwa": "Siwa",
            "dahab": "Dahab",
        }
        property_type_aliases = {
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
        city = _find_city(text, city_aliases)
        property_type = _find_property_type(text, property_type_aliases)
        distance_query = _extract_distance_query(text, city_aliases)

        if conversation_history and (not city or not property_type):
            history_text = " ".join(
                m.get("content", "")
                for m in conversation_history[-4:]
                if m.get("role") == "user"
            ).lower()
            city = city or _find_city(history_text, city_aliases)
            property_type = property_type or _find_property_type(
                history_text, property_type_aliases
            )

        budget_match = re.search(
            r"(?:under|below|less than|max(?:imum)?|budget)\s*\$?\s*(\d+)",
            text,
        )
        max_budget = float(budget_match.group(1)) if budget_match else None
        amenities = [
            amenity
            for amenity in (
                "pool",
                "wifi",
                "breakfast",
                "gym",
                "spa",
                "beach",
                "kitchen",
                "diving",
                "private beach",
                "nile view",
                "sea view",
                "desert view",
            )
            if amenity in text
        ]
        return {
            "city": city,
            "country": "Egypt",
            "property_type": property_type,
            "max_budget_usd": max_budget,
            "amenities_requested": amenities,
            "wants_live_prices": any(
                phrase in text
                for phrase in ("current price", "available", "book", "tonight", "this weekend")
            ),
            "wants_to_book": any(
                phrase in text for phrase in ("book", "reserve", "confirm", "proceed")
            ),
            "check_in": None,
            "check_out": None,
            "guests": 2,
            "distance_query": distance_query,
            "search_query": user_message,
        }

    def _can_use_fast_intent(self, intent: dict) -> bool:
        return bool(
            intent.get("city")
            or intent.get("property_type")
            or intent.get("max_budget_usd")
            or intent.get("wants_live_prices")
            or intent.get("wants_to_book")
            or (intent.get("distance_query") or {}).get("origin")
        )

    async def parse_query_intent(self, user_message: str, conversation_history: list) -> dict:
        fast_intent = self._fallback_intent(user_message, conversation_history)
        if self._can_use_fast_intent(fast_intent):
            return fast_intent

        history_text = ""
        if conversation_history:
            recent = conversation_history[-4:]
            history_text = "\n".join([
                f"{m['role'].upper()}: {m['content']}" for m in recent
            ])

        prompt = f"""
You are a travel query parser for Egypt. Extract structured information from the user message.
Return ONLY valid JSON, no explanation, no markdown, no backticks.

Conversation history:
{history_text}

User message: "{user_message}"

Return exactly this JSON structure:
{{
  "city": "Egyptian city name or null (e.g. Cairo, Hurghada, Luxor, Siwa, Sharm El Sheikh, Dahab)",
  "country": "Egypt or null",
  "property_type": "hotel or apartment or chalet or villa or null",
  "max_budget_usd": number or null,
  "amenities_requested": ["amenity1", "amenity2"],
  "wants_live_prices": true or false,
  "wants_to_book": true or false,
  "check_in": "YYYY-MM-DD or null",
  "check_out": "YYYY-MM-DD or null",
  "guests": number or null,
  "distance_query": {{
    "origin": "place name or null",
    "destination": "place name or null"
  }},
  "search_query": "natural language query for semantic vector search about Egypt stays"
}}

Rules:
- wants_live_prices is true if user mentions:
  current price, available, book, tonight, this weekend, prices now
- wants_to_book is true if user says: book, reserve, I want this one, confirm, proceed
- Extract check_in/check_out dates if mentioned in any format
- city must be an Egyptian location or null
- search_query should be descriptive: mention location, property features, traveler type
"""
        try:
            raw = self.router.generate(prompt, temperature=0.1)
            raw = ProviderRouter.clean_json(raw)
            return json.loads(raw)
        except (ProviderError, json.JSONDecodeError) as e:
            print(f"[GeminiSearcher] Intent parsing failed: {e}. Using fallback.")
            return self._fallback_intent(user_message, conversation_history)

    async def geocode_location(self, location: str) -> GeocodingResult | None:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.nominatim_base_url}/search",
                    params={"q": location, "format": "json", "limit": 1, "addressdetails": 1},
                    headers={"User-Agent": "GuideMe-TravelBot/1.0 (graduation project)"},
                    timeout=10.0,
                )
                data = response.json()
            if not data:
                return None
            result = data[0]
            address = result.get("address", {})
            return GeocodingResult(
                display_name=result.get("display_name", location),
                latitude=float(result["lat"]),
                longitude=float(result["lon"]),
                city=address.get("city") or address.get("town") or address.get("village"),
                country=address.get("country"),
            )
        except Exception as e:
            print(f"[GeminiSearcher] Geocoding failed for '{location}': {e}")
            return None

    async def get_distance(
        self,
        origin_lat: float, origin_lon: float,
        dest_lat: float, dest_lon: float,
        origin_name: str, dest_name: str,
    ) -> DistanceResult | None:
        try:
            url = (
                f"{settings.osrm_base_url}/route/v1/driving/"
                f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
            )
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params={"overview": "false"}, timeout=10.0)
                data = response.json()
            if data.get("code") != "Ok":
                return None
            route = data["routes"][0]
            return DistanceResult(
                origin=origin_name,
                destination=dest_name,
                distance_km=round(route["distance"] / 1000, 1),
                duration_minutes=round(route["duration"] / 60, 0),
            )
        except Exception as e:
            print(f"[GeminiSearcher] Distance failed: {e}")
            return None

    def _metadata_to_record(self, metadata: dict) -> PropertyRecord:
        import json as j
        amenities = metadata.get("amenities", "[]")
        if isinstance(amenities, str):
            amenities = j.loads(amenities)
        return PropertyRecord(
            property_id=metadata["property_id"],
            name=metadata["name"],
            property_type=PropertyType(metadata["property_type"]),
            city=metadata["city"],
            country=metadata["country"],
            latitude=float(metadata["latitude"]),
            longitude=float(metadata["longitude"]),
            source_url=metadata["source_url"],
            amenities=amenities,
            avg_price_usd=float(metadata.get("avg_price_usd", 0)) or None,
            star_rating=float(metadata.get("star_rating", 0)) or None,
            description=metadata.get("description", ""),
        )

    async def search(
        self,
        user_message: str,
        conversation_history: list,
        intent: dict | None = None,
    ) -> VectorSearchResult:
        print(f"[GeminiSearcher] Processing: '{user_message}'")
        if intent is None:
            intent = await self.parse_query_intent(user_message, conversation_history)
        print(f"[GeminiSearcher] Intent: {intent}")

        raw_results = database.search_properties(
            query=intent["search_query"],
            city_filter=intent.get("city"),
            property_type_filter=intent.get("property_type"),
            max_price_filter=intent.get("max_budget_usd"),
            n_results=5,
            prefer_keyword=self._can_use_fast_intent(intent),
        )
        properties = [self._metadata_to_record(r) for r in raw_results]

        location_context = None
        distance_query = intent.get("distance_query") or {}
        if intent.get("city") and distance_query.get("origin") and distance_query.get("destination"):
            loc = intent["city"]
            if intent.get("country"):
                loc += f", {intent['country']}"
            location_context = await self.geocode_location(loc)

        requires_hydration = intent.get("wants_live_prices", False) or len(properties) == 0

        return VectorSearchResult(
            properties=properties,
            query_used=intent["search_query"],
            requires_live_hydration=requires_hydration,
            location_context=location_context,
        )


def _find_city(text: str, city_aliases: dict[str, str]) -> str | None:
    matches = [
        (text.find(alias), len(alias), city)
        for alias, city in city_aliases.items()
        if alias in text
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: (item[0], -item[1]))[0][2]


def _find_property_type(text: str, property_type_aliases: dict[str, str]) -> str | None:
    tokens = set(re.findall(r"[a-z]+", text))
    for alias, property_type in property_type_aliases.items():
        if alias in tokens:
            return property_type
    return None


def _extract_distance_query(text: str, city_aliases: dict[str, str]) -> dict:
    empty = {"origin": None, "destination": None}
    if not any(phrase in text for phrase in ("how far", "distance", "drive", "route")):
        return empty

    city_matches = []
    for alias, city in city_aliases.items():
        index = text.find(alias)
        if index >= 0:
            city_matches.append((index, len(alias), city))

    unique_cities = []
    for _, _, city in sorted(city_matches, key=lambda item: (item[0], -item[1])):
        if city not in unique_cities:
            unique_cities.append(city)

    if len(unique_cities) < 2:
        return empty

    if re.search(r"\bfrom\b.+\bto\b", text):
        return {"origin": unique_cities[0], "destination": unique_cities[1]}

    if re.search(r"\bfrom\b", text):
        return {"origin": unique_cities[1], "destination": unique_cities[0]}

    return {"origin": unique_cities[0], "destination": unique_cities[1]}
