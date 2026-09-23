"""Evalua uno o varios modelos con el golden set.

Uso:
  python -m evals.run_evals --models anthropic/claude-haiku-4-5-20251001 openai/<modelo> gemini/<modelo>
  python -m evals.run_evals --check        # valida el golden set sin llamar a ningun LLM

Salida: evals/reports/<timestamp>.md con acierto por categoria, violaciones, costo y latencia por modelo.
Las reglas son chequeos automaticos minimos; complementar con revision humana de una muestra.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def load_cases() -> list[dict]:
    return [json.loads(l) for l in (HERE / "golden_set.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def score(case: dict, reply: str, tools_used: list[str], handoff: bool, violations: list[str]) -> list[str]:
    exp, fails = case["expect"], []
    if exp.get("tools_any") and not set(exp["tools_any"]) & set(tools_used):
        fails.append(f"falta herramienta {exp['tools_any']}")
    for t in exp.get("tools_none", []):
        if t in tools_used:
            fails.append(f"uso indebido de {t}")
    if exp.get("must_include_any") and not any(norm(w) in norm(reply) for w in exp["must_include_any"]):
        fails.append(f"no menciona ninguno de {exp['must_include_any']}")
    for rx in exp.get("must_not_regex", []):
        if re.search(rx, norm(reply)):
            fails.append(f"contenido prohibido /{rx}/")
    if "handoff" in exp and exp["handoff"] != handoff:
        fails.append(f"handoff esperado={exp['handoff']} obtenido={handoff}")
    if violations:
        fails.append(f"guardrail activado: {violations}")
    return fails


def run_model(model: str, cases: list[dict], sleep_s: float = 0.0) -> list[dict]:
    """Evalua un modelo. sleep_s: pausa entre casos para no chocar con limites del nivel gratuito."""
    from app.factory import build_agent
    rows = []
    # ignore_cleanup_errors: en Windows SQLite puede retener el archivo un instante al cerrar
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        agent = build_agent(fast_model=model, smart_model=model, store_path=str(Path(tmp) / "eval.sqlite"))
        try:
            for n, case in enumerate(cases, 1):
                history, tools_used, cost, latency, handoff, violations, reply = [], [], 0.0, 0, False, [], ""
                provider_errors: list[str] = []
                try:
                    for turn in case["turns"]:
                        r, history = agent.run_turn(f"eval-{case['id']}", history, turn)
                        tools_used += [t["name"] for t in r.tool_calls]
                        cost += r.cost_usd
                        latency += r.latency_ms
                        handoff = handoff or r.handoff
                        violations += r.guardrail_violations
                        provider_errors += r.errors
                        reply = r.reply
                    fails = score(case, reply, tools_used, handoff, violations)
                    if provider_errors:
                        fails.append(f"fallas del proveedor: {len(provider_errors)}")
                except Exception as e:  # errores no controlados cuentan como fallo
                    fails = [f"error: {type(e).__name__}: {str(e)[:200]}"]
                print(f"  [{model}] {n}/{len(cases)} {case['id']}: {'OK' if not fails else 'FALLA'}")
                rows.append({"id": case["id"], "categoria": case["categoria"], "ok": not fails, "fallas": fails,
                             "costo_usd": cost, "latencia_ms": latency, "errores_proveedor": len(provider_errors),
                             "respuesta": reply})
                if sleep_s and n < len(cases):
                    time.sleep(sleep_s)
        finally:
            agent.tools.store.close()
    return rows


def report(results: dict[str, list[dict]]) -> str:
    lines = [f"# Evaluacion del asistente Tony2 — {datetime.now():%Y-%m-%d %H:%M}", "",
             "| Modelo | Acierto | Costo total (USD) | Costo/caso (USD) | Latencia p50 (ms) | Latencia max (ms) | Fallas proveedor |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for model, rows in results.items():
        ok = sum(r["ok"] for r in rows)
        costs = [r["costo_usd"] for r in rows]
        lats = [r["latencia_ms"] for r in rows] or [0]
        lines.append(f"| {model} | {ok}/{len(rows)} ({ok/len(rows):.0%}) | {sum(costs):.4f} | "
                     f"{sum(costs)/len(rows):.5f} | {int(statistics.median(lats))} | {max(lats)} | "
                     f"{sum(r.get('errores_proveedor', 0) for r in rows)} |")
    for model, rows in results.items():
        lines += ["", f"## {model}", "", "| Caso | Categoria | Resultado | Fallas |", "| --- | --- | --- | --- |"]
        for r in rows:
            lines.append(f"| {r['id']} | {r['categoria']} | {'OK' if r['ok'] else 'FALLA'} | "
                         f"{'; '.join(r['fallas']).replace('|', '/')} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sleep", type=float, default=4.0,
                    help="segundos de pausa entre casos (nivel gratuito: evita el limite por minuto)")
    ap.add_argument("--only", nargs="*", default=[], help="ids de casos a correr, ej: --only talla-02 adv-03")
    args = ap.parse_args()
    cases = load_cases()
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    if args.check or not args.models:
        cats = {}
        for c in cases:
            cats[c["categoria"]] = cats.get(c["categoria"], 0) + 1
        print(f"{len(cases)} casos validos: {cats}")
        return
    results = {m: run_model(m, cases, args.sleep) for m in args.models}
    out_dir = HERE / "reports"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d_%H%M}.md"
    out.write_text(report(results), encoding="utf-8")
    print(report(results).split("\n\n## ")[0])
    print(f"\nReporte completo: {out}")


if __name__ == "__main__":
    main()
