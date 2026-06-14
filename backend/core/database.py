from backend.core.config import settings
from backend.core.schemas import PropertyRecord, PropertyType
from typing import Any, Optional
import json
import re
from urllib.parse import quote_plus

CITY_ALIASES = {
    "cairo": "cairo",
    "giza": "cairo",
    "pyramid": "cairo",
    "pyramids": "cairo",
    "great pyramid": "cairo",
    "great pyramids": "cairo",
    "sphinx": "cairo",
    "luxor": "luxor",
    "hurghada": "hurghada",
    "sharm": "sharm el sheikh",
    "sharm el sheikh": "sharm el sheikh",
    "sharm-el-sheikh": "sharm el sheikh",
    "siwa": "siwa",
    "dahab": "dahab",
}

PROPERTY_TYPE_ALIASES = {
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

EXACT_PROPERTY_URLS = {
    "prop_005": "https://www.booking.com/hotel/eg/luxor-guest-house.en-gb.html",
}


_chroma_client: Optional[Any] = None
_embedding_model: Optional[Any] = None
_embedding_model_error: Optional[Exception] = None


def get_chroma_client() -> Any:
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        _chroma_client = chromadb.PersistentClient(
            path=settings.chroma_persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def get_embedding_model() -> Any:
    global _embedding_model, _embedding_model_error
    if _embedding_model_error is not None:
        raise RuntimeError(f"Embedding model unavailable: {_embedding_model_error}")
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        print(f"[Database] Loading embedding model: {settings.embedding_model}")
        try:
            _embedding_model = SentenceTransformer(settings.embedding_model, local_files_only=True)
        except TypeError:
            _embedding_model = SentenceTransformer(settings.embedding_model)
        except Exception as exc:
            _embedding_model_error = exc
            raise
        print("[Database] Embedding model ready.")
    return _embedding_model


def get_collection() -> Any:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=settings.chroma_collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def add_property(record: PropertyRecord) -> None:
    model = get_embedding_model()
    collection = get_collection()
    embedding = model.encode(record.description).tolist()
    collection.upsert(
        ids=[record.property_id],
        embeddings=[embedding],
        documents=[record.description],
        metadatas=[{
            "property_id": str(record.property_id),
            "name": str(record.name),
            "property_type": record.property_type.value,
            "city": record.city.lower().strip(),
            "country": record.country.lower().strip(),
            "latitude": float(record.latitude),
            "longitude": float(record.longitude),
            "source_url": str(record.source_url),
            "amenities": json.dumps(record.amenities),
            "avg_price_usd": float(record.avg_price_usd) if record.avg_price_usd is not None else 0.0,
            "star_rating": float(record.star_rating) if record.star_rating is not None else 0.0,
        }],
    )


def _sample_properties() -> list[PropertyRecord]:
    return [
        PropertyRecord(
            property_id="prop_001",
            name="Nile View Luxury Hotel",
            property_type=PropertyType.HOTEL,
            city="Cairo",
            country="Egypt",
            latitude=30.0444,
            longitude=31.2357,
            source_url=_property_search_url("Nile View Luxury Hotel", "Cairo"),
            amenities=["pool", "wifi", "breakfast", "gym", "river view", "spa"],
            avg_price_usd=120.0,
            star_rating=5.0,
            description=(
                "A luxurious 5-star hotel on the banks of the Nile River in Cairo. "
                "Features stunning river views, rooftop pool, full spa, and complimentary "
                "breakfast. Walking distance to the Egyptian Museum and Khan el-Khalili bazaar. "
                "Perfect for couples and business travelers seeking premium comfort in central Cairo."
            ),
        ),
        PropertyRecord(
            property_id="prop_002",
            name="Old Town Cairo Apartment",
            property_type=PropertyType.APARTMENT,
            city="Cairo",
            country="Egypt",
            latitude=30.0459,
            longitude=31.2624,
            source_url=_property_search_url("Old Town Cairo Apartment", "Cairo"),
            amenities=["wifi", "kitchen", "washing machine", "air conditioning"],
            avg_price_usd=45.0,
            star_rating=4.2,
            description=(
                "A charming 2-bedroom apartment in the heart of Islamic Cairo. "
                "Fully equipped kitchen, fast wifi, and authentic local feel. "
                "Steps from Al-Azhar mosque and the historic bazaars. "
                "Ideal for budget-conscious travelers wanting an authentic Cairo experience."
            ),
        ),
        PropertyRecord(
            property_id="prop_008",
            name="Giza Pyramids View Inn",
            property_type=PropertyType.HOTEL,
            city="Cairo",
            country="Egypt",
            latitude=29.9773,
            longitude=31.1325,
            source_url=_property_search_url("Giza Pyramids View Inn", "Giza"),
            amenities=["wifi", "breakfast", "pyramids view", "rooftop terrace", "airport shuttle"],
            avg_price_usd=85.0,
            star_rating=4.3,
            description=(
                "A comfortable hotel-style stay in Giza near the Great Pyramids and the Sphinx. "
                "Features rooftop terrace views of the pyramids, breakfast, wifi, and easy access "
                "to the Giza Plateau. Ideal for travelers who want to stay close to Egypt's "
                "most famous ancient landmarks."
            ),
        ),
        PropertyRecord(
            property_id="prop_003",
            name="Sahara Desert Chalet",
            property_type=PropertyType.CHALET,
            city="Siwa",
            country="Egypt",
            latitude=29.2032,
            longitude=25.5194,
            source_url=_property_search_url("Sahara Desert Chalet", "Siwa"),
            amenities=["wifi", "desert view", "private pool", "all-inclusive", "camel tours"],
            avg_price_usd=200.0,
            star_rating=4.8,
            description=(
                "An exclusive eco-chalet on the edge of the Sahara Desert in Siwa Oasis. "
                "Private plunge pool, stunning sand dune views, all-inclusive meals. "
                "Guided camel tours, sandboarding, and stargazing available. "
                "Perfect for adventurous travelers seeking a unique luxury desert escape."
            ),
        ),
        PropertyRecord(
            property_id="prop_004",
            name="Red Sea Beach Villa",
            property_type=PropertyType.VILLA,
            city="Hurghada",
            country="Egypt",
            latitude=27.2579,
            longitude=33.8116,
            source_url=_property_search_url("Red Sea Beach Villa", "Hurghada"),
            amenities=["private beach", "pool", "wifi", "snorkeling gear", "bbq", "sea view"],
            avg_price_usd=350.0,
            star_rating=4.9,
            description=(
                "A stunning beachfront villa on the Red Sea coast in Hurghada. "
                "Private beach access, infinity pool, world-class snorkeling. "
                "Sleeps up to 8 guests with private chef and housekeeper. "
                "Ideal for families or groups wanting a premium Red Sea holiday."
            ),
        ),
        PropertyRecord(
            property_id="prop_005",
            name="Luxor Heritage Guesthouse",
            property_type=PropertyType.HOTEL,
            city="Luxor",
            country="Egypt",
            latitude=25.6872,
            longitude=32.6396,
            source_url=EXACT_PROPERTY_URLS["prop_005"],
            amenities=["wifi", "rooftop terrace", "breakfast", "nile view", "temple tours"],
            avg_price_usd=65.0,
            star_rating=4.5,
            description=(
                "A beautifully restored heritage guesthouse overlooking the Nile in Luxor. "
                "Rooftop terrace with direct views of Luxor Temple, complimentary breakfast. "
                "Walking distance to Karnak Temple and Valley of the Kings ferry. "
                "Perfect for history lovers and culture travelers."
            ),
        ),
        PropertyRecord(
            property_id="prop_006",
            name="Sharm El Sheikh Resort Hotel",
            property_type=PropertyType.HOTEL,
            city="Sharm El Sheikh",
            country="Egypt",
            latitude=27.9158,
            longitude=34.3299,
            source_url=_property_search_url("Sharm El Sheikh Resort Hotel", "Sharm El Sheikh"),
            amenities=["pool", "wifi", "all-inclusive", "diving center", "kids club", "beach"],
            avg_price_usd=180.0,
            star_rating=5.0,
            description=(
                "A world-class all-inclusive 5-star resort in Sharm El Sheikh. "
                "Multiple pools, private beach, PADI certified diving center, full kids club. "
                "All meals and drinks included, incredible coral reef snorkeling. "
                "Ideal for families, divers, and couples seeking a complete beach resort."
            ),
        ),
        PropertyRecord(
            property_id="prop_007",
            name="Dahab Lagoon Dive Camp",
            property_type=PropertyType.HOTEL,
            city="Dahab",
            country="Egypt",
            latitude=28.5097,
            longitude=34.5134,
            source_url=_property_search_url("Dahab Lagoon Dive Camp", "Dahab"),
            amenities=["wifi", "breakfast", "diving center", "beach", "lagoon view"],
            avg_price_usd=75.0,
            star_rating=4.4,
            description=(
                "A relaxed beachside stay near Dahab Lagoon with a diving center, breakfast, "
                "wifi, and easy access to snorkeling spots. Great for solo travelers, divers, "
                "and couples looking for a laid-back Red Sea base."
            ),
        ),
    ]


def _property_search_url(name: str, city: str) -> str:
    query = quote_plus(f"{name}, {city}, Egypt")
    return f"https://www.booking.com/searchresults.html?ss={query}"


def _record_to_search_result(record: PropertyRecord, similarity_score: float = 0.0) -> dict:
    return {
        "property_id": record.property_id,
        "name": record.name,
        "property_type": record.property_type.value,
        "city": record.city.lower(),
        "country": record.country.lower(),
        "latitude": record.latitude,
        "longitude": record.longitude,
        "source_url": record.source_url,
        "amenities": json.dumps(record.amenities),
        "avg_price_usd": record.avg_price_usd or 0.0,
        "star_rating": record.star_rating or 0.0,
        "description": record.description,
        "similarity_score": similarity_score,
    }


def _normalize_city_filter(city_filter: Optional[str]) -> Optional[str]:
    if not city_filter:
        return None
    normalized = re.sub(r"[^a-z\s-]", " ", city_filter.lower())
    normalized = re.sub(r"\begypt\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in CITY_ALIASES:
        return CITY_ALIASES[normalized]
    for alias, city in CITY_ALIASES.items():
        if alias in normalized:
            return city
    return None


def _normalize_property_type_filter(property_type_filter: Optional[str]) -> Optional[str]:
    if not property_type_filter:
        return None
    normalized = re.sub(r"[^a-z\s-]", " ", property_type_filter.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in PROPERTY_TYPE_ALIASES:
        return PROPERTY_TYPE_ALIASES[normalized]
    for alias, property_type in PROPERTY_TYPE_ALIASES.items():
        if alias in normalized:
            return property_type
    return None


def _keyword_search_properties(
    query: str,
    city_filter: Optional[str],
    property_type_filter: Optional[str],
    max_price_filter: Optional[float],
    n_results: int,
) -> list[dict]:
    city_filter = _normalize_city_filter(city_filter)
    property_type_filter = _normalize_property_type_filter(property_type_filter)
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    output = []
    for record in _sample_properties():
        if city_filter and record.city.lower() != city_filter:
            continue
        if property_type_filter and record.property_type.value != property_type_filter:
            continue
        if (
            max_price_filter is not None
            and record.avg_price_usd is not None
            and record.avg_price_usd > max_price_filter
        ):
            continue

        haystack = " ".join([
            record.name,
            record.property_type.value,
            record.city,
            record.country,
            " ".join(record.amenities),
            record.description,
        ]).lower()
        matched_terms = sum(1 for term in terms if term in haystack)
        exact_bonus = 3 if city_filter and record.city.lower() == city_filter else 0
        type_bonus = (
            2
            if property_type_filter and record.property_type.value == property_type_filter
            else 0
        )
        score = matched_terms + exact_bonus + type_bonus
        if score > 0 or city_filter or property_type_filter:
            output.append((score, record))

    output.sort(key=lambda item: (item[0], item[1].star_rating or 0), reverse=True)
    return [
        _record_to_search_result(record, similarity_score=score / max(len(terms), 1))
        for score, record in output[:n_results]
    ]


def _keyword_search_with_relaxation(
    query: str,
    city_filter: Optional[str],
    property_type_filter: Optional[str],
    max_price_filter: Optional[float],
    n_results: int,
) -> list[dict]:
    attempts = [
        (city_filter, property_type_filter, max_price_filter),
        (city_filter, None, max_price_filter),
        (city_filter, property_type_filter, None),
        (city_filter, None, None),
        (None, property_type_filter, max_price_filter),
        (None, property_type_filter, None),
        (None, None, max_price_filter),
        (None, None, None),
    ]
    seen_attempts = set()
    seen_properties = set()
    output = []
    for index, attempt in enumerate(attempts):
        if attempt in seen_attempts:
            continue
        seen_attempts.add(attempt)
        results = _keyword_search_properties(query, *attempt, n_results)
        if index == 0 and len(results) >= min(2, n_results):
            return results
        for result in results:
            property_id = result["property_id"]
            if property_id in seen_properties:
                continue
            seen_properties.add(property_id)
            output.append(result)
            if len(output) >= n_results:
                return output
    return output


def _supplement_with_relaxed_results(
    output: list[dict],
    query: str,
    city_filter: Optional[str],
    property_type_filter: Optional[str],
    max_price_filter: Optional[float],
    n_results: int,
) -> list[dict]:
    if len(output) >= n_results:
        return output

    seen_properties = {result["property_id"] for result in output}
    relaxed_results = _keyword_search_with_relaxation(
        query, city_filter, property_type_filter, max_price_filter, n_results
    )
    for result in relaxed_results:
        property_id = result["property_id"]
        if property_id in seen_properties:
            continue
        output.append(result)
        seen_properties.add(property_id)
        if len(output) >= n_results:
            break
    return output


def _build_where_filter(
    city_filter: Optional[str],
    property_type_filter: Optional[str],
    max_price_filter: Optional[float],
) -> dict:
    clauses = []
    if city_filter:
        clauses.append({"city": {"$eq": city_filter}})
    if property_type_filter:
        clauses.append({"property_type": {"$eq": property_type_filter}})
    if max_price_filter is not None:
        clauses.append({"avg_price_usd": {"$lte": float(max_price_filter)}})
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) > 1:
        return {"$and": clauses}
    return {}


def search_properties(
    query: str,
    city_filter: Optional[str] = None,
    property_type_filter: Optional[str] = None,
    max_price_filter: Optional[float] = None,
    n_results: int = 5,
    prefer_keyword: bool = False,
) -> list[dict]:
    if not query or not query.strip():
        query = "comfortable stay holiday location"

    city_filter = _normalize_city_filter(city_filter)
    property_type_filter = _normalize_property_type_filter(property_type_filter)

    if prefer_keyword or city_filter or property_type_filter or max_price_filter is not None:
        return _keyword_search_with_relaxation(
            query, city_filter, property_type_filter, max_price_filter, n_results
        )

    collection = get_collection()
    try:
        model = get_embedding_model()
        query_embedding = model.encode(query).tolist()
    except Exception as exc:
        print(f"[Database] Embedding search unavailable; using keyword fallback: {exc}")
        return _keyword_search_with_relaxation(
            query, city_filter, property_type_filter, max_price_filter, n_results
        )

    where_filter = _build_where_filter(city_filter, property_type_filter, max_price_filter)

    search_kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        search_kwargs["where"] = where_filter

    try:
        results = collection.query(**search_kwargs)
    except Exception as exc:
        print(f"[Database] Chroma query failed; using keyword fallback: {exc}")
        return _keyword_search_with_relaxation(
            query, city_filter, property_type_filter, max_price_filter, n_results
        )

    output = []
    if results and results["metadatas"]:
        for i, metadata in enumerate(results["metadatas"][0]):
            metadata["description"] = results["documents"][0][i]
            metadata["similarity_score"] = 1 - results["distances"][0][i]
            output.append(metadata)
    if not output:
        return _keyword_search_with_relaxation(
            query, city_filter, property_type_filter, max_price_filter, n_results
        )
    return _supplement_with_relaxed_results(
        output, query, city_filter, property_type_filter, max_price_filter, n_results
    )


def get_collection_count() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0


def seed_sample_data() -> None:
    samples = _sample_properties()
    print(f"[Database] Seeding {len(samples)} sample properties...")
    for record in samples:
        add_property(record)
    print(f"[Database] Done. Collection has {get_collection_count()} properties.")
