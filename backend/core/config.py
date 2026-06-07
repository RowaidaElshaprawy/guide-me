from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_name: str = "Travel Agent Bot"
    app_env: str = "development"
    debug: bool = True

    # FastAPI
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Gemini — free tier: 15 rpm, 1M tokens/day
    gemini_api_key: str
    gemini_model: str = "gemini-1.5-flash"

    # ChromaDB — fully local
    chroma_persist_directory: str = "./data/chromadb"
    chroma_collection_name: str = "travel_properties"

    # Sentence Transformers — fully local embedding model
    embedding_model: str = "all-MiniLM-L6-v2"

    # Ollama — fully local
    ollama_base_url: str = "http://localhost:11434"
    ollama_cleaner_model: str = "phi3:mini"
    ollama_reviewer_model: str = "phi3:mini"

    # Free geocoding & routing — no API key needed
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    osrm_base_url: str = "https://router.project-osrm.org"

    # Streamlit -> FastAPI
    api_base_url: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()