"""Validador post-respuesta: bloquea precios, SKUs o tallas que no provengan de herramientas del turno."""
from __future__ import annotations

import json
import re
from typing import Any

PRICE_RE = re.compile(r"(?:\$|cop\s*)?\s*(\d{1,3}(?:[.,]\d{3})+|\d{5,7})(?!\s*(?:cm|mm))", re.IGNORECASE)
SKU_RE = re.compile(r"\b[A-Z0-9]{2,4}-[A-Z]{3}-[A-Z0-9]{2,3}\b")
SIZE_NUM_RE = re.compile(r"talla\s*\*?\s*\d{2}", re.IGNORECASE)
SIZE_CLAIM_RE = re.compile(r"recom[ie]nd|sugier|ideal|te queda|te va|tu talla|pide", re.IGNORECASE)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def collect_allowed(tool_outputs: list[Any]) -> tuple[set[str], set[str]]:
    blob = json.dumps(tool_outputs, ensure_ascii=False)
    numbers = {_digits(m) for m in re.findall(r"\d[\d.,]*", blob) if len(_digits(m)) >= 4}
    skus = set(SKU_RE.findall(blob))
    return numbers, skus


def validate_reply(reply: str, tool_outputs: list[Any], tools_called: list[str] | None = None) -> list[str]:
    """Devuelve lista de violaciones (vacia = respuesta valida)."""
    allowed_numbers, allowed_skus = collect_allowed(tool_outputs)
    violations = []
    for m in PRICE_RE.finditer(reply):
        d = _digits(m.group(1))
        if int(d) >= 10000 and d not in allowed_numbers:
            violations.append(f"precio_no_verificado:{m.group(0).strip()}")
    for sku in SKU_RE.findall(reply):
        if sku not in allowed_skus:
            violations.append(f"sku_no_verificado:{sku}")
    if tools_called is not None and "recommend_size" not in tools_called:
        for sentence in re.split(r"[.!?\n]", reply):
            if SIZE_NUM_RE.search(sentence) and SIZE_CLAIM_RE.search(sentence):
                violations.append("talla_no_verificada: recomienda talla sin llamar recommend_size en este turno")
                break
    return violations