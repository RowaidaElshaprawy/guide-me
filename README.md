# Guide Me - Egypt Travel Agent Bot

Guide Me is a Streamlit + FastAPI travel assistant for discovering stays in Egypt. It combines a small property database, hybrid search, optional LLM intent parsing, reviewer validation, Booking.com links, and a booking-assistant flow.

## Features

- Chat-based property search for Cairo, Luxor, Hurghada, Sharm El Sheikh, Siwa, and Dahab.
- Recommendations for hotels, apartments, chalets, and villas.
- Budget filtering, amenity-aware keyword matching, and related alternatives when exact matches are limited.
- Exact Booking.com property links when a verified detail URL is known.
- Optional live price/availability hydration using Scrapling.
- Booking assistant that extracts dates, guests, rooms, and selected listing.
- Distance queries using Nominatim and OSRM when the user asks for routes or distance.

## Tech Stack

- Frontend: Streamlit
- Backend: FastAPI
- Data store: ChromaDB
- Embeddings: sentence-transformers
- LLM providers: Gemini with Groq fallback
- Scraping: Scrapling
- Package manager: uv

## Project Structure

```text
backend/
  agents/          Intent parsing, search orchestration, review, booking logic
  api/             FastAPI chat route
  core/            Settings, schemas, ChromaDB helpers, seed data
  scrapers/        Live hydration and HTML compression
frontend/
  app.py           Streamlit chat UI
  components/      Property card rendering
data/
  chromadb/        Local ChromaDB persistence
resources/
  logo.png         Optional UI logo
```

## Requirements

- Python 3.11+
- uv
- A Gemini API key in `.env`
- Optional Groq API key for fallback

## Environment

Create a `.env` file in the project root:

```env
APP_NAME="Guide Me"
APP_ENV=development
DEBUG=true

GEMINI_API_KEY=your_gemini_key_here
GEMINI_MODEL=gemini-1.5-flash

GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

API_HOST=127.0.0.1
API_PORT=8000
API_BASE_URL=http://127.0.0.1:8000

CHROMA_PERSIST_DIRECTORY=./data/chromadb
CHROMA_COLLECTION_NAME=travel_properties
EMBEDDING_MODEL=all-MiniLM-L6-v2

NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
OSRM_BASE_URL=https://router.project-osrm.org
```

## Install

```bash
uv sync
```

If you need development tools:

```bash
uv sync --extra dev
```

## Run

Start the backend:

```bash
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```bash
uv run streamlit run frontend/app.py
```

Open the Streamlit URL shown in the terminal, usually:

```text
http://localhost:8501
```

## Example Prompts

- Find me a hotel in Cairo
- Cheap apartments in Luxor under 70
- Beach villa in Hurghada with pool
- Show chalets in Siwa
- How far is Siwa from Cairo?
- Show current prices for hotels in Sharm
- I want to book the first one, check-in July 10 check-out July 15 for 2 guests

## How Search Works

1. The chat request goes to FastAPI at `/api/chat`.
2. `GeminiSearcher` extracts intent. Common city/type/budget searches use a fast local parser to reduce latency.
3. `database.search_properties` searches local seeded records. Filtered searches use the keyword path first; broad semantic searches can use ChromaDB embeddings.
4. `ReviewerAgent` checks budget and availability signals, then labels exact matches and related alternatives honestly.
5. The frontend renders result cards with price, amenities, status, and `View Property` links.

## Accuracy Notes

The app uses a small sample dataset, so exact recommendations are limited. When the database has only one exact match, the assistant may include related alternatives and now labels them as alternatives instead of pretending they are exact matches.

Live prices and availability depend on third-party pages. If scraping is blocked or the page structure changes, the app falls back to stored database estimates.

## Reset Seed Data

The backend seeds sample data automatically when ChromaDB is empty. To force a fresh seed, stop the app and clear the ChromaDB data directory, then restart the backend.

## Verification

Useful local checks:

```bash
uv run ruff check backend frontend
python -m py_compile backend/core/database.py backend/agents/gemini_searcher.py backend/agents/reviewer.py
```

If `ruff` is not installed, run:

```bash
uv sync --extra dev
```
