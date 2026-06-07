import ollama
import json
import re
from backend.core.config import settings
from backend.core.schemas import RawHydrationData, LivePriceData
from datetime import datetime, timezone


class DataCleaner:
    """
    Agent 2 — The Structured Extractor.

    RECEIVES: Compressed HTML text from Scrapling (~8000 chars)
    PRODUCES: Clean LivePriceData with nightly price, fees, availability

    WHY PHI-3 MINI FOR THIS JOB:
    This is a pure extraction task — not reasoning or creativity.
    Phi-3 Mini is excellent at following strict JSON output instructions.
    It runs fully locally so there is no per-token cost and no rate limits.
    The compressed HTML input is small enough to fit in Phi-3's context window.
    """

    def __init__(self):
        self.model = settings.ollama_cleaner_model

    async def clean(self, raw_data: RawHydrationData) -> LivePriceData:
        """
        Sends compressed HTML to Phi-3 Mini and extracts structured price data.
        """
        print(f"[DataCleaner] Cleaning HTML for property: {raw_data.property_id}")

        prompt = f"""
You are a data extraction assistant. Extract pricing and availability information from the following text scraped from a travel booking website.

Return ONLY valid JSON. No explanation. No markdown. No backticks.

Text to analyze:
{raw_data.compressed_html}

Return exactly this JSON structure:
{{
  "nightly_price_usd": number or null,
  "total_price_usd": number or null,
  "currency_original": "USD or EUR or EGP etc or null",
  "cleaning_fee_usd": number or null,
  "is_available": true or false or null,
  "availability_notes": "any relevant availability text or null"
}}

Rules:
- If a price is in a non-USD currency, convert it approximately to USD
- is_available is false if you see: sold out, unavailable, no rooms left, fully booked
- is_available is true if you see: available, book now, reserve, per night
- is_available is null if you cannot determine availability
- All numeric values should be plain numbers with no currency symbols
- If you cannot find a value, use null
"""

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},  # Low temp = more deterministic extraction
            )

            raw_text = response["message"]["content"].strip()

            # Strip any markdown fences the model might add
            raw_text = re.sub(r"```json|```", "", raw_text).strip()

            extracted = json.loads(raw_text)

            return LivePriceData(
                property_id=raw_data.property_id,
                nightly_price_usd=extracted.get("nightly_price_usd"),
                total_price_usd=extracted.get("total_price_usd"),
                currency_original=extracted.get("currency_original"),
                cleaning_fee_usd=extracted.get("cleaning_fee_usd"),
                is_available=extracted.get("is_available"),
                availability_notes=extracted.get("availability_notes"),
                scrape_timestamp=raw_data.scrape_timestamp,
            )

        except json.JSONDecodeError as e:
            print(f"[DataCleaner] JSON parse failed: {e}. Returning empty price data.")
            return LivePriceData(
                property_id=raw_data.property_id,
                scrape_timestamp=raw_data.scrape_timestamp,
            )
        except Exception as e:
            print(f"[DataCleaner] Unexpected error: {e}")
            return LivePriceData(
                property_id=raw_data.property_id,
                scrape_timestamp=raw_data.scrape_timestamp,
            )