from app.catalog import CatalogRepository
from app.config import settings

cat = CatalogRepository(settings.catalog_path)


def test_infers_surface_and_category():
    r = cat.search("guayos para cancha sintetica")
    assert r["filtros_aplicados"]["superficie"] == "TF"
    assert all(x["suela"] == "TF" and x["categoria"] == "guayo" for x in r["resultados"])


def test_goalkeeper_gloves():
    r = cat.search("tienen guantes de portero?")
    assert r["total"] >= 2 and all(x["categoria"] == "guante" for x in r["resultados"])


def test_pagination():
    p1 = cat.search("guayo", categoria="guayo", page=1)
    p2 = cat.search("guayo", categoria="guayo", page=2)
    assert p1["hay_mas"] and {x["sku"] for x in p1["resultados"]}.isdisjoint({x["sku"] for x in p2["resultados"]})


def test_size_filter_excludes_out_of_stock():
    r = cat.search("speed", categoria="guayo", superficie="TF", talla="42")
    assert all(x["sku"] != "T2S-VER-TF" for x in r["resultados"])


def test_futsal():
    r = cat.search("algo para microfutbol")
    assert r["resultados"] and r["resultados"][0]["suela"] == "IC"
