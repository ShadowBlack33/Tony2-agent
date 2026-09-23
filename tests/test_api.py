from fastapi.testclient import TestClient

import app.main as main
from app.factory import build_agent
from app.llm import FakeLLM, LLMResponse, ToolCall


def test_chat_endpoint_keeps_session(tmp_path):
    main._agent = build_agent(llm=FakeLLM([
        LLMResponse(content=None, tool_calls=[ToolCall("1", "search_products", {"query": "balon"})]),
        LLMResponse(content="Tenemos el Balon Tony2 N5 a $59.000."),
        LLMResponse(content="Con gusto."),
    ]), fast_model="fake/fast", smart_model="fake/smart", store_path=str(tmp_path / "api.sqlite"), use_env_embedder=False)
    c = TestClient(main.app)
    r1 = c.post("/chat", json={"message": "tienen balones?"}).json()
    assert r1["tools"] == ["search_products"] and "59.000" in r1["reply"]
    r2 = c.post("/chat", json={"session_id": r1["session_id"], "message": "gracias"}).json()
    assert r2["session_id"] == r1["session_id"]
    assert len(main._sessions[r1["session_id"]]) == 4
