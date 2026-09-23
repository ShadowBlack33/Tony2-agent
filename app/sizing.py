"""Recomendador de talla basado en la medida real de cada horma (no en tallas de otras marcas)."""
from __future__ import annotations

from typing import Any


def recommend_size(horma: dict[str, Any], foot_length_cm: float, allowance_cm: float = 0.5,
                   stock: dict[str, int] | None = None) -> dict[str, Any]:
    """Devuelve la talla mas pequena cuya plantilla >= pie + holgura.

    horma: {"tallas": {"40": 26.4, ...}, "placeholder": bool}
    stock: opcional {"40": 3, ...} para indicar disponibilidad.
    """
    if not 10 <= foot_length_cm <= 35:
        return {"ok": False, "motivo": "medida_fuera_de_rango",
                "detalle": "El largo del pie debe estar entre 10 y 35 cm. Verifica la medida."}

    tallas = sorted(((t, float(cm)) for t, cm in horma["tallas"].items()), key=lambda x: x[1])
    target = foot_length_cm + allowance_cm
    for i, (talla, cm) in enumerate(tallas):
        if cm >= target:
            margen = round(cm - foot_length_cm, 1)
            alternativa = tallas[i - 1][0] if i > 0 and (tallas[i - 1][1] - foot_length_cm) >= 0.2 else None
            result = {"ok": True, "talla": talla, "largo_plantilla_cm": cm, "margen_cm": margen,
                      "alternativa_ajustada": alternativa, "horma_placeholder": bool(horma.get("placeholder"))}
            if stock is not None:
                result["disponible"] = stock.get(talla, 0) > 0
                if not result["disponible"]:
                    result["tallas_disponibles"] = [t for t, q in stock.items() if q > 0]
            return result
    return {"ok": False, "motivo": "fuera_de_horma",
            "detalle": f"No hay talla para un pie de {foot_length_cm} cm en esta horma.",
            "talla_maxima": tallas[-1][0]}
