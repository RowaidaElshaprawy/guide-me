# backend/agents/orchestrator.py

from backend.agents.booking_engine import (
    build_booking_intent,
    extract_booking_details_from_conversation,
    select_property_for_booking,
)
from backend.agents.data_cleaner import DataCleaner
from backend.agents.gemini_searcher import GeminiSearcher
from backend.agents.reviewer import ReviewerAgent
from backend.core.config import Settings
from backend.core.schemas import (
    ChatRequest,
    ChatResponse,
    HydrationRequest,
    LivePriceData,
    PipelineStage,
    ScrapeStatus,
)
from backend.scrapers.scrapling_engine import ScraplingEngine


class Orchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.searcher = GeminiSearcher()
        self.cleaner = DataCleaner()
        self.reviewer = ReviewerAgent()
        self.scraper = ScraplingEngine()

    async def run(self, request: ChatRequest) -> ChatResponse:
        print("\n[Orchestrator] -- New Request --")
        print(f"[Orchestrator] Message: {request.user_message}")

        try:
            print("[Orchestrator] Stage 1: Intent + vector search")
            intent = await self.searcher.parse_query_intent(
                request.user_message,
                request.conversation_history,
            )
            search_result = await self.searcher.search(
                user_message=request.user_message,
                conversation_history=request.conversation_history,
                intent=intent,
            )

            if not search_result.properties:
                return ChatResponse(
                    session_id=request.session_id,
                    assistant_message=(
                        "I couldn't find properties matching your search. "
                        "We have listings in Cairo, Luxor, Hurghada, "
                        "Sharm El Sheikh, Siwa, and Dahab. "
                        "Try searching by city name or property type."
                    ),
                    properties=[],
                    pipeline_stage_reached=PipelineStage.VECTOR_SEARCH,
                )

            live_prices: dict[str, LivePriceData] = {}

            if search_result.requires_live_hydration and not intent.get("wants_to_book"):
                print("[Orchestrator] Stage 2+3: Hydrating top 3 properties")
                for prop in search_result.properties[:3]:
                    live_prices[prop.property_id] = await self._hydrate_property(prop)
            else:
                print("[Orchestrator] Stage 2: Static data sufficient before review")

            print("[Orchestrator] Stage 4: Review & synthesis")
            distance_info = await self._maybe_get_distance(intent)
            verified_properties, summary = await self.reviewer.review(
                properties=search_result.properties,
                live_prices=live_prices,
                user_message=request.user_message,
                max_budget_usd=intent.get("max_budget_usd"),
                distance_info=distance_info,
            )

            booking_intent = None
            if intent.get("wants_to_book") and verified_properties:
                booking_details = extract_booking_details_from_conversation(
                    request.user_message,
                    request.conversation_history,
                )
                selected_record = select_property_for_booking(
                    search_result.properties,
                    booking_details,
                )

                if selected_record:
                    if selected_record.property_id not in live_prices:
                        print(
                            "[Orchestrator] Booking flow: live-checking selected property "
                            f"{selected_record.property_id}"
                        )
                        live_prices[selected_record.property_id] = await self._hydrate_property(
                            selected_record,
                            check_in=intent.get("check_in") or booking_details.get("check_in"),
                            check_out=intent.get("check_out") or booking_details.get("check_out"),
                            guests=intent.get("guests") or booking_details.get("guests", 2),
                        )

                    live_price = live_prices.get(selected_record.property_id)
                    booking_intent = build_booking_intent(
                        property_record=selected_record,
                        check_in=intent.get("check_in") or booking_details.get("check_in"),
                        check_out=intent.get("check_out") or booking_details.get("check_out"),
                        guests=intent.get("guests") or booking_details.get("guests", 2),
                        rooms=booking_details.get("rooms", 1),
                        guest_name=booking_details.get("guest_name"),
                        live_price=live_price,
                    )

                    for prop in verified_properties:
                        if prop.property_id == selected_record.property_id:
                            prop.booking_url = booking_intent.booking_url
                            if live_price:
                                prop.scrape_status = live_price.scrape_status
                                prop.is_available = live_price.is_available
                                if (
                                    live_price.scrape_status == ScrapeStatus.SUCCESS
                                    and live_price.nightly_price_usd
                                ):
                                    prop.nightly_price_usd = live_price.nightly_price_usd
                                    prop.total_price_usd = live_price.total_price_usd
                            break

                    summary += (
                        f"\n\n✅ **Booking assistant ready for {booking_intent.property_name}.** "
                        f"I prepared dates, guests, room count, price source, and a one-click "
                        f"deeplink for final confirmation. {booking_intent.status_message}"
                    )

            print(f"[Orchestrator] Complete - {len(verified_properties)} properties.")

            return ChatResponse(
                session_id=request.session_id,
                assistant_message=summary,
                properties=verified_properties,
                pipeline_stage_reached=PipelineStage.COMPLETE,
                booking_intent=booking_intent,
            )

        except Exception as exc:
            print(f"[Orchestrator] Fatal: {exc}")
            import traceback

            traceback.print_exc()
            return ChatResponse(
                session_id=request.session_id,
                assistant_message="Something went wrong. Please try again.",
                properties=[],
                pipeline_stage_reached=PipelineStage.VECTOR_SEARCH,
                error=str(exc),
            )

    async def _hydrate_property(
        self,
        prop,
        check_in: str | None = None,
        check_out: str | None = None,
        guests: int = 2,
    ) -> LivePriceData:
        try:
            raw_data = await self.scraper.hydrate(
                HydrationRequest(
                    property_id=prop.property_id,
                    source_url=prop.source_url,
                    check_in=check_in,
                    check_out=check_out,
                    guests=guests,
                )
            )
            return await self.cleaner.clean(raw_data)
        except Exception as exc:
            print(f"[Orchestrator] Hydration error for {prop.property_id}: {exc}")
            return LivePriceData(
                property_id=prop.property_id,
                scrape_timestamp="",
                scrape_status=ScrapeStatus.FAILED,
            )

    async def _maybe_get_distance(self, intent: dict):
        dist_query = intent.get("distance_query", {}) or {}
        if not (
            isinstance(dist_query, dict)
            and dist_query.get("origin")
            and dist_query.get("destination")
        ):
            return None

        origin_geo = await self.searcher.geocode_location(dist_query["origin"])
        dest_geo = await self.searcher.geocode_location(dist_query["destination"])
        if not origin_geo or not dest_geo:
            return None

        return await self.searcher.get_distance(
            origin_geo.latitude,
            origin_geo.longitude,
            dest_geo.latitude,
            dest_geo.longitude,
            dist_query["origin"],
            dist_query["destination"],
        )
