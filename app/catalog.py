"""Catalogo en memoria con busqueda lexica + filtros.

Etapa 1: se carga desde JSON. En Etapa 2 se reemplaza por PostgreSQL + pgvector
manteniendo la misma interfaz (CatalogRepository), asi las herramientas no cambian.
"""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)
RRF_K = 60  # constante estandar de Reciprocal Rank Fusion

SURFACE_SYNONYMS = {
    "FG": ["grama", "natural", "pasto", "cesped", "fg", "tacos"],
    "TF": ["sintetica", "sintetico", "turf", "tf", "grama sintetica", "multitaco", "torretin"],
    "AG": ["artificial", "ag"],
    "IC": ["futsal", "sala", "microfutbol", "micro", "indoor", "coliseo", "ic"],
}

CATEGORY_SYNONYMS = {
    "guayo": ["guayo", "guayos", "botin", "botines", "zapato", "tenis", "chuteador", "chuteadores"],
    "guante": ["guante", "guantes", "portero", "arquero", "golero"],
    "balon": ["balon", "balones", "pelota"],
    "media": ["media", "medias", "calcetas", "antideslizante", "antideslizantes"],
    "canillera": ["canillera", "canilleras", "espinillera", "espinilleras"],
}

STOPWORDS = {"de", "la", "el", "los", "las", "un", "una", "unos", "unas", "para", "con", "que", "y", "o",
             "en", "me", "mi", "tienen", "tiene", "hay", "quiero", "busco", "algo", "por", "favor", "del", "al"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9/ ]+", " ", text)


def tokenize(text: str) -> list[str]:
    return [t for t in normalize(text).split() if t and t not in STOPWORDS]


@dataclass
class Variant:
    sku: str
    product_id: str
    color: str
    suela: str
    precio: int
    tallas_stock: dict[str, int]

    @property
    def tallas_disponibles(self) -> list[str]:
        return [t for t, q in self.tallas_stock.items() if q > 0]


@dataclass
class Product:
    id: str
    nombre: str
    linea: str
    categoria: str
    segmento: str
    material: str
    concepto: str
    horma: str | None
    origen: str
    descripcion: str
    placeholder: bool
    variantes: list[Variant]

    def search_text(self) -> str:
        suelas = " ".join(v.suela for v in self.variantes)
        colores = " ".join(v.color for v in self.variantes)
        return " ".join([self.nombre, self.linea, self.categoria, self.segmento, self.material,
                         self.concepto, self.descripcion, suelas, colores])


