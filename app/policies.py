"""Base de conocimiento de politicas (RAG simple por tema en Etapa 1)."""
from __future__ import annotations

from pathlib import Path

from app.catalog import tokenize

TOPIC_KEYWORDS = {
    "envios": ["envio", "envios", "enviar", "llega", "demora", "transportadora", "guia", "domicilio", "ciudad"],
    "cambios_y_devoluciones": ["cambio", "cambiar", "devolucion", "devolver", "talla equivocada", "no me quedo"],
    "garantia": ["garantia", "defecto", "despego", "desprendio", "roto", "costura", "danado"],
    "medios_de_pago": ["pago", "pagar", "tarjeta", "pse", "contraentrega", "efectivo", "credito"],
}


class PolicyStore:
    def __init__(self, directory: Path):
        self.docs = {p.stem: p.read_text(encoding="utf-8") for p in Path(directory).glob("*.md")}

    def topics(self) -> list[str]:
        return sorted(self.docs)

    def get(self, tema: str) -> dict:
        tema_norm = tema.strip().lower().replace(" ", "_")
        if tema_norm in self.docs:
            return self._payload(tema_norm)
        toks = set(tokenize(tema))
        best, best_score = None, 0
        for topic, words in TOPIC_KEYWORDS.items():
            score = sum(1 for w in words if set(tokenize(w)) <= toks)
            if score > best_score:
                best, best_score = topic, score
        if best and best in self.docs:
            return self._payload(best)
        return {"encontrado": False, "temas_disponibles": self.topics()}

    def _payload(self, topic: str) -> dict:
        text = self.docs[topic]
        return {"encontrado": True, "tema": topic, "placeholder": "PLACEHOLDER" in text,
                "contenido": text.replace("<!-- PLACEHOLDER: reemplazar con la politica real de Tony2 -->", "").strip()}
