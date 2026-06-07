from scrapling.fetchers import StealthyFetcher
from backend.core.schemas import HydrationRequest, RawHydrationData
from backend.scrapers.html_compressor import compress_html
from datetime import datetime, timezone
import asyncio


class ScraplingEngine:
    """
    Real-time live hydration engine.

    WHEN IT RUNS:
    Only when the user explicitly asks for current prices or availability.
    Never on every query — that would be too slow and risk IP blocking.

    HOW STEALTHYFETCHER WORKS:
    - Launches a real Playwright browser (Chromium) headlessly
    - Executes JavaScript — gets the fully rendered DOM, not raw HTML
    - Randomizes fingerprints (user-agent, screen size, timezone, WebGL)
    - Mimics human mouse movements and scroll patterns
    - Bypasses Cloudflare and most anti-bot systems
    """

    async def hydrate(self, request: HydrationRequest) -> RawHydrationData:
        """
        Fetches a live property page and returns compressed HTML for Agent 2.
        Runs in a thread pool because Scrapling is synchronous internally.
        """
        print(f"[Scrapling] Hydrating: {request.source_url}")

        # Run the synchronous scraper in a thread to avoid blocking FastAPI's event loop
        raw_html = await asyncio.to_thread(self._scrape, request.source_url)

        compressed = compress_html(raw_html)
        timestamp = datetime.now(timezone.utc).isoformat()

        print(f"[Scrapling] Done. Compressed HTML: {len(compressed)} chars.")

        return RawHydrationData(
            property_id=request.property_id,
            source_url=request.source_url,
            compressed_html=compressed,
            scrape_timestamp=timestamp,
        )

    def _scrape(self, url: str) -> str:
        """
        Synchronous scraping call — runs inside asyncio.to_thread.
        Returns raw HTML string of the fully rendered page.
        """
        try:
            fetcher = StealthyFetcher(auto_match=False)
            page = fetcher.fetch(
                url,
                headless=True,
                network_idle=True,       # Wait until all XHR/fetch calls complete
                timeout=30000,           # 30 second timeout
            )
            return page.html_content
        except Exception as e:
            print(f"[Scrapling] Error scraping {url}: {e}")
            return ""