class CatalogRepository:
    def __init__(self, path: Path, embedder=None, min_similarity: float = 0.5):
        """embedder: CachedEmbedder opcional. Sin embedder (o si falla) la busqueda es solo lexica."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.hormas: dict[str, dict[str, Any]] = raw["hormas"]
        self.products: dict[str, Product] = {}
        self.variants: dict[str, Variant] = {}
        for p in raw["productos"]:
            variants = [Variant(sku=v["sku"], product_id=p["id"], color=v["color"], suela=v["suela"],
                                precio=int(v["precio"]), tallas_stock=v["tallas_stock"]) for v in p["variantes"]]
            prod = Product(id=p["id"], nombre=p["nombre"], linea=p["linea"], categoria=p["categoria"],
                           segmento=p["segmento"], material=p["material"], concepto=p["concepto"],
                           horma=p.get("horma"), origen=p["origen"], descripcion=p["descripcion"],
                           placeholder=bool(p.get("placeholder", False)), variantes=variants)
            self.products[prod.id] = prod
            for v in variants:
                self.variants[v.sku] = v
        self._build_index()
        self.embedder, self.min_similarity = embedder, min_similarity
        self._pids = list(self.products)
        self._vectors: np.ndarray | None = None
        if embedder is not None:
            try:
                self._vectors = embedder.embed_documents([self.products[pid].search_text() for pid in self._pids])
            except Exception as e:  # sin red / sin key: se degrada a lexica
                log.warning("Embeddings no disponibles (%s); busqueda solo lexica.", e)

    @property
    def search_mode(self) -> str:
        return "hibrida" if self._vectors is not None else "lexica"

    def _semantic_scores(self, query: str) -> dict[str, float]:
        if self._vectors is None or not query.strip():
            return {}
        try:
            q = self.embedder.embed_query(query)
        except Exception as e:
            log.warning("Fallo embedding de consulta (%s); se usa solo lexica.", e)
            return {}
        sims = self._vectors @ q
        return {pid: float(s) for pid, s in zip(self._pids, sims)}

    # --- indice lexico (BM25 simple) ---
    def _build_index(self) -> None:
        self._docs = {pid: tokenize(p.search_text()) for pid, p in self.products.items()}
        n = len(self._docs)
        df: dict[str, int] = {}
        for toks in self._docs.values():
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._avgdl = sum(len(t) for t in self._docs.values()) / max(n, 1)

    def _bm25(self, query_tokens: list[str], pid: str, k1: float = 1.4, b: float = 0.75) -> float:
        toks = self._docs[pid]
        score = 0.0
        for q in query_tokens:
            tf = toks.count(q)
            if tf == 0:
                continue
            idf = self._idf.get(q, 0.0)
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(toks) / self._avgdl))
        return score

    @staticmethod
    def infer_filters(query: str) -> dict[str, str]:
        """Detecta superficie y categoria mencionadas en texto libre."""
        q = f" {normalize(query)} "
        inferred: dict[str, str] = {}
        for code, words in SURFACE_SYNONYMS.items():
            if any(f" {w} " in q for w in words):
                inferred["superficie"] = code
                break
        for cat, words in CATEGORY_SYNONYMS.items():
            if any(f" {w} " in q for w in words):
                inferred["categoria"] = cat
                break
        return inferred

    def search(self, query: str = "", categoria: str | None = None, superficie: str | None = None,
               color: str | None = None, precio_max: int | None = None, segmento: str | None = None,
               talla: str | None = None, page: int = 1, page_size: int = 3) -> dict[str, Any]:
        inferred = self.infer_filters(query)
        categoria = categoria or inferred.get("categoria")
        superficie = (superficie or inferred.get("superficie") or "").upper() or None
        qtoks = tokenize(query)

        candidates: list[tuple[Product, Variant]] = []
        for pid, p in self.products.items():
            if categoria and p.categoria != categoria:
                continue
            if segmento and p.segmento != segmento:
                continue
            for v in p.variantes:
                if superficie and v.suela != superficie:
                    continue
                if color and normalize(color) not in normalize(v.color):
                    continue
                if precio_max and v.precio > precio_max:
                    continue
                if talla and v.tallas_stock.get(str(talla), 0) <= 0:
                    continue
                candidates.append((p, v))

        cand_pids = list(dict.fromkeys(p.id for p, _ in candidates))
        lex = {pid: self._bm25(qtoks, pid) for pid in cand_pids} if qtoks else {}
        sem_all = self._semantic_scores(query)
        sem = {pid: sem_all[pid] for pid in cand_pids if pid in sem_all}

        # Reciprocal Rank Fusion entre ranking lexico y semantico
        fused: dict[str, float] = {pid: 0.0 for pid in cand_pids}
        for ranking in (lex, sem):
            ordered = sorted((pid for pid in ranking if ranking[pid] > 0 or ranking is sem),
                             key=lambda x: ranking[x], reverse=True)
            for rank, pid in enumerate(ordered):
                fused[pid] += 1.0 / (RRF_K + rank + 1)

        results = [(fused[p.id] + 1e-7 * sum(v.tallas_stock.values()), p, v) for p, v in candidates]
        best_lex = max(lex.values(), default=0.0)
        best_sem = max(sem.values(), default=None)
        low_match = bool(qtoks) and best_lex == 0 and (best_sem is None or best_sem < self.min_similarity) \
            and not (categoria or superficie)
        results.sort(key=lambda r: r[0], reverse=True)
        start = (page - 1) * page_size
        page_items = results[start:start + page_size]
        return {
            "filtros_aplicados": {"categoria": categoria, "superficie": superficie, "color": color,
                                  "precio_max": precio_max, "segmento": segmento, "talla": talla},
            "modo_busqueda": self.search_mode,
            "coincidencia_baja": low_match,
            "total": len(results),
            "pagina": page,
            "hay_mas": start + page_size < len(results),
            "resultados": [self.variant_card(p, v) for _, p, v in page_items],
        }

    def variant_card(self, p: Product, v: Variant) -> dict[str, Any]:
        return {
            "sku": v.sku, "nombre": p.nombre, "linea": p.linea, "categoria": p.categoria,
            "concepto": p.concepto, "material": p.material, "color": v.color, "suela": v.suela,
            "precio_cop": v.precio, "tallas_disponibles": v.tallas_disponibles,
            "placeholder": p.placeholder,
        }

    def get_product(self, sku: str) -> dict[str, Any] | None:
        v = self.variants.get(sku)
        if not v:
            return None
        p = self.products[v.product_id]
        card = self.variant_card(p, v)
        card.update({"descripcion": p.descripcion, "origen": p.origen, "horma": p.horma,
                     "otras_variantes": [x.sku for x in p.variantes if x.sku != sku]})
        return card
