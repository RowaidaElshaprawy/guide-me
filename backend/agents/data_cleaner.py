# backend/agents/data_cleaner.py
import json
import re
import logging
from datetime import datetime, timezone
import ollama

from backend.core.config import settings
from backend.core.schemas import LivePriceData, RawHydrationData, ScrapeStatus

logger = logging.getLogger(__name__)


class DataCleaner:
    """
    Agent 2: Local Phi-3 Mini parses compressed HTML into structured price data.
    Runs entirely locally via Ollama — zero API cost.
    """

    def __init__(self):
        self.model = settings.ollama_cleaner_model

    async def clean(self, raw_data: RawHydrationData) -> LivePriceData:
        """
        Accepts RawHydrationData, extracts price/availability, returns LivePriceData.
        """
        property_id = raw_data.property_id
        compressed_html = raw_data.compressed_html
        logger.info(f"[DataCleaner] Parsing property: {property_id}")

        # If scraper flagged a structure change or error, skip inference
        if raw_data.scrape_status in (ScrapeStatus.STRUCTURE_CHANGED, ScrapeStatus.FAILED):
            return LivePriceData(
                property_id=property_id,
                scrape_timestamp=raw_data.scrape_timestamp,
                scrape_status=raw_data.scrape_status,
            )

        if not compressed_html or "[ERROR]" in compressed_html:
            return LivePriceData(
                property_id=property_id,
                scrape_timestamp=raw_data.scrape_timestamp,
                scrape_status=ScrapeStatus.FAILED,
                availability_notes=compressed_html,
            )

        prompt = f"""
You are a data extraction assistant. Extract pricing and availability from booking website text.
Return ONLY valid JSON. No explanation. No markdown. No backticks.

Text:
{compressed_html[:6000]}

Return exactly:
{{
  "nightly_price_usd": number or null,
  "total_price_usd": number or null,
  "currency_original": "USD or EUR or EGP etc or null",
  "cleaning_fee_usd": number or null,
  "is_available": true or false or null,
  "availability_notes": "any availability text or null"
}}

Rules:
- Convert non-USD prices approximately to USD
- is_available is false if: sold out, unavailable, no rooms, fully booked
- is_available is true if: available, book now, reserve, per night
- All numbers are plain numerics, no currency symbols
- null for anything not found
"""
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0},
            )
            raw_text = response["message"]["content"].strip()
            raw_text = re.sub(r"```json|```", "", raw_text).strip()
            extracted = json.loads(raw_text)

            return LivePriceData(
                property_id=property_id,
                nightly_price_usd=extracted.get("nightly_price_usd"),
                total_price_usd=extracted.get("total_price_usd"),
                currency_original=extracted.get("currency_original"),
                cleaning_fee_usd=extracted.get("cleaning_fee_usd"),
                is_available=extracted.get("is_available"),
                availability_notes=extracted.get("availability_notes"),
                scrape_timestamp=raw_data.scrape_timestamp,
                scrape_status=ScrapeStatus.SUCCESS,
            )
        except Exception as e:
            logger.error(f"[DataCleaner] Failed for {property_id}: {e}")
            return LivePriceData(
                property_id=property_id,
                scrape_timestamp=raw_data.scrape_timestamp,
                scrape_status=ScrapeStatus.FAILED,
            )