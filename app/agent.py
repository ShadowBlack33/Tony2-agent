"""Loop del agente: LLM -> herramientas -> LLM ... -> respuesta validada."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.guardrails import validate_reply
from app.llm import LLMClient, choose_model
from app.tools import TOOL_SCHEMAS, ToolExecutor

FALLBACK = ("Quiero darte la informacion exacta, asi que te paso con una persona del equipo. "
            "En un momento te responden por aqui.")
CORRECTION = ("Tu respuesta anterior incluyo datos no verificados ({v}). Reescribela usando SOLO precios, "
              "tallas y SKUs que aparezcan en resultados de herramientas; si falta el dato, consulta la herramienta.")


@dataclass
class TurnResult:
    reply: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: int = 0          # tiempo total en el LLM
    tools_ms: int = 0            # tiempo total en herramientas (incluye embeddings de busqueda)
    llm_calls: int = 0
    guardrail_violations: list[str] = field(default_factory=list)
    handoff: bool = False


class Agent:
    def __init__(self, llm: LLMClient, tools: ToolExecutor, system_prompt: str,
                 fast_model: str, smart_model: str, max_steps: int = 6):
        self.llm, self.tools, self.system_prompt = llm, tools, system_prompt
        self.fast_model, self.smart_model, self.max_steps = fast_model, smart_model, max_steps

    def run_turn(self, session_id: str, history: list[dict], user_text: str) -> tuple[TurnResult, list[dict]]:
        """history: mensajes previos (sin system). Devuelve resultado y el history actualizado."""
        model = choose_model(user_text, self.fast_model, self.smart_model)
        messages = [{"role": "system", "content": self.system_prompt}, *history,
                    {"role": "user", "content": user_text}]
        result = TurnResult(reply="")
        tool_outputs: list[Any] = []
        corrected = False

        for _ in range(self.max_steps):
            resp = self.llm.complete(model, messages, TOOL_SCHEMAS)
            result.models.append(resp.model)
            result.cost_usd += resp.cost_usd
            result.latency_ms += resp.latency_ms
            result.llm_calls += 1

            # 1) El modelo pidio herramientas: ejecutarlas y volver a llamarlo con los resultados
            if resp.tool_calls:
                messages.append({"role": "assistant", "content": resp.content or "",
                                 "tool_calls": [{"id": tc.id, "type": "function",
                                                 "function": {"name": tc.name,
                                                              "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                                                for tc in resp.tool_calls]})
                for tc in resp.tool_calls:
                    t0 = time.perf_counter()
                    out = self.tools.run(session_id, tc.name, tc.arguments)
                    result.tools_ms += int((time.perf_counter() - t0) * 1000)
                    tool_outputs.append(out)
                    result.tool_calls.append({"name": tc.name, "arguments": tc.arguments})
                    if tc.name == "handoff_to_human" and out.get("ok"):
                        result.handoff = True
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": json.dumps(out, ensure_ascii=False)})
                continue

            # 2) Respuesta final: validar precios, SKUs y tallas contra lo que devolvieron las herramientas
            reply = (resp.content or "").strip()
            tools_called = [t["name"] for t in result.tool_calls]
            violations = validate_reply(reply, tool_outputs, tools_called)
            if violations and not corrected:
                # Primera falla: se le pide corregir, con el modelo capaz
                corrected = True
                result.guardrail_violations.extend(violations)
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": CORRECTION.format(v=", ".join(violations))})
                model = self.smart_model
                continue
            if violations:
                # Segunda falla: no se arriesga, pasa a humano
                result.guardrail_violations.extend(violations)
                reply = self._fallback(session_id, user_text, result)
            result.reply = reply
            break
        else:
            # Se agotaron los pasos sin respuesta final
            result.reply = self._fallback(session_id, user_text, result)

        new_history = [*history, {"role": "user", "content": user_text},
                       {"role": "assistant", "content": result.reply}]
        return result, new_history

    def _fallback(self, session_id: str, user_text: str, result: TurnResult) -> str:
        self.tools.run(session_id, "handoff_to_human",
                       {"resumen": f"Fallback automatico. Ultimo mensaje: {user_text[:200]}",
                        "motivo": "no_resuelto", "prioridad": "media"})
        result.handoff = True
        return FALLBACK