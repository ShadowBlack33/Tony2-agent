# Tony2 Agent — Etapa 1

Agente conversacional de ventas para Deportes Tony 2 S.A.S. Arquitectura y decisiones en el doc
"Plan de Reactivación Tony2" (pestañas *Asistente IA* y *Modelo de Datos*).

> **Catálogo, hormas y políticas son PLACEHOLDER.** Todo lo marcado `placeholder: true` o
> `<!-- PLACEHOLDER -->` debe reemplazarse con datos reales antes de exponer el agente a clientes.

## Qué incluye

| Módulo | Qué hace |
| --- | --- |
| `app/catalog.py` | Catálogo en memoria, búsqueda **híbrida** (BM25 + embeddings, fusión RRF) + filtros duros (categoría, superficie, color, precio, talla), sinónimos colombianos, paginación, bandera `coincidencia_baja`. Si no hay embeddings, cae a búsqueda léxica |
| `app/embeddings.py` | Embeddings vía LiteLLM (ej. Gemini) con caché en disco (catálogo) y LRU (consultas) |
| `app/sizing.py` | Talla por largo de pie en cm contra la tabla de cada horma, con holgura configurable y stock |
| `app/tools.py` | 7 herramientas con esquema OpenAI/LiteLLM: search, get, compare, recommend_size, get_policy, handoff, log_unmet_demand |
| `app/agent.py` | Loop LLM ↔ herramientas, enrutamiento rápido/capaz, corrección automática y fallback a humano |
| `app/guardrails.py` | Bloquea precios y SKUs que no salieron de una herramienta en el turno |
| `app/llm.py` | Capa agnóstica (LiteLLM): Claude, GPT, Gemini… cambiando solo `.env`. `FakeLLM` para tests |
| `app/main.py` | API FastAPI: `POST /chat`, `GET /health` |
| `app/cli.py` | Chat en terminal con costo y latencia por turno |
| `app/store.py` | SQLite local: mensajes, tool calls, handoffs, demanda no cubierta |
| `evals/` | Golden set (25 casos, 6 categorías) + runner comparativo multi-modelo con reporte Markdown |
| `db/schema.sql` | Esquema PostgreSQL destino (validado en PG16 + pgvector) |
| `scripts/probe_search.py` | Prueba búsquedas sin LLM y muestra similitudes para calibrar el umbral |
| `tests/` | 24 tests (tallaje, búsqueda léxica e híbrida, caché, fallback, guardrails, loop del agente, API) |

## Correr

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # poner al menos una API key
pytest -q                       # no requiere API key
python -m app.cli               # chat en terminal
uvicorn app.main:app --reload   # API en http://localhost:8000/docs
```

## Búsqueda semántica (embeddings)

En `.env`:

```dotenv
EMBEDDING_MODEL=gemini/gemini-embedding-001
```

- La primera ejecución embebe el catálogo y lo guarda en `embeddings_cache.json`; solo se recalcula si cambia un producto.
- Cada búsqueda del cliente cuesta una llamada de embedding (con caché para consultas repetidas).
- Calibrar el umbral de `coincidencia_baja`: `python -m scripts.probe_search "algo rapido para sintetica" "camisetas del america"`
  y ajustar `SEARCH_MIN_SIMILARITY` al valor que separe lo que sí existe de lo que no.
- `gemini-embedding-2-preview` (multimodal: texto + imágenes) es el candidato para búsqueda por foto en Etapa 2;
  al ser preview, se prueba antes de adoptarlo.

## Comparar modelos

```bash
python -m evals.run_evals --check
python -m evals.run_evals --models gemini/gemini-3.5-flash-lite gemini/gemini-3.8-flash
```

Genera `evals/reports/<fecha>.md` con acierto por caso, costo y latencia. Los chequeos son reglas
mínimas; revisar a mano una muestra de respuestas (tono, naturalidad) antes de decidir.

## Pendiente para Etapa 1 completa

- [ ] Reemplazar `app/data/catalog_seed.json` con el catálogo real (loader desde los Excel → PostgreSQL).
- [ ] Medir `horma_talla` real (cm de plantilla por talla y horma).
- [ ] Políticas reales en `app/data/policies/`.
- [x] Búsqueda híbrida con embeddings (en memoria).
- [ ] Mover vectores a PostgreSQL + pgvector con la misma interfaz de `CatalogRepository`.
- [ ] Calibrar `SEARCH_MIN_SIMILARITY` con el modelo de embeddings real.
- [ ] Ampliar golden set a ≥100 casos con chats reales anonimizados.
- [ ] Widget web para tony2.store.

## Etapa 2 (siguiente)

Webhook de WhatsApp Cloud API (verificación + firma), stock y pedidos vía Tiendanube, link de pago,
visión y audio, perfiles con consentimiento y cifrado de PII.
