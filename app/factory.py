"""Construye el agente con la configuracion del entorno."""
from __future__ import annotations

from app.agent import Agent
from app.catalog import CatalogRepository
from app.config import settings
from app.embeddings import CachedEmbedder, LiteLLMEmbedder
from app.llm import LLMClient, LiteLLMClient
from app.policies import PolicyStore
from app.store import Store
from app.tools import ToolExecutor


def build_embedder(model: str | None = None):
    model = settings.embedding_model if model is None else model
    if not model:
        return None
    return CachedEmbedder(LiteLLMEmbedder(model), settings.embedding_cache_path)


def build_agent(llm: LLMClient | None = None, fast_model: str | None = None, smart_model: str | None = None,
                store_path: str | None = None, embedder=None, use_env_embedder: bool = True) -> Agent:
    if embedder is None and use_env_embedder:
        embedder = build_embedder()
    catalog = CatalogRepository(settings.catalog_path, embedder=embedder,
                                min_similarity=settings.search_min_similarity)
    policies = PolicyStore(settings.policies_dir)
    store = Store(store_path or settings.store_path)
    tools = ToolExecutor(catalog, policies, store, settings.size_allowance_cm)
    if llm is None:
        llm = LiteLLMClient(temperature=float(settings.llm_temperature) if settings.llm_temperature else None,
                            reasoning_effort=settings.llm_reasoning_effort or None)
    return Agent(llm=llm, tools=tools,
                 system_prompt=settings.system_prompt_path.read_text(encoding="utf-8"),
                 fast_model=fast_model or settings.fast_model, smart_model=smart_model or settings.smart_model,
                 max_steps=settings.agent_max_steps)
