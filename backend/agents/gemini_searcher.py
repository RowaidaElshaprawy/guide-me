import google.generativeai as genai
import httpx
import json
from backend.core.config import settings
from backend.core.schemas import (
    VectorSearchResult, PropertyRecord, PropertyType,
    GeocodingResult, DistanceResult, HydrationRequest
)
from backend.core import database


class GeminiSearcher:
    """
    Agent 1 — The Decision Maker.

    RESPONSIBILITIES:
    1. Parse the user's natural language query for intent, location, and constraints
    2. Query ChromaDB using semantic vector search
    3. Geocode locations using Nominatim (free OSM API)
    4. Calculate distances using OSRM (free routing API)
    5. Decide whether live hydration (Scrapling) is needed

    WHY GEMINI FLASH SPECIFICALLY:
    - Free tier: 15 requests/minute, 1 million tokens/day
    - Fast enough for real-time chat responses
    - Strong enough for intent parsing and decision making
    - We only use it for Agent 1 — Agents 2 & 3 use local Phi-3 Mini
    """

    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model)

    async def parse_query_intent(self, user_message: str, conversation_history: list) -> dict:
        """
        Uses Gemini to extract structured intent from natural language.

        Returns a dict with:
        - city: extracted city name or None
        - country: extracted country name or None
        - property_type: hotel/apartment/chalet/villa or None
        - max_budget_usd: numeric budget or None
        - amenities_requested: list of requested amenities
        - wants_live_prices: bool — did user ask for current prices?
        - distance_query: dict with origin/destination if user asks "how far"
        - search_query: reformulated query optimized for semantic vector search
        """
        history_text = ""
        if conversation_history:
            recent = conversation_history[-4:]  # Last 4 turns for context
            history_text = "\n".join([
                f"{m['role'].upper()}: {m['content']}"
                for m in recent
            ])

        prompt = f"""
You are a travel query parser. Extract structured information from the user message.
Return ONLY valid JSON, no explanation, no markdown, no backticks.

Conversation history (for context):
{history_text}

User message: "{user_message}"

Return exactly this JSON structure:
{{
  "city": "city name or null",
  "country": "country name or null",
  "property_type": "hotel or apartment or chalet or villa or null",
  "max_budget_usd": number or null,
  "amenities_requested": ["amenity1", "amenity2"],
  "wants_live_prices": true or false,
  "distance_query": {{
    "origin": "place name or null",
    "destination": "place name or null"
  }},
  "search_query": "a natural language query optimized for semantic search about travel accommodations"
}}

Rules:
- wants_live_prices is true if user says: current price, available, book, tonight, this weekend
- distance_query origin and destination are null unless user explicitly asks about distance
- search_query should be descriptive and mention property features, location feel, and traveler type
"""
        try:
            response = self.model.generate_content(prompt)
            raw = response.text.strip()
            # Strip markdown code fences if Gemini adds them
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except Exception as e:
            print(f"[GeminiSearcher] Intent parsing failed: {e}")
            # Fallback: treat entire message as search query
            return {
                "city": None,
                "country": None,
                "property_type": None,
                "max_budget_usd": None,
                "amenities_requested": [],
                "wants_live_prices": False,
                "distance_query": {"origin": None, "destination": None},
                "search_query": user_message,
            }

    async def geocode_location(self, location: str) -> GeocodingResult | None:
        """
        Converts a place name to coordinates using Nominatim (free OSM geocoding).
        No API key required. Rate limit: 1 request/second — we respect it.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.nominatim_base_url}/search",
                    params={
                        "q": location,
                        "format": "json",
                        "limit": 1,
                        "addressdetails": 1,
                    },
                    headers={"User-Agent": "TravelAgentBot/1.0 (educational project)"},
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
        """
        Calculates driving distance and duration using OSRM (free routing API).
        No API key required.
        """
        try:
            url = (
                f"{settings.osrm_base_url}/route/v1/driving/"
                f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
            )
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params={"overview": "false", "alternatives": "false"},
                    timeout=10.0,
                )
                data = response.json()

            if data.get("code") != "Ok":
                return None

            route = data["routes"][0]
            distance_km = round(route["distance"] / 1000, 1)
            duration_min = round(route["duration"] / 60, 0)

            return DistanceResult(
                origin=origin_name,
                destination=dest_name,
                distance_km=distance_km,
                duration_minutes=duration_min,
            )
        except Exception as e:
            print(f"[GeminiSearcher] Distance calculation failed: {e}")
            return None

    def _metadata_to_property_record(self, metadata: dict) -> PropertyRecord:
        """Converts ChromaDB flat metadata dict back into a typed PropertyRecord."""
        import json as json_lib
        amenities = metadata.get("amenities", "[]")
        if isinstance(amenities, str):
            amenities = json_lib.loads(amenities)

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
    ) -> VectorSearchResult:
        """
        Full Agent 1 execution:
        1. Parse intent with Gemini
        2. Search ChromaDB with semantic query + metadata filters
        3. Geocode location if found
        4. Decide if live hydration is needed
        """
        print(f"[GeminiSearcher] Processing: '{user_message}'")

        # Step 1 — Parse intent
        intent = await self.parse_query_intent(user_message, conversation_history)
        print(f"[GeminiSearcher] Intent: {intent}")

        # Step 2 — Search ChromaDB
        raw_results = database.search_properties(
            query=intent["search_query"],
            city_filter=intent.get("city"),
            property_type_filter=intent.get("property_type"),
            max_price_filter=intent.get("max_budget_usd"),
            n_results=5,
        )

        properties = [self._metadata_to_property_record(r) for r in raw_results]

        # Step 3 — Geocode if we have a location
        location_context = None
        if intent.get("city"):
            query_location = intent["city"]
            if intent.get("country"):
                query_location += f", {intent['country']}"
            location_context = await self.geocode_location(query_location)

        # Step 4 — Decide on live hydration
        # Trigger if: user wants live prices OR no properties found in static DB
        requires_hydration = intent.get("wants_live_prices", False) or len(properties) == 0

        return VectorSearchResult(
            properties=properties,
            query_used=intent["search_query"],
            requires_live_hydration=requires_hydration,
            location_context=location_context,
        )