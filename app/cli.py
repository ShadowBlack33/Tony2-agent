"""Chat de prueba en terminal:  python -m app.cli"""
import uuid

from app.factory import build_agent


def main():
    agent = build_agent()
    sid, history = uuid.uuid4().hex, []
    print(f"Asistente Tony2 | busqueda: {agent.tools.catalog.search_mode} (Ctrl+C para salir)\n")
    while True:
        try:
            text = input("Tu: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not text:
            continue
        result, history = agent.run_turn(sid, history, text)
        tools = ", ".join(t["name"] for t in result.tool_calls) or "-"
        print(f"\nTony2: {result.reply}\n   [herramientas: {tools} | modelo: {result.models[-1] if result.models else '-'}"
            f" | costo: ${result.cost_usd:.5f} | LLM {result.latency_ms} ms en {result.llm_calls} llamadas"
            f" | herramientas {result.tools_ms} ms]\n")


if __name__ == "__main__":
    main()
