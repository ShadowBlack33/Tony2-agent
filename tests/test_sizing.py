from app.sizing import recommend_size

HORMA = {"placeholder": True, "tallas": {"39": 25.7, "40": 26.4, "41": 27.0, "42": 27.7}}


def test_picks_smallest_fitting_size():
    r = recommend_size(HORMA, 26.0, allowance_cm=0.5)
    assert r["ok"] and r["talla"] == "41"


def test_exact_fit_with_allowance():
    r = recommend_size(HORMA, 25.9, allowance_cm=0.5)
    assert r["talla"] == "40"


def test_reports_stock():
    r = recommend_size(HORMA, 26.0, 0.5, stock={"41": 0, "42": 2})
    assert r["disponible"] is False and r["tallas_disponibles"] == ["42"]


def test_out_of_range():
    assert recommend_size(HORMA, 50, 0.5)["motivo"] == "medida_fuera_de_rango"
    assert recommend_size(HORMA, 28.0, 0.5)["motivo"] == "fuera_de_horma"
