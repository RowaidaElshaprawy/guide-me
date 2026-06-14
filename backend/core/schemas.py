# backend/core/schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum


class PropertyType(str, Enum):
    HOTEL = "hotel"
    APARTMENT = "apartment"
    CHALET = "chalet"
    VILLA = "villa"


class PipelineStage(str, Enum):
    VECTOR_SEARCH = "vector_search"
    LIVE_HYDRATION = "live_hydration"
    CLEANING = "cleaning"
    REVIEW = "review"
    COMPLETE = "complete"


class ScrapeStatus(str, Enum):
    SUCCESS = "success"
    STRUCTURE_CHANGED = "structure_changed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Frontend → FastAPI ──

class ChatRequest(BaseModel):
    session_id: str
    user_message: str = Field(..., min_length=2, max_length=2000)
    conversation_history: list[dict] = Field(default_factory=list)

    @field_validator("user_message")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


# ── ChromaDB property record ──

class PropertyRecord(BaseModel):
    property_id: str
    name: str
    property_type: PropertyType
    city: str
    country: str
    latitude: float
    longitude: float
    source_url: str
    amenities: list[str]
    avg_price_usd: Optional[float] = None
    star_rating: Optional[float] = None
    description: str


# ── Geocoding / Distance ──

class GeocodingResult(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    city: Optional[str] = None
    country: Optional[str] = None


class DistanceResult(BaseModel):
    origin: str
    destination: str
    distance_km: float
    duration_minutes: float


# ── Agent 1 output ──

class VectorSearchResult(BaseModel):
    properties: list[PropertyRecord]
    query_used: str
    requires_live_hydration: bool
    location_context: Optional[GeocodingResult] = None


# ── Scraper contracts ──

class HydrationRequest(BaseModel):
    property_id: str
    source_url: str
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    guests: int = 2


class RawHydrationData(BaseModel):
    property_id: str
    source_url: str
    compressed_html: str
    scrape_timestamp: str
    scrape_status: ScrapeStatus = ScrapeStatus.SUCCESS


# ── Agent 2 output ──

class LivePriceData(BaseModel):
    property_id: str
    nightly_price_usd: Optional[float] = None
    total_price_usd: Optional[float] = None
    currency_original: Optional[str] = None
    cleaning_fee_usd: Optional[float] = None
    is_available: Optional[bool] = None
    availability_notes: Optional[str] = None
    scrape_timestamp: str
    scrape_status: ScrapeStatus = ScrapeStatus.SKIPPED


# ── Booking Intent (new — for autonomous booking flow) ──

class BookingIntent(BaseModel):
    """
    Collected conversationally before generating the pre-filled booking deeplink.
    The system autonomously assembles this and generates a ready-to-click URL.
    """
    property_id: str
    property_name: str
    source_url: str
    check_in: Optional[str] = None       # ISO format: YYYY-MM-DD
    check_out: Optional[str] = None
    guests: int = 2
    rooms: int = 1
    guest_name: Optional[str] = None
    booking_url: Optional[str] = None    # Generated pre-filled deeplink
    nightly_price_usd: Optional[float] = None
    total_price_usd: Optional[float] = None
    is_available: Optional[bool] = None
    scrape_status: ScrapeStatus = ScrapeStatus.SKIPPED
    price_source: str = "database"
    status_message: Optional[str] = None


# ── Final verified output ──

class VerifiedProperty(BaseModel):
    property_id: str
    name: str
    property_type: PropertyType
    city: str
    country: str
    latitude: float
    longitude: float
    amenities: list[str]
    star_rating: Optional[float] = None
    nightly_price_usd: Optional[float] = None
    total_price_usd: Optional[float] = None
    is_available: Optional[bool] = None
    source_url: str
    reviewer_notes: str
    passed_review: bool
    distance_info: Optional[DistanceResult] = None
    scrape_status: ScrapeStatus = ScrapeStatus.SKIPPED
    booking_url: Optional[str] = None    # Pre-filled booking deeplink


# ── FastAPI → Streamlit ──

class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    properties: list[VerifiedProperty]
    pipeline_stage_reached: PipelineStage
    error: Optional[str] = None
    booking_intent: Optional[BookingIntent] = None
