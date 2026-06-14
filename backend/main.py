from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core import database
from backend.agents.orchestrator import Orchestrator
from backend.api.chat_router import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[{settings.app_name}] Starting up...")

    count = database.get_collection_count()
    if count == 0:
        print("[Startup] Empty database — seeding sample data...")
        database.seed_sample_data()
    else:
        print(f"[Startup] Database has {count} properties.")

    print("[Startup] Initializing Orchestrator...")
    app.state.orchestrator = Orchestrator(settings)
    print("[Startup] All systems ready.")

    yield

    print(f"[{settings.app_name}] Shutdown.")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")


@app.get("/health")
async def health_check():
    count = database.get_collection_count()
    return {"status": "ok", "env": settings.app_env, "properties_in_db": count}