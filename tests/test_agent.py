from app.factory import build_agent
from app.llm import FakeLLM, LLMResponse, ToolCall


def make(script, tmp_path):
    return build_agent(llm=FakeLLM(script), fast_model="fake/fast", smart_model="fake/smart",
                       store_path=str(tmp_path / "t.sqlite"), use_env_embedder=False)


def test_tool_then_answer(tmp_path):
    agent = make([
        LLMResponse(content=None, tool_calls=[ToolCall("1", "search_products", {"query": "guantes de portero"})]),
        LLMResponse(content="Tenemos los Guantes Control Grip a $69.000."),
    ], tmp_path)
    r, hist = agent.run_turn("s1", [], "tienen guantes?")
    assert r.tool_calls[0]["name"] == "search_products"
    assert r.guardrail_violations == [] and "69.000" in r.reply and len(hist) == 2


def test_guardrail_forces_correction(tmp_path):
    agent = make([
        LLMResponse(content="Los guantes cuestan $50.000."),               # precio inventado
        LLMResponse(content=None, tool_calls=[ToolCall("1", "search_products", {"query": "guantes"})]),
        LLMResponse(content="Los Guantes Control Grip cuestan $69.000."),
    ], tmp_path)
    r, _ = agent.run_turn("s2", [], "cuanto valen los guantes?")
    assert r.guardrail_violations and "69.000" in r.reply and not r.handoff


def test_fallback_to_human_after_repeated_violation(tmp_path):
    agent = make([LLMResponse(content="Cuesta $50.000."), LLMResponse(content="Cuesta $51.000.")], tmp_path)
    r, _ = agent.run_turn("s3", [], "precio?")
    assert r.handoff and "persona" in r.reply


def test_size_recommendation_tool(tmp_path):
    agent = make([
        LLMResponse(content=None, tool_calls=[ToolCall("1", "recommend_size", {"sku": "T2S-VER-FG", "largo_pie_cm": 26})]),
        LLMResponse(content="Te recomiendo talla 41."),
    ], tmp_path)
    r, _ = agent.run_turn("s4", [], "mi pie mide 26 cm, que talla del speed?")
    out = agent.tools.recommend_size("s4", "T2S-VER-FG", 26)
    assert out["ok"] and out["talla"] == "41" and r.reply.endswith("41.")
