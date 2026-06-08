# backend/agents/orchestrator.py
from backend.core.schemas import (
    ChatRequest, ChatResponse, PipelineStage,
    HydrationRequest, LivePriceData
)
from backend.core.config import Settings
from backend.agents.gemini_searcher import GeminiSearcher
from backend.agents.data_cleaner import DataCleaner
from backend.agents.reviewer import ReviewerAgent
from backend.scrapers.scrapling_engine import ScraplingEngine


class Orchestrator:
    """
    The Central State Machine.

    Controls the full 4-stage pipeline:
    Stage 1: Agent 1 (Gemini) — parse intent + search ChromaDB
    Stage 2: Scrapling Engine — live hydration if needed
    Stage 3: Agent 2 (Phi-3) — extract structured prices from HTML
    Stage 4: Agent 3 (Phi-3) — review, filter, synthesize

    WHY A CLASS AND NOT FUNCTIONS:
    The Orchestrator holds references to all agent instances.
    This means agents initialize once (loading models, configuring API keys)
    and are reused across requests — not re-initialized on every call.
    FastAPI will hold one Orchestrator instance in app state.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.searcher = GeminiSearcher()
        self.cleaner = DataCleaner()
        self.reviewer = ReviewerAgent()
        self.scraper = ScraplingEngine()

    async def run(self, request: ChatRequest) -> ChatResponse:
        print(f"\n[Orchestrator] ── New Request ──────────────────────────")
        print(f"[Orchestrator] Session: {request.session_id}")
        print(f"[Orchestrator] Message: {request.user_message}")

        try:
            # ── STAGE 1: Vector Search ──────────────────────────────
            print("[Orchestrator] Stage 1: Vector Search")
            search_result = await self.searcher.search(
                user_message=request.user_message,
                conversation_history=request.conversation_history,
            )

            if not search_result.properties:
                return ChatResponse(
                    session_id=request.session_id,
                    assistant_message=(
                        "I couldn't find any properties matching your search in our database. "
                        "Try searching for a different city or property type. "
                        "We currently have properties in Cairo, Luxor, Hurghada, "
                        "Sharm El Sheikh, and Siwa."
                    ),
                    properties=[],
                    pipeline_stage_reached=PipelineStage.VECTOR_SEARCH,
                )

            # ── STAGE 2: Live Hydration (conditional) ──────────────
            live_prices: dict[str, LivePriceData] = {}

            if search_result.requires_live_hydration:
                print(f"[Orchestrator] Stage 2: Live Hydration for {len(search_result.properties)} properties")

                for prop in search_result.properties[:3]:  # Limit to top 3 to avoid timeouts
                    try:
                        hydration_request = HydrationRequest(
                            property_id=prop.property_id,
                            source_url=prop.source_url,
                        )
                        raw_data = await self.scraper.hydrate(hydration_request)

                        # ── STAGE 3: Data Cleaning ──────────────────
                        print(f"[Orchestrator] Stage 3: Cleaning data for {prop.property_id}")
                        if raw_data.compressed_html:
                            live_price = await self.cleaner.clean(raw_data)
                            live_prices[prop.property_id] = live_price

                    except Exception as e:
                        print(f"[Orchestrator] Hydration failed for {prop.property_id}: {e}")
                        continue
            else:
                print("[Orchestrator] Stage 2: Skipping live hydration (static data sufficient)")

            # ── STAGE 4: Review & Synthesis ─────────────────────────
            print("[Orchestrator] Stage 4: Review & Synthesis")

            # Re-parse intent to get budget for reviewer
            intent = await self.searcher.parse_query_intent(
                request.user_message,
                request.conversation_history,
            )

            # FIX: Ensure intent context is reliably handled as a dictionary wrapper
            if hasattr(intent, "model_dump"):
                intent_dict = intent.model_dump()
            elif hasattr(intent, "__dict__"):
                intent_dict = intent.__dict__
            elif isinstance(intent, dict):
                intent_dict = intent
            else:
                intent_dict = {}

            # Handle distance query if requested safely
            distance_info = None
            dist_query = intent_dict.get("distance_query", {}) or {}
            
            if isinstance(dist_query, dict) and dist_query.get("origin") and dist_query.get("destination"):
                origin_geo = await self.searcher.geocode_location(dist_query["origin"])
                dest_geo = await self.searcher.geocode_location(dist_query["destination"])

                if origin_geo and dest_geo:
                    distance_info = await self.searcher.get_distance(
                        origin_lat=origin_geo.latitude,
                        origin_lon=origin_geo.longitude,
                        dest_lat=dest_geo.latitude,
                        dest_lon=dest_geo.longitude,
                        origin_name=dist_query["origin"],
                        dest_name=dist_query["destination"],
                    )

            # Fire off batch checking rules aligned with our updated ReviewerAgent implementation
            verified_properties, summary_message = await self.reviewer.review(
                properties=search_result.properties,
                live_prices=live_prices,
                user_message=request.user_message,
                max_budget_usd=intent_dict.get("max_budget_usd"),
                distance_info=distance_info,
            )

            print(f"[Orchestrator] Complete. {len(verified_properties)} properties verified.")

            return ChatResponse(
                session_id=request.session_id,
                assistant_message=summary_message,
                properties=verified_properties,
                pipeline_stage_reached=PipelineStage.COMPLETE,
            )

        except Exception as e:
            print(f"[Orchestrator] Fatal error: {e}")
            return ChatResponse(
                session_id=request.session_id,
                assistant_message="Something went wrong processing your request. Please try again.",
                properties=[],
                pipeline_stage_reached=PipelineStage.VECTOR_SEARCH,
                error=str(e),
            )