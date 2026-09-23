"""Herramientas del agente: esquemas (formato OpenAI/LiteLLM) + ejecucion.

Regla central: precios, stock, tallas y politicas SOLO salen de estas herramientas.
"""
from __future__ import annotations

from typing import Any, Callable

from app.catalog import CatalogRepository
from app.policies import PolicyStore
from app.sizing import recommend_size
from app.store import Store

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "search_products",
        "description": "Busca productos de Tony2 (guayos, guantes, balones, medias, canilleras). Usala para cualquier "
                       "pregunta sobre que hay disponible, precios u opciones. Soporta paginacion para 'muestrame mas'.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Lo que busca el cliente en texto libre"},
            "categoria": {"type": "string", "enum": ["guayo", "guante", "balon", "media", "canillera"]},
            "superficie": {"type": "string", "enum": ["FG", "TF", "AG", "IC"],
                           "description": "FG grama natural, TF/AG sintetica, IC futsal"},
            "color": {"type": "string"},
            "precio_max": {"type": "integer", "description": "Precio maximo en COP"},
            "segmento": {"type": "string", "enum": ["adulto", "nino"]},
            "talla": {"type": "string", "description": "Solo variantes con esta talla en stock"},
            "page": {"type": "integer", "minimum": 1, "default": 1}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_product",
        "description": "Ficha completa de un producto por SKU (descripcion, origen, tallas, otras variantes).",
        "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]}}},
    {"type": "function", "function": {
        "name": "compare_products",
        "description": "Compara 2 a 4 productos por SKU.",
        "parameters": {"type": "object", "properties": {
            "skus": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4}},
            "required": ["skus"]}}},
    {"type": "function", "function": {
        "name": "recommend_size",
        "description": "Recomienda talla para un producto a partir del largo del pie en cm (talon a dedo mas largo). "
                       "Nunca recomiendes talla sin esta herramienta ni a partir de tallas de otras marcas.",
        "parameters": {"type": "object", "properties": {
            "sku": {"type": "string"},
            "largo_pie_cm": {"type": "number"}},
            "required": ["sku", "largo_pie_cm"]}}},
    {"type": "function", "function": {
        "name": "get_policy",
        "description": "Consulta politicas de Tony2: envios, cambios_y_devoluciones, garantia, medios_de_pago.",
        "parameters": {"type": "object", "properties": {"tema": {"type": "string"}}, "required": ["tema"]}}},
    {"type": "function", "function": {
        "name": "handoff_to_human",
        "description": "Pasa la conversacion a una persona del equipo. Usala si el cliente lo pide, hay un reclamo, "
                       "una garantia, un pedido mayorista, o no puedes resolver tras varios intentos.",
        "parameters": {"type": "object", "properties": {
            "resumen": {"type": "string", "description": "Que quiere el cliente, en 1-3 frases"},
            "motivo": {"type": "string", "enum": ["solicitud_cliente", "reclamo", "garantia", "mayorista",
                                                  "no_resuelto", "otro"]},
            "prioridad": {"type": "string", "enum": ["baja", "media", "alta"]}},
            "required": ["resumen", "motivo", "prioridad"]}}},
    {"type": "function", "function": {
        "name": "log_unmet_demand",
        "description": "Registra algo que el cliente busco y Tony2 no tiene (producto, color, talla o suela).",
        "parameters": {"type": "object", "properties": {
            "consulta": {"type": "string"},
            "motivo": {"type": "string", "enum": ["no_existe", "sin_stock", "talla_no_disponible", "otro"]},
            "filtros": {"type": "object"}},
            "required": ["consulta", "motivo"]}}},
]


class ToolExecutor:
    def __init__(self, catalog: CatalogRepository, policies: PolicyStore, store: Store, allowance_cm: float):
        self.catalog, self.policies, self.store, self.allowance_cm = catalog, policies, store, allowance_cm
        self._fns: dict[str, Callable[..., Any]] = {
            "search_products": self.search_products, "get_product": self.get_product,
            "compare_products": self.compare_products, "recommend_size": self.recommend_size,
            "get_policy": self.get_policy, "handoff_to_human": self.handoff_to_human,
            "log_unmet_demand": self.log_unmet_demand,
        }

    def run(self, session_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = self._fns.get(name)
        if fn is None:
            result = {"error": f"herramienta desconocida: {name}"}
        else:
            try:
                result = fn(session_id=session_id, **args)
            except TypeError as e:
                result = {"error": f"argumentos invalidos: {e}"}
        self.store.log_tool(session_id, name, args, result)
        return result

    def search_products(self, session_id: str, **kw) -> dict:
        return self.catalog.search(**kw)

    def get_product(self, session_id: str, sku: str) -> dict:
        return self.catalog.get_product(sku) or {"error": "sku_no_existe", "sku": sku}

    def compare_products(self, session_id: str, skus: list[str]) -> dict:
        items = [self.catalog.get_product(s) for s in skus]
        return {"productos": [i for i in items if i], "no_encontrados": [s for s, i in zip(skus, items) if not i]}

    def recommend_size(self, session_id: str, sku: str, largo_pie_cm: float) -> dict:
        v = self.catalog.variants.get(sku)
        if not v:
            return {"ok": False, "motivo": "sku_no_existe"}
        p = self.catalog.products[v.product_id]
        if not p.horma:
            return {"ok": False, "motivo": "producto_sin_talla_por_horma"}
        result = recommend_size(self.catalog.hormas[p.horma], float(largo_pie_cm), self.allowance_cm, v.tallas_stock)
        result["sku"] = sku
        return result

    def get_policy(self, session_id: str, tema: str) -> dict:
        return self.policies.get(tema)

    def handoff_to_human(self, session_id: str, resumen: str, motivo: str, prioridad: str) -> dict:
        ticket = self.store.create_handoff(session_id, resumen, motivo, prioridad)
        return {"ok": True, "ticket": ticket, "mensaje": "Un asesor continuara la conversacion."}

    def log_unmet_demand(self, session_id: str, consulta: str, motivo: str, filtros: dict | None = None) -> dict:
        self.store.log_unmet_demand(session_id, consulta, filtros, motivo)
        return {"ok": True}
