"""Capa agnostica de proveedor LLM.

LiteLLMClient habla con Anthropic, OpenAI, Google, etc. usando el mismo formato de herramientas.
Cambiar de proveedor = cambiar LLM_FAST_MODEL / LLM_SMART_MODEL en .env.
FakeLLM permite probar el loop del agente sin API ni costo.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    cost_usd: float = 0.0
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    def complete(self, model: str, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


class LiteLLMClient:
    def __init__(self, temperature: float | None = None, max_tokens: int = 800, reasoning_effort: str | None = "low",
                 timeout_s: float = 30.0, num_retries: int = 2):
        import litellm  # import diferido: los tests no lo necesitan
        litellm.drop_params = True  # si un proveedor no soporta un parametro, se omite en vez de fallar
        litellm.suppress_debug_info = True  # sin el banner "Give Feedback" en cada error
        self._litellm = litellm
        self.temperature, self.max_tokens, self.reasoning_effort = temperature, max_tokens, reasoning_effort
        self.timeout_s, self.num_retries = timeout_s, num_retries

    def complete(self, model: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        # num_retries: reintentos con espera creciente ante 429/503/timeouts del proveedor
        kwargs: dict[str, Any] = {"max_tokens": self.max_tokens, "timeout": self.timeout_s,
                                  "num_retries": self.num_retries}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        t0 = time.perf_counter()
        resp = self._litellm.completion(model=model, messages=messages, tools=tools, **kwargs)
        latency = int((time.perf_counter() - t0) * 1000)
        msg = resp.choices[0].message
        calls = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        try:
            cost = float(self._litellm.completion_cost(completion_response=resp) or 0.0)
        except Exception:
            cost = 0.0
        usage = getattr(resp, "usage", None)
        return LLMResponse(content=msg.content, tool_calls=calls, model=model, cost_usd=cost, latency_ms=latency,
                           input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                           output_tokens=getattr(usage, "completion_tokens", 0) or 0)


class FakeLLM:
    """LLM guionado para tests: devuelve respuestas en orden."""

    def __init__(self, script: list[LLMResponse]):
        self.script = list(script)
        self.calls: list[dict] = []

    def complete(self, model: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.calls.append({"model": model, "messages": [dict(m) for m in messages]})
        if not self.script:
            return LLMResponse(content="(sin respuesta guionada)", model=model)
        r = self.script.pop(0)
        r.model = model
        return r


SMART_HINTS = ("compar", "diferencia", "cual es mejor", "reclamo", "garantia", "no me sirve", "molest")


def choose_model(user_text: str, fast: str, smart: str) -> str:
    """Enrutamiento simple: modelo capaz para comparaciones, quejas o mensajes largos."""
    t = user_text.lower()
    if len(t) > 400 or any(h in t for h in SMART_HINTS):
        return smart
    return fast