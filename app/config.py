"""Configuracion central leida de variables de entorno (.env)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


@dataclass(frozen=True)
class Settings:
    fast_model: str = os.getenv("LLM_FAST_MODEL", "gemini/gemini-3.5-flash-lite")
    smart_model: str = os.getenv("LLM_SMART_MODEL", "gemini/gemini-3.8-flash")
    llm_temperature: str = os.getenv("LLM_TEMPERATURE", "")
    llm_reasoning_effort: str = os.getenv("LLM_REASONING_EFFORT", "low")
    size_allowance_cm: float = float(os.getenv("SIZE_ALLOWANCE_CM", "0.5"))
    agent_max_steps: int = int(os.getenv("AGENT_MAX_STEPS", "6"))
    store_path: str = os.getenv("STORE_PATH", "./tony2_store.sqlite")
    # Vacio = busqueda solo lexica. Ej: gemini/gemini-embedding-001
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "")
    search_min_similarity: float = float(os.getenv("SEARCH_MIN_SIMILARITY", "0.61"))
    embedding_cache_path: Path = Path(os.getenv("EMBEDDING_CACHE_PATH", "./embeddings_cache.json"))
    catalog_path: Path = DATA_DIR / "catalog_seed.json"
    policies_dir: Path = DATA_DIR / "policies"
    system_prompt_path: Path = BASE_DIR / "prompts" / "system.md"


settings = Settings()
