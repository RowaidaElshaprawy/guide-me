# backend/scrapers/scrapling_engine.py
import asyncio
import logging
from datetime import datetime, timezone

from backend.core.schemas import HydrationRequest, RawHydrationData, ScrapeStatus
from backend.scrapers.html_compressor import compress_html

logger = logging.getLogger(__name__)

PRICE_SIGNALS = [
    "per night", "total", "price", "usd", "egp", "eur",
    "$", "£", "€", "night", "book", "reserve", "available",
    "unavailable", "sold out", "fee", "rate",
]


def _has_price_signals(text: str) -> bool:
    text_lower = text.lower()
    return sum(1 for kw in PRICE_SIGNALS if kw in text_lower) >= 3


def _scrape_sync(url: str) -> tuple[str, ScrapeStatus]:
    """
    Synchronous scraping — runs inside asyncio.to_thread.
    Uses Scrapling's StealthyFetcher correctly.
    """
    try:
        from scrapling.fetchers import StealthyFetcher

        fetcher = StealthyFetcher(auto_match=False)
        page = fetcher.fetch(
            url,
            headless=True,
            network_idle=True,
            timeout=30000,
        )

        if not page:
            return "", ScrapeStatus.FAILED

        # Scrapling returns a Page object — get HTML via .html_content or .content
        raw_html = getattr(page, "html_content", None) or getattr(page, "content", "") or ""

        if not raw_html:
            return "", ScrapeStatus.FAILED

        compressed = compress_html(raw_html)

        if not compressed:
            return "", ScrapeStatus.FAILED

        if not _has_price_signals(compressed):
            logger.warning(f"[Scrapling] STRUCTURE_CHANGED detected for {url}")
            return compressed, ScrapeStatus.STRUCTURE_CHANGED

        logger.info(f"[Scrapling] Success — {len(compressed)} chars extracted")
        return compressed, ScrapeStatus.SUCCESS

    except Exception as e:
        logger.error(f"[Scrapling] Exception for {url}: {e}")
        return "", ScrapeStatus.FAILED


class ScraplingEngine:

    async def hydrate(self, request: HydrationRequest) -> RawHydrationData:
        logger.info(f"[ScraplingEngine] Hydrating: {request.property_id} → {request.source_url}")

        compressed_html, status = await asyncio.to_thread(_scrape_sync, request.source_url)
        timestamp = datetime.now(timezone.utc).isoformat()

        if status == ScrapeStatus.STRUCTURE_CHANGED:
            logger.warning(f"[ScraplingEngine] DOM shift for {request.property_id} — reviewer will use DB baseline")

        return RawHydrationData(
            property_id=request.property_id,
            source_url=request.source_url,
            compressed_html=compressed_html,
            scrape_timestamp=timestamp,
            scrape_status=status,
        )