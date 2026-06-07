import ollama
import json
import re
from backend.core.config import settings
from backend.core.schemas import (
    PropertyRecord, LivePriceData, VerifiedProperty,
    PropertyType, DistanceResult
)


class Reviewer:
    """
    Agent 3 — The Quality Controller and Synthesizer.

    RECEIVES: Static property records + live price data + user constraints
    PRODUCES: Final verified list with reviewer notes + narrative response

    TWO JOBS:
    1. FILTER: Drop properties that violate user constraints (over budget, wrong type, unavailable)
    2. SYNTHESIZE: Write a natural conversational response summarizing what was found

    WHY LOCAL MODEL FOR THIS:
    Filtering is rule-based logic. Synthesis is short-form writing.
    Both are well within Phi-3 Mini's capability with zero API cost.
    """

    def __init__(self):
        self.model = settings.ollama_reviewer_model

    def _merge_property_data(
        self,
        record: PropertyRecord,
        live_data: LivePriceData | None,
        distance_info: DistanceResult | None,
    ) -> dict:
        """Merges static and live data into a single dict for the reviewer prompt."""
        return {
            "property_id": record.property_id,
            "name": record.name,
            "type": record.property_type.value,
            "city": record.city,
            "country": record.country,
            "amenities": record.amenities,
            "star_rating": record.star_rating,
            "static_avg_price_usd": record.avg_price_usd,
            "live_nightly_price_usd": live_data.nightly_price_usd if live_data else None,
            "live_total_price_usd": live_data.total_price_usd if live_data else None,
            "is_available": live_data.is_available if live_data else None,
            "availability_notes": live_data.availability_notes if live_data else None,
            "distance_km": distance_info.distance_km if distance_info else None,
            "duration_minutes": distance_info.duration_minutes if distance_info else None,
            "source_url": record.source_url,
        }

    async def review(
        self,
        properties: list[PropertyRecord],
        live_prices: dict[str, LivePriceData],
        user_message: str,
        max_budget_usd: float | None,
        distance_info: DistanceResult | None,
    ) -> tuple[list[VerifiedProperty], str]:
        """
        Reviews all properties and returns:
        - List of VerifiedProperty objects (passed or failed review)
        - Natural language assistant message summarizing results
        """
        if not properties:
            return [], (
                "I couldn't find any properties matching your request in our database. "
                "Try broadening your search — for example, search by country instead of city, "
                "or remove specific amenity requirements."
            )

        merged = [
            self._merge_property_data(
                p,
                live_prices.get(p.property_id),
                distance_info,
            )
            for p in properties
        ]

        prompt = f"""
You are a travel recommendation reviewer. Review these properties against the user's request and return structured JSON.

User request: "{user_message}"
Budget constraint: {f"Maximum ${max_budget_usd} per night" if max_budget_usd else "No budget specified"}

Properties to review:
{json.dumps(merged, indent=2)}

For each property, decide if it PASSES review based on:
1. Budget: if max budget specified and price exceeds it → FAIL
2. Availability: if is_available is explicitly false → FAIL
3. Everything else: PASS (be generous, user can decide)

Return ONLY valid JSON, no explanation, no markdown:
{{
  "reviewed_properties": [
    {{
      "property_id": "...",
      "passed_review": true or false,
      "reviewer_notes": "one sentence explaining why it passed or failed",
      "recommended_nightly_price": number or null
    }}
  ],
  "summary_message": "A warm, helpful 2-3 sentence summary of what you found. Mention the best options. If nothing passed, suggest alternatives. Be conversational, not robotic."
}}
"""

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )

            raw_text = response["message"]["content"].strip()
            raw_text = re.sub(r"```json|```", "", raw_text).strip()
            result = json.loads(raw_text)

            # Build VerifiedProperty list
            review_map = {
                r["property_id"]: r
                for r in result["reviewed_properties"]
            }

            verified = []
            for record in properties:
                review = review_map.get(record.property_id, {})
                live = live_prices.get(record.property_id)
                dist = distance_info

                verified.append(VerifiedProperty(
                    property_id=record.property_id,
                    name=record.name,
                    property_type=record.property_type,
                    city=record.city,
                    country=record.country,
                    latitude=record.latitude,
                    longitude=record.longitude,
                    amenities=record.amenities,
                    star_rating=record.star_rating,
                    nightly_price_usd=(
                        live.nightly_price_usd if live and live.nightly_price_usd
                        else record.avg_price_usd
                    ),
                    total_price_usd=live.total_price_usd if live else None,
                    is_available=live.is_available if live else None,
                    source_url=record.source_url,
                    reviewer_notes=review.get("reviewer_notes", "No review available."),
                    passed_review=review.get("passed_review", True),
                    distance_info=dist,
                ))

            summary = result.get("summary_message", "Here are the properties I found for you.")
            return verified, summary

        except Exception as e:
            print(f"[Reviewer] Error: {e}")
            # Fallback — pass everything through without review
            verified = []
            for record in properties:
                live = live_prices.get(record.property_id)
                verified.append(VerifiedProperty(
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
                    source_url=record.source_url,
                    reviewer_notes="Review unavailable — showing unfiltered results.",
                    passed_review=True,
                    distance_info=distance_info,
                ))
            return verified, "Here are the properties I found. Review was unavailable so results are unfiltered."