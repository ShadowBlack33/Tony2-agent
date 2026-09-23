import numpy as np
import pytest

from app.catalog import CatalogRepository
from app.config import settings
from app.embeddings import CachedEmbedder


class KeywordStub:
    """Asigna vectores segun palabras clave: simula un embedding semantico sin API."""
    model = "stub"

    def __init__(self):
        self.calls = 0
        self.rules = [("t2 speed", [1, 0, 0, 0]), ("t2 vertex", [0.9, 0.1, 0, 0]), ("aureon", [0, 0, 1, 0]),
                      ("vuele", [1, 0, 0, 0]), ("comodo para jugar", [0, 0, 1, 0]),
                      ("camiseta", [0, 0, 0, 1])]  # concepto ajeno al catalogo

    def embed(self, texts):
        self.calls += 1
        rows = []
        for t in texts:
            vec = next((v for k, v in self.rules if k in t.lower()), [0, 1, 0, 0])
            rows.append(vec)
        m = np.asarray(rows, dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)


class Broken:
    model = "broken"

    def embed(self, texts):
        raise ConnectionError("sin red")


def repo(inner, tmp_path, **kw):
    return CatalogRepository(settings.catalog_path, CachedEmbedder(inner, tmp_path / "c.json"), **kw)


def test_semantic_match_without_shared_words(tmp_path):
    cat = repo(KeywordStub(), tmp_path)
    r = cat.search("algo que vuele", categoria="guayo")
    assert r["modo_busqueda"] == "hibrida"
    assert r["resultados"][0]["nombre"] == "T2 Speed"


def test_hybrid_still_respects_filters(tmp_path):
    cat = repo(KeywordStub(), tmp_path)
    r = cat.search("comodo para jugar", superficie="TF")
    assert all(x["suela"] == "TF" for x in r["resultados"])  # Aureon es FG: no puede aparecer


def test_falls_back_to_lexical_when_embeddings_fail(tmp_path):
    cat = repo(Broken(), tmp_path)
    r = cat.search("guantes de portero")
    assert r["modo_busqueda"] == "lexica" and r["resultados"][0]["categoria"] == "guante"


def test_low_match_flag(tmp_path):
    cat = repo(KeywordStub(), tmp_path)
    assert cat.search("camisetas del america")["coincidencia_baja"] is True
    assert cat.search("guantes")["coincidencia_baja"] is False


def test_document_cache_avoids_reembedding(tmp_path):
    inner = KeywordStub()
    repo(inner, tmp_path)
    first = inner.calls
    inner2 = KeywordStub()
    repo(inner2, tmp_path)          # mismo archivo de cache
    assert first == 1 and inner2.calls == 0


def test_query_cache(tmp_path):
    inner = KeywordStub()
    cat = repo(inner, tmp_path)
    before = inner.calls
    cat.search("algo que vuele")
    cat.search("algo que vuele")
    assert inner.calls == before + 1
