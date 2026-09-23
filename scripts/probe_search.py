"""Prueba la busqueda sin pasar por el LLM, para calibrar SEARCH_MIN_SIMILARITY.

Uso: python -m scripts.probe_search "algo rapido para sintetica" "camisetas del america"
Muestra modo, similitud semantica por producto y la bandera coincidencia_baja.
"""
import sys

from app.catalog import CatalogRepository
from app.config import settings
from app.factory import build_embedder


def main(queries: list[str]) -> None:
    cat = CatalogRepository(settings.catalog_path, build_embedder(), settings.search_min_similarity)
    print(f"Modo: {cat.search_mode} | umbral: {settings.search_min_similarity}\n")
    for q in queries:
        r = cat.search(q, page_size=5)
        sims = cat._semantic_scores(q)
        top = sorted(sims.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"> {q}\n  coincidencia_baja={r['coincidencia_baja']}  filtros={r['filtros_aplicados']}")
        print("  resultados:", [x["nombre"] + " " + x["suela"] for x in r["resultados"]])
        if top:
            print("  similitud:", [(cat.products[p].nombre, round(s, 3)) for p, s in top])
        print()


if __name__ == "__main__":
    main(sys.argv[1:] or ["algo rapido para sintetica", "guantes que agarren con lluvia", "camisetas del america"])